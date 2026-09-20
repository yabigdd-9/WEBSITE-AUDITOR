from auditor_core.bundles import build_fix_bundles, bundle_for, bundles_markdown


def sample(check_id, category, priority, effort="10 min", human=False):
    return {
        "check_id": check_id,
        "category": category,
        "priority": priority,
        "human_review": human,
        "defect": check_id,
        "fix": {"title": "Fix it", "effort": effort},
    }


def test_bundle_routing_is_explainable():
    assert bundle_for(sample("ecommerce.gst_clarity_missing", "conversion", 5)) == "ecommerce"
    assert bundle_for(sample("security.hsts_missing", "security", 3)) == "trust_security"
    assert bundle_for(sample("seo.h1_missing", "seo", 2, "2 min")) == "quick_wins"
    assert bundle_for(sample("seo.canonical_missing", "seo", 6, "1 hour")) == "seo_accessibility"


def test_build_fix_bundles_groups_actions_and_effort():
    remediation = {
        "domain": "example.co.nz",
        "actions": [
            sample("seo.h1_missing", "seo", 2, "2 min"),
            sample("security.hsts_missing", "security", 3, "15 min"),
            sample("ecommerce.gst_clarity_missing", "conversion", 5, "20 min", True),
        ],
    }
    report = build_fix_bundles(remediation)
    assert report["bundle_count"] == 3
    assert [bundle["bundle_id"] for bundle in report["bundles"]] == [
        "quick_wins",
        "trust_security",
        "ecommerce",
    ]
    assert "Fix Bundles — example.co.nz" in bundles_markdown(report)
