import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from casino_auditor.cli import validate_target, main


GOOD = {
    "url": "https://example.com",
    "approved_by": "Operator approval lead",
    "authorization_reference": "signed-approval-001",
    "scope": "public-site-audit",
    "expires_utc": "2099-01-01T00:00:00Z",
}


class CasinoAuditCLIUnitTests(unittest.TestCase):
    def test_authorized_target(self):
        self.assertEqual(validate_target(GOOD)[0], "example.com")

    def test_rejects_missing_approval(self):
        with self.assertRaises(ValueError):
            validate_target({**GOOD, "authorization_reference": ""})

    def test_rejects_expired_approval(self):
        with self.assertRaises(ValueError):
            validate_target({**GOOD, "expires_utc": "2020-01-01T00:00:00Z"})

    def test_rejects_internal_hosts(self):
        for url in ["http://example.com", "https://localhost", "https://127.0.0.1",
                    "https://localhost.local", "https://example.com:8443",
                    "https://example.com/admin", "https://example.com?token=x"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_target({**GOOD, "url": url})

    def test_rejects_active_security_scope(self):
        with self.assertRaises(ValueError):
            validate_target({**GOOD, "scope": "penetration-test"})

    def test_dry_run_does_not_start_scanner(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "targets.json"
            manifest.write_text(json.dumps({"targets": [GOOD]}))
            self.assertEqual(main(["--manifest", str(manifest)]), 0)


if __name__ == "__main__":
    unittest.main()
