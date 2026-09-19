import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "integrations" / "deepseek-harness" / "scripts" / "dsh_mm_bridge.py"
SPEC = importlib.util.spec_from_file_location("dsh_mm_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bridge)


class DeepSeekHarnessBridgeTests(unittest.TestCase):
    def test_runtime_is_allowlisted(self):
        args = bridge.parser().parse_args(["runtime"])
        cmd, _ = bridge.build_command(args)
        self.assertEqual(cmd[-1], "--runtime")
        self.assertTrue(cmd[0].endswith("money-machine/mm"))

    def test_private_urls_are_blocked(self):
        for url in (
            "http://127.0.0.1:11434",
            "http://10.0.0.1",
            "http://192.168.1.2",
            "http://localhost:3000",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    bridge._public_http_url(url)

    def test_public_url_is_allowed(self):
        self.assertEqual(
            bridge._public_http_url("https://example.co.nz"),
            "https://example.co.nz",
        )

    def test_repo_path_cannot_escape(self):
        with self.assertRaises(ValueError):
            bridge._repo_path("../../outside.txt")

    def test_email_find_fails_closed(self):
        args = bridge.parser().parse_args(["email-find", "--business-id", "5"])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.BOUNDED_WRITE_ENV, None)
            with self.assertRaises(PermissionError):
                bridge.build_command(args)

    def test_email_find_requires_explicit_supervised_flag(self):
        args = bridge.parser().parse_args(["email-find", "--business-id", "5"])
        with patch.dict(os.environ, {bridge.BOUNDED_WRITE_ENV: "1"}):
            cmd, _ = bridge.build_command(args)
        self.assertEqual(cmd[-3:], ["email-find", "5", "--json"])


if __name__ == "__main__":
    unittest.main()
