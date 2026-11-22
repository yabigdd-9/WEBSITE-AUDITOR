import copy
import hashlib
import unittest

from scripts import cloud_pipeline_outcomes as o
from scripts import cloud_prospect_pipeline as p


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.entity = hashlib.sha256(b"example.com").hexdigest()
        self.state = p.empty_state()
        self.state["prospects"][self.entity] = {
            "status": "complete",
            "draft": "Evidence-backed draft",
        }
        self.counter = 0

    def item(self, action, status, record="record-1", **extra):
        self.counter += 1
        return dict(
            event_id=f"event-{self.counter}",
            entity_id=self.entity,
            action=action,
            status=status,
            record_id=record,
            timestamp_utc="2026-01-01T00:00:00Z",
            evidence_sha256=hashlib.sha256(str(self.counter).encode()).hexdigest(),
            owner_verified=True,
            **extra,
        )

    def apply(self, *events):
        return o.import_outcomes(
            self.state,
            {"kind": o.KIND, "events": list(events)},
            now=1800000000,
            run_id="run-1",
            actor="owner",
        )

    def approve(self):
        item = self.item("approval", "approved")
        item["evidence_sha256"] = hashlib.sha256(b"Evidence-backed draft").hexdigest()
        self.apply(item)

    def test_delivery_requires_provider_acceptance_and_exact_approval(self):
        with self.assertRaises(ValueError):
            self.apply(self.item("send", "queued"))
        self.approve()
        self.apply(self.item("send", "queued"), self.item("send", "attempted"))
        with self.assertRaises(ValueError):
            self.apply(self.item("send", "delivered"))
        self.apply(self.item("send", "provider_accepted"))
        self.assertEqual(p.metrics(self.state)["contacts_sent"], 1)
        self.assertEqual(p.metrics(self.state)["delivered"], 0)
        self.apply(self.item("send", "delivered"))
        self.assertEqual(p.metrics(self.state)["delivered"], 1)
        self.assertEqual(p.metrics(self.state)["approvals_pending"], 0)

    def test_revenue_requires_receipt_and_invoice_not_quote(self):
        self.apply(self.item("quote", "issued"), self.item("quote", "accepted"))
        self.assertEqual(p.metrics(self.state)["confirmed_revenue"], 0)
        payment = self.item("payment", "confirmed", amount_minor=12345, currency="NZD")
        with self.assertRaises(ValueError):
            self.apply(payment)
        self.apply(self.item("invoice", "issued"), payment)
        self.assertEqual(p.metrics(self.state)["confirmed_revenue_minor"], 12345)
        self.assertEqual(self.apply(payment), 0)
        self.assertEqual(p.metrics(self.state)["confirmed_revenue_minor"], 12345)
        self.apply(self.item("payment", "refunded", amount_minor=2345, currency="NZD"))
        self.assertEqual(p.metrics(self.state)["confirmed_revenue_minor"], 10000)
        with self.assertRaises(ValueError):
            self.apply(self.item("payment", "refunded", amount_minor=10001, currency="NZD"))

    def test_failed_bundle_is_atomic_and_private_fields_rejected(self):
        before = copy.deepcopy(self.state)
        valid = self.item("invoice", "issued")
        bad = self.item("payment", "confirmed", amount_minor=100, currency="NZD")
        bad["recipient_email"] = "private@example.com"
        with self.assertRaises(ValueError):
            self.apply(valid, bad)
        self.assertEqual(self.state, before)

    def test_duplicate_source_and_conflicting_ids_rejected(self):
        event = self.item("response", "received")
        self.apply(event)
        other = {**event, "event_id": "different-id"}
        with self.assertRaises(ValueError):
            self.apply(other)
        with self.assertRaises(ValueError):
            self.apply({**event, "record_id": "changed"})

    def test_opt_out_clears_draft_and_blocks_new_sends(self):
        self.approve()
        self.apply(self.item("suppression", "opted_out"))
        self.assertEqual(self.state["prospects"][self.entity]["status"], "suppressed")
        self.assertIsNone(self.state["prospects"][self.entity]["draft"])
        with self.assertRaises(ValueError):
            self.apply(self.item("send", "queued"))

    def test_billing_and_invalid_money_never_infer_revenue(self):
        self.apply(
            self.item("invoice", "issued"),
            self.item("cost", "confirmed", amount_minor=99, currency="NZD"),
        )
        self.assertEqual(p.metrics(self.state)["confirmed_revenue"], 0)
        self.assertEqual(p.metrics(self.state)["confirmed_cost_minor"], 99)
        for value in (True, -1, 0, 1.5):
            with self.assertRaises(ValueError):
                self.apply(self.item("payment", "confirmed", amount_minor=value, currency="NZD"))

    def test_evidence_and_owner_attestation_required(self):
        item = self.item("invoice", "issued")
        with self.assertRaises(ValueError):
            self.apply({**item, "owner_verified": False})
        with self.assertRaises(ValueError):
            self.apply({**item, "evidence_sha256": "unverified"})
        with self.assertRaises(ValueError):
            self.apply(self.item("approval", "approved"))


if __name__ == "__main__":
    unittest.main()
