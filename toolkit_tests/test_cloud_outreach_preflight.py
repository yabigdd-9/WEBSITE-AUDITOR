import hashlib
import unittest
from unittest.mock import patch

from scripts.cloud_outreach_preflight import review


class OutreachPreflightTests(unittest.TestCase):
    def setUp(self):
        self.prospect = {
            "domain": "example.com",
            "active": True,
            "suppressed": False,
            "findings": [
                {
                    "finding_id": "current-meta",
                    "confidence": "observed",
                    "evidence_check_status": "ok",
                    "independently_verified": True,
                    "source_url": "https://example.com/",
                }
            ],
        }
        self.contact = {
            "address": "office@example.com",
            "address_verified": True,
            "address_provenance": "own_website",
            "address_source_url": "https://example.com/contact",
            "address_verified_at": "2026-11-16T00:00:00Z",
            "verified_finding_ids": ["current-meta"],
        }
        self.sender = {
            "name": "Owner",
            "email": "owner@example.org",
            "contact_details": "Owner contact",
            "unsubscribe_verified": True,
        }
        self.message = "Individually reviewed message"
        self.approval = hashlib.sha256(self.message.encode()).hexdigest()

    def run_review(self):
        with patch(
            "scripts.cloud_outreach_preflight.consent_check",
            return_value=("PERMITTED", [], "email"),
        ):
            return review(
                self.prospect,
                self.contact,
                self.sender,
                now=1794787200,
                message=self.message,
                approved_sha256=self.approval,
            )

    def test_canonical_consent_gate_rejects_ratified_guessed_address(self):
        from outreach.consent_gate import check

        contact = {
            "business_name": "Example business",
            "address": "office@example.com",
            "address_source_url": "https://example.com/contact",
            "address_found_where": "Contact block",
            "surrounding_wording": "Contact office@example.com about work enquiries",
            "invites_contact": True,
            "refusal_statement_present": False,
            "role_or_personal": "role",
            "relevance_to_role": "An observed issue on this business's own website",
            "prior_relationship": "none",
            "consent_type_claimed": "INFERRED",
            "why_consent_believed": "The verified office address invites relevant work enquiries on its own website.",
            "human_ratified_by": "Owner",
            "verified_defects": ["NO_META_DESCRIPTION"],
        }
        with (
            patch("outreach.consent_gate.load_suppression", return_value=set()),
            patch("outreach.consent_gate.recently_contacted", return_value=False),
        ):
            decision, reasons, _ = check(contact)
            self.assertEqual(decision, "BLOCKED")
            self.assertIn("INFERENCE_UNSUPPORTED:recipient_not_directly_confirmed", reasons)
            contact["address_verified"] = True
            self.assertEqual(check(contact)[0], "PERMITTED")
            contact["address_found_where"] = "email inferred from domain-pattern"
            self.assertEqual(check(contact)[0], "BLOCKED")

    def test_ratified_but_guessed_email_still_blocked(self):
        self.contact["address_verified"] = False
        result = self.run_review()
        self.assertIn("recipient_not_directly_verified", result["blockers"])
        self.assertFalse(result["candidate_review_ready"])

    def test_contradictory_provenance_cannot_be_marked_verified(self):
        self.contact["why_consent_believed"] = (
            "EMAIL NOT DIRECTLY CONFIRMED — domain-pattern inference"
        )
        self.assertIn(
            "recipient_provenance_contradicts_verification", self.run_review()["blockers"]
        )

    def test_old_defects_do_not_authorize_current_claims(self):
        self.contact["verified_finding_ids"] = ["old-broken-link"]
        self.assertIn(
            "claims_not_bound_to_current_verified_findings", self.run_review()["blockers"]
        )

    def test_suppression_and_missing_exact_approval_block(self):
        self.prospect["suppressed"] = True
        self.approval = "not-the-current-message"
        result = self.run_review()
        self.assertIn("target_suppressed", result["blockers"])
        self.assertIn("exact_message_approval_missing", result["blockers"])

    def test_stale_source_and_missing_unsubscribe_block(self):
        self.contact["address_verified_at"] = "2026-08-01T00:00:00Z"
        self.sender["unsubscribe_verified"] = False
        result = self.run_review()
        self.assertIn("recipient_verification_stale_or_missing", result["blockers"])
        self.assertIn("unsubscribe_unverified", result["blockers"])

    def test_valid_review_never_releases_sending(self):
        result = self.run_review()
        self.assertTrue(result["candidate_review_ready"], result)
        self.assertFalse(result["send_enabled"])
        self.assertEqual(result["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()
