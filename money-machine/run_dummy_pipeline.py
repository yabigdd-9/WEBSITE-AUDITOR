#!/usr/bin/env python3
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "money_machine.db"
REPORT = ROOT / "reports" / "dummy-pipeline-latest.json"
now = datetime.now(timezone.utc).isoformat()

def event(db, business_id, stage, detail):
    db.execute(
        "INSERT INTO pipeline_events(business_id, stage, event_at, detail) VALUES (?, ?, ?, ?)",
        (business_id, stage, now, detail),
    )

with sqlite3.connect(DB) as db:
    db.execute("PRAGMA foreign_keys = ON")
    dummy_ids = [row[0] for row in db.execute("SELECT id FROM businesses WHERE is_dummy = 1")]
    for dummy_id in dummy_ids:
        offer_ids = [row[0] for row in db.execute("SELECT id FROM offers WHERE business_id = ?", (dummy_id,))]
        for offer_id in offer_ids:
            db.execute("DELETE FROM outreach WHERE offer_id = ?", (offer_id,))
            db.execute("DELETE FROM approval_events WHERE object_type = 'offer' AND object_id = ?", (offer_id,))
        db.execute("DELETE FROM pipeline_events WHERE business_id = ?", (dummy_id,))
        db.execute("DELETE FROM contacts WHERE business_id = ?", (dummy_id,))
        db.execute("DELETE FROM offers WHERE business_id = ?", (dummy_id,))
        db.execute("DELETE FROM audits WHERE business_id = ?", (dummy_id,))
    db.execute("DELETE FROM businesses WHERE is_dummy = 1")
    industry_id = db.execute(
        "INSERT INTO industries(name, region, market_notes, evidence, last_reviewed) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET last_reviewed=excluded.last_reviewed RETURNING id",
        ("Dummy NZ Home Services", "New Zealand", "Synthetic test segment", "TEST DATA ONLY", now),
    ).fetchone()[0]
    business_id = db.execute(
        "INSERT INTO businesses(name, industry_id, region, public_website, source, discovered_at, current_status, is_dummy) "
        "VALUES (?, ?, ?, ?, ?, ?, 'discovered', 1) RETURNING id",
        ("Koru Test Plumbing Ltd", industry_id, "Auckland", "https://example.invalid", "synthetic fixture", now),
    ).fetchone()[0]
    event(db, business_id, "discovered", "Synthetic business created; no public lookup and no personal data.")

    score_components = {
        "demonstrated_pain": 16,
        "ability_to_pay": 10,
        "identifiable_prospects": 8,
        "visible_digital_weakness": 9,
        "urgency": 7,
        "repeatability": 9,
        "recurring_revenue": 8,
        "ease_of_building": 4,
        "competition": 3,
        "low_friction": 4,
    }
    opportunity_score = sum(score_components.values())
    audit_id = db.execute(
        "INSERT INTO audits(business_id, mobile_quality, conversion_quality, quote_flow, booking_flow, seo_basics, trust_signals, page_speed, accessibility, broken_paths, follow_up_quality, crm_signal, automation_opportunities, evidence, opportunity_score, created_at) "
        "VALUES (?, 35, 30, 10, 20, 40, 50, 45, 50, 'synthetic: none tested', 20, 15, ?, ?, ?, ?) RETURNING id",
        (business_id, "Mobile quote request and automated acknowledgement", "SYNTHETIC TEST EVIDENCE; not a claim about a real business", opportunity_score, now),
    ).fetchone()[0]
    db.execute("UPDATE businesses SET current_status='audited' WHERE id=?", (business_id,))
    event(db, business_id, "audited", f"Synthetic audit {audit_id} stored with explicit test-only evidence.")
    db.execute("UPDATE businesses SET current_status='scored' WHERE id=?", (business_id,))
    event(db, business_id, "scored", f"Opportunity score {opportunity_score}/100 from bounded fixture inputs.")

    draft = (
        "INTERNAL TEST DRAFT — DO NOT SEND\n\n"
        "The synthetic audit suggests customers may abandon phone-only quote requests after hours. "
        "A mobile quote form with automatic confirmation could reduce that friction. "
        "Before any real proposal, verify the issue on a real business and obtain human approval."
    )
    offer_id = db.execute(
        "INSERT INTO offers(business_id, problem, proposed_outcome, implementation_scope, price_test, estimated_delivery_effort, expected_value, offer_score, draft, external_send_approved, created_at) "
        "VALUES (?, ?, ?, ?, NULL, 8, 0, 72, ?, 0, ?) RETURNING id",
        (business_id, "Synthetic phone-only quote-flow friction", "Faster mobile quote capture and acknowledgement", "Local prototype only; no production mutation", draft, now),
    ).fetchone()[0]
    db.execute("UPDATE businesses SET current_status='offer_drafted' WHERE id=?", (business_id,))
    event(db, business_id, "offer_drafted", f"Offer {offer_id} drafted locally; external_send_approved=0.")
    db.execute(
        "INSERT INTO approval_events(action_type, object_type, object_id, requested_at, approved, notes) VALUES ('external_send', 'offer', ?, ?, 0, ?)",
        (offer_id, now, "Test pipeline stops here by design."),
    )
    db.execute("UPDATE businesses SET current_status='human_review' WHERE id=?", (business_id,))
    event(db, business_id, "human_review", "Pipeline halted at approval gate; nothing was sent.")
    db.execute(
        "INSERT INTO agent_runs(task, agent, model, cost_nzd, outcome, created_at) VALUES (?, ?, ?, 0, ?, ?)",
        ("dummy discovery-to-offer pipeline", "deterministic-local-test", "none", "passed; stopped before external send", now),
    )
    rows = db.execute(
        "SELECT stage, detail FROM pipeline_events WHERE business_id=? ORDER BY id", (business_id,)
    ).fetchall()
    result = {
        "test": "dummy prospect pipeline",
        "business_id": business_id,
        "opportunity_score": opportunity_score,
        "score_components": score_components,
        "stages": [{"stage": stage, "detail": detail} for stage, detail in rows],
        "external_send_approved": False,
        "external_send_performed": False,
        "cost_nzd": 0,
        "status": "PASS — awaiting human review",
    }

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
