"""
Tests for proposal scope mapping.
"""

from proposal_engine.scope import map_finding_to_scope, deduplicate_scope_items


def test_map_finding_to_scope():
    finding = {
        "id": "f1",
        "title": "Missing meta description",
        "description": "The homepage is missing a meta description.",
        "evidence": "Seen on homepage",
        "urls": ["https://example.com/"],
        "root_cause": "Not set in CMS",
        "recommended_action": "Add meta description",
        "deliverables": ["Updated meta description"],
        "verification_method": "View source",
        "effort_band": "XS",
        "dependencies": [],
        "risk": "LOW",
    }
    scope_item = map_finding_to_scope(finding)
    assert scope_item.scope_id == "scope-f1"
    assert scope_item.title == "Missing meta description"
    assert scope_item.effort_band == "XS"


def test_deduplicate_scope_items():
    # Create two scope items with the same scope_id
    item1 = map_finding_to_scope({
        "id": "f1",
        "title": "Test",
        "description": "desc",
        "evidence": "ev",
        "urls": [],
        "root_cause": "rc",
        "proposed_work": "work",
        "deliverables": [],
        "verification_method": "ver",
        "effort_band": "XS",
        "dependencies": [],
        "risk": "LOW",
    })
    item2 = map_finding_to_scope({
        "id": "f1",  # same id
        "title": "Test 2",
        "description": "desc2",
        "evidence": "ev2",
        "urls": [],
        "root_cause": "rc2",
        "proposed_work": "work2",
        "deliverables": [],
        "verification_method": "ver2",
        "effort_band": "XS",
        "dependencies": [],
        "risk": "LOW",
    })
    items = [item1, item2]
    unique = deduplicate_scope_items(items)
    assert len(unique) == 1
    assert unique[0].scope_id == "scope-f1"
