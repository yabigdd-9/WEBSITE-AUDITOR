import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_pipeline_checkpoint as c


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS can return a temporary path under a symlinked system directory.
        self.root = Path(self.temp.name).resolve()
        env = patch.dict("os.environ", {"RUNNER_TEMP": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.ids = [10, 9]
        self.jobs = {10: "success", 9: "success"}
        self.info = {"head_branch": "master", "event": "workflow_dispatch", "path": c.WORKFLOW_PATH}
        self.downloaded = []

    def query(self, args):
        if args[0] == "run":
            return [{"databaseId": x} for x in self.ids]
        if args[1].endswith("/jobs"):
            identity = int(args[1].split("/")[-2])
            return {"jobs": [{"name": "draft-pipeline", "conclusion": self.jobs[identity]}]}
        return self.info

    def download(self, identity, directory):
        self.downloaded.append(identity)
        (directory / "pipeline-state.enc").write_bytes(b"ciphertext")

    def restore(self, **kwargs):
        return c.restore(
            repo="owner/repo",
            current_id=11,
            state_path=self.root / "state.enc",
            query=self.query,
            download=kwargs.pop("download", self.download),
            **kwargs,
        )

    def test_restore_latest_and_skip_disabled_runs(self):
        self.jobs[10] = "skipped"
        result = self.restore()
        self.assertEqual(result["source_run"], 9)
        self.assertEqual((self.root / "state.enc").read_bytes(), b"ciphertext")
        self.assertFalse(result["recovery"])

    def test_failed_prior_run_never_silently_falls_back(self):
        self.jobs[10] = "failure"

        def missing(identity, directory):
            self.assertEqual(identity, 10)

        with self.assertRaises(ValueError):
            self.restore(download=missing)
        self.assertFalse((self.root / "state.enc").exists())

    def test_owner_can_explicitly_recover_trusted_older_checkpoint(self):
        result = self.restore(recovery_id=9)
        self.assertTrue(result["recovery"])
        self.assertEqual(self.downloaded, [9])

    def test_bootstrap_only_before_worker_history(self):
        self.ids = []
        with self.assertRaises(ValueError):
            self.restore()
        self.assertTrue(self.restore(bootstrap=True)["bootstrap"])
        self.ids = [10]
        with self.assertRaises(ValueError):
            self.restore(bootstrap=True)

    def test_untrusted_recovery_and_future_ids_rejected(self):
        self.info["event"] = "pull_request"
        with self.assertRaises(ValueError):
            self.restore(recovery_id=9)
        with self.assertRaises(ValueError):
            self.restore(recovery_id=12)
        self.assertEqual(self.downloaded, [])

    def test_missing_worker_metadata_blocks_restore(self):
        def query(args):
            if args[0] == "run":
                return [{"databaseId": 10}]
            return {"jobs": []}

        with self.assertRaises(ValueError):
            c.restore(
                repo="owner/repo",
                current_id=11,
                state_path=self.root / "state.enc",
                query=query,
                download=self.download,
            )

    def test_push_checkpoint_is_selected_before_older_manual_checkpoint(self):
        events = []

        def query(args):
            if args[0] == "run":
                event = args[args.index("--event") + 1]
                events.append(event)
                return [{"databaseId": 10 if event == "push" else 9}]
            if args[1].endswith("/jobs"):
                return {"jobs": [{"name": "draft-pipeline", "conclusion": "success"}]}
            return {"head_branch": "master", "event": "push", "path": c.WORKFLOW_PATH}

        result = c.restore(
            repo="owner/repo", current_id=11, state_path=self.root / "state.enc",
            query=query, download=self.download,
        )
        self.assertEqual(set(events), {"schedule", "workflow_dispatch", "push"})
        self.assertEqual(result["source_run"], 10)
        self.assertEqual(self.downloaded, [10])

    def test_push_requires_trusted_branch_and_workflow(self):
        good = {"head_branch": "master", "event": "push", "path": c.WORKFLOW_PATH}
        self.assertTrue(c.eligible_run(good))
        self.assertFalse(c.eligible_run({**good, "head_branch": "feature"}))
        self.assertFalse(c.eligible_run({**good, "path": ".github/workflows/other.yml"}))


if __name__ == "__main__":
    unittest.main()
