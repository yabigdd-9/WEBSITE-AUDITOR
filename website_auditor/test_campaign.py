from pathlib import Path

from website_auditor.outreach.campaign import (
    render_template,
    simulate_campaign,
    spam_risk,
)
from website_auditor.outreach.suppression import SuppressionStore


def test_template_reports_missing_variables():
    rendered, missing = render_template(
        "Subject: Hello {contact_name}\nHi {contact_name}, {top_issue}",
        {"contact_name": "Sam"},
    )
    assert missing == ["top_issue"]
    assert "{top_issue}" in rendered


def test_spam_risk_flags_aggressive_language():
    result = spam_risk("ACT NOW!!! GUARANTEED", "Buy now. Limited time.")
    assert result["risk"] in {"medium", "high"}
    assert result["score"] > 0


def test_campaign_simulation_never_exposes_transport(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    report = simulate_campaign(
        [{
            "domain": "example.co.nz",
            "email": "owner@example.co.nz",
            "contact_name": "Sam",
            "top_issue": "missing H1",
            "opportunity_score": "80",
            "quick_win_count": "3",
            "sender_name": "Dion",
            "agency_name": "Example Digital",
            "physical_address": "1 Example Street, Christchurch",
        }],
        "Subject: Quick note about {domain}\nHi {contact_name}, I noticed {top_issue}. Reply no if not useful.",
        suppression_store=store,
    )
    assert report["transport_available"] is False
    assert report["mode"] == "simulation_only"
    assert report["results"][0]["ranking"]["explanation"]


def test_campaign_simulation_honours_suppression(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    store.suppress_email("owner@example.co.nz", reason="opt-out")
    report = simulate_campaign(
        [{"domain": "example.co.nz", "email": "owner@example.co.nz"}],
        "Subject: Hello\nHi there",
        suppression_store=store,
    )
    result = report["results"][0]
    assert result["suppression"]["suppressed"] is True
    assert result["eligible_for_human_send_review"] is False
