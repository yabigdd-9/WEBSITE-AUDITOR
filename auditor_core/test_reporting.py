import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name("fixtures")


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dashboard_escapes_content_and_applies_safe_branding():
    dashboard = load_module("audit_dashboard_test", "audit-dashboard.py")
    audit = json.loads((FIXTURES / "audit_before.json").read_text())
    audit["domain"] = '<script>alert("x")</script>'
    audit["site_category_scores"] = {"overall_health_score": 95}
    audit["site_findings"] = audit["findings"]

    rendered = dashboard.generate_dashboard(
        [audit],
        {},
        title="Client Audit",
        tagline="Prepared for Example",
        accent="not-a-colour",
    )
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "Client Audit" in rendered
    assert "Prepared for Example" in rendered
    assert "color:#7dd3fc" in rendered
    assert ">95<" in rendered


def test_portfolio_exports_csv_xlsx_and_pdf(tmp_path: Path):
    exporter = load_module("portfolio_export_test", "portfolio-export.py")
    audit = json.loads((FIXTURES / "audit_before.json").read_text())
    audit["score"] = 42
    audit["audit_profile"] = {"name": "standard"}
    audit["site_type"] = {"site_type": "lead_generation"}

    rows = exporter.portfolio_rows([audit])
    csv_path = exporter.export_csv(rows, tmp_path / "portfolio.csv")
    xlsx_path = exporter.export_xlsx(rows, tmp_path / "portfolio.xlsx")
    pdf_path = exporter.export_pdf(rows, tmp_path / "portfolio.pdf", title="Client Portfolio")

    assert "example.co.nz" in csv_path.read_text(encoding="utf-8-sig")
    assert xlsx_path.read_bytes()[:2] == b"PK"
    assert pdf_path.read_bytes()[:4] == b"%PDF"
