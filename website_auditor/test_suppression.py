from pathlib import Path

from website_auditor.outreach.suppression import SuppressionStore


def test_email_suppression_is_normalized_and_hashed(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    record = store.suppress_email(" Person@Example.co.nz ", reason="opt-out", source="test")
    assert record["masked"] == "p***@example.co.nz"
    raw = (tmp_path / "suppression.json").read_text()
    assert "person@example.co.nz" not in raw
    assert store.check(email="person@example.co.nz")["suppressed"] is True


def test_domain_suppression_blocks_any_email_on_domain(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    store.suppress_domain("Example.co.nz", reason="do-not-contact")
    result = store.check(email="someone@example.co.nz")
    assert result["suppressed"] is True
    assert result["scope"] == "domain"


def test_unsuppress_removes_records(tmp_path: Path):
    store = SuppressionStore(tmp_path / "suppression.json")
    store.suppress_email("person@example.co.nz")
    assert store.unsuppress_email("person@example.co.nz") is True
    assert store.check(email="person@example.co.nz")["suppressed"] is False
