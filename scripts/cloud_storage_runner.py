"""Select one explicit cloud authority; never fall back or bootstrap Postgres."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def run_postgres(state_path, key):
    from cryptography.fernet import Fernet

    from scripts.cloud_prospect_pipeline import main, seal
    from scripts.postgres_backup import read_private
    from scripts.postgres_store import PostgresPipelineStore

    cipher = Fernet(key.encode())  # Validate before any audits or connection.
    if os.environ.get("BOOTSTRAP") == "true" or os.environ.get("WA_RECOVERY_RUN", "").strip():
        raise ValueError("Postgres requires the reviewed migration/recovery path")
    store = PostgresPipelineStore()
    state = store.read()
    if not state or state.get("storage_authority") != "postgres" or not state.get("checkpoint_import"):
        raise ValueError("Import the current checkpoint before selecting Postgres")
    if main(["--postgres"]) != 0:
        raise ValueError("Private worker failed")
    with tempfile.TemporaryDirectory(prefix="wa-pg-export-", dir=state_path.parent) as directory:
        backup = Path(directory) / "paired.json"
        store.backup(backup)
        content = read_private(backup)
        # Snapshot and operational export come from the same locked consistent
        # export. Only ciphertext may leave this temporary directory.
        seal(content["state"], state_path, key)
        encrypted = state_path.with_name("pipeline-postgres-backup.enc")
        fd = os.open(encrypted, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(cipher.encrypt(backup.read_bytes()))
            stream.flush()
            os.fsync(stream.fileno())


def main():
    try:
        from scripts.cloud_pipeline_checkpoint import restore
        from scripts.cloud_prospect_pipeline import main as pipeline_main
        from scripts.cloud_prospect_pipeline import private_state_path

        mode = os.environ.get("WA_PIPELINE_STORAGE", "checkpoint")
        state_path = private_state_path(Path(os.environ["RUNNER_TEMP"]) / "pipeline-state.enc")
        if mode == "postgres":
            run_postgres(state_path, os.environ.get("WA_PIPELINE_STATE_KEY", ""))
        elif mode == "checkpoint":
            recovery = os.environ.get("WA_RECOVERY_RUN", "").strip()
            bootstrap = os.environ.get("BOOTSTRAP") == "true"
            restore(
                repo=os.environ["GITHUB_REPOSITORY"], current_id=int(os.environ["GITHUB_RUN_ID"]),
                state_path=state_path, bootstrap=bootstrap,
                recovery_id=int(recovery) if recovery else None,
            )
            args = ["--state", str(state_path)]
            if bootstrap:
                args.append("--bootstrap")
            return pipeline_main(args)
        else:
            raise ValueError("Unknown storage authority")
        return 0
    except Exception:
        print("Cloud storage execution blocked; no fallback was attempted.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
