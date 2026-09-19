"""Grader unit tests — pure functions, no network, stdlib only."""

import unittest

from integrations.tier1_enrichment.graders import grade_security_headers


class TestGradeSecurityHeaders(unittest.TestCase):
    def test_perfect_headers_get_a_plus(self):
        headers = {
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=()",
            "Cross-Origin-Opener-Policy": "same-origin",
        }
        out = grade_security_headers(headers)
        self.assertEqual(out["grade"], "A+")
        self.assertEqual(out["score"], 100)
        self.assertEqual(out["defects"], [])

    def test_empty_headers_get_f_with_seven_defects(self):
        out = grade_security_headers({})
        self.assertEqual(out["grade"], "F")
        self.assertEqual(len(out["defects"]), 7)
        for d in out["defects"]:
            self.assertIn("defect", d)
            self.assertIn("impact", d)

    def test_typical_wordpress_gets_mid_grade(self):
        out = grade_security_headers({
            "X-Frame-Options": "SAMEORIGIN",
            "X-Content-Type-Options": "nosniff",
        })
        self.assertIn(out["grade"], ("D", "E", "F"))
        self.assertTrue(any("HSTS" in d["defect"] or "strict-transport" in d["defect"].lower()
                            for d in out["defects"]))

    def test_weak_hsts_flagged_not_failed(self):
        out = grade_security_headers({
            "Strict-Transport-Security": "max-age=1000",
            "Content-Security-Policy": "default-src 'self'",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=()",
            "Cross-Origin-Opener-Policy": "same-origin",
        })
        weak = [r for r in out["headers"]
                if r["header"] == "strict-transport-security"]
        self.assertEqual(weak[0]["status"], "weak")
        self.assertLess(out["score"], 100)

    def test_header_names_case_insensitive(self):
        out = grade_security_headers({"STRICT-TRANSPORT-SECURITY": "max-age=31536000"})
        row = [r for r in out["headers"] if r["header"] == "strict-transport-security"][0]
        self.assertEqual(row["status"], "pass")


if __name__ == "__main__":
    unittest.main()
