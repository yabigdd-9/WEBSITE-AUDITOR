from auditor_toolkit.evidence_brief import create_evidence_brief


def test_evidence_summary_is_exposed_to_downstream_drafting():
    brief = create_evidence_brief(
        {
            "status": "complete",
            "health_score": 75,
            "defects": [{"severity": "high", "check": "no_title", "finding": "Missing title"}],
        }
    )

    assert brief["summary"]["evidence_summary"] == (
        "1 high-priority issue(s) impacting user experience."
    )
