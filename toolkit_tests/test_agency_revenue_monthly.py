import copy
import json
import smtplib
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from auditor_toolkit.agency_config import load_config, validate_config
from auditor_toolkit.cli import main
from auditor_toolkit.monthly import MonthlyStore, collect_month, due_monthly, generate_monthly
from auditor_toolkit.revenue import calculate_revenue, roi_csv
from auditor_toolkit.storage import History


def assumption():
    return {
        "currency": "NZD",
        "monthly_visitors": 2000,
        "baseline_conversion_rate": 0.05,
        "value_per_conversion_nzd": 150,
        "contribution_margin": 0.6,
        "hourly_rate_nzd": 120,
        "horizon_months": 12,
        "segments": {"all": 1},
        "impacts": {
            "missing_title": {
                "relative_conversion_loss": {"low": 0.1, "high": 0.18},
                "recovery_fraction": {"low": 0.5, "high": 1},
                "fix_hours": {"low": 1, "high": 2},
                "source": "Hypothetical fixture only, not industry data",
                "rationale": "Sensitivity test",
                "reviewed_by": "Fixture reviewer",
            }
        },
    }


def defect(key="missing_title", identity="finding-a"):
    return {
        "finding_id": identity,
        "defect_key": key,
        "defect": "Missing title",
        "source_url": "https://example.com/",
        "severity": "high",
        "check": "page",
    }


def report(identity="current", timestamp="2026-08-15T12:00:00+00:00", findings=None, **kwargs):
    value = {
        "schema_version": 2,
        "run_id": identity,
        "url": "https://example.com/",
        "timestamp": timestamp,
        "profile": "static",
        "status": "complete",
        "health_score": 84,
        "defects": [defect()] if findings is None else findings,
        "checks": {"page": {"status": "ok"}},
        "artifacts": {},
    }
    value.update(kwargs)
    return value


def config():
    return validate_config(
        {
            "agency": {"name": "Fixture Agency"},
            "contact": {"email": "agency@example.com"},
            "clients": [
                {
                    "id": "one",
                    "url": "https://example.com/",
                    "name": "Example Client",
                    "email": "client@example.com",
                    "profile": "static",
                    "revenue": assumption(),
                }
            ],
        }
    )


def seed(root):
    history = History(root)
    history.save(report("prior", "2026-07-20T12:00:00+00:00", health_score=70))
    history.save(report())
    return history


def test_financial_math_corrects_missing_conversion_rate():
    result = calculate_revenue(report(), assumption())
    assert result["baseline_nzd_monthly"] == "15000.00"
    assert result["revenue_at_risk_nzd_monthly"] == {"low": "1500.00", "high": "2700.00"}
    assert result["potential_recovery_nzd_monthly"] == {"low": "750.00", "high": "2700.00"}
    assert result["fix_cost_nzd"] == {"low": "120.00", "high": "240.00"}
    assert result["profit_roi_percent"]["low"] == "2150.00"
    assert result["payback_months"]["low"] == "0.53"
    assert "Scenario only" in result["disclaimer"]


def test_duplicates_and_overlapping_effects_are_not_summed():
    inputs = assumption()
    inputs["impacts"]["missing_description"] = copy.deepcopy(inputs["impacts"]["missing_title"])
    result = calculate_revenue(
        report(findings=[defect(), defect(), defect("missing_description", "b")]), inputs
    )
    assert len(result["rows"]) == 2
    assert result["revenue_at_risk_nzd_monthly"]["high"] == "2700.00"
    assert result["fix_cost_nzd"]["high"] == "480.00"


def test_disjoint_segments_and_caps():
    inputs = assumption()
    inputs["segments"] = {"mobile": 0.6, "desktop": 0.4}
    inputs["impacts"]["missing_title"]["segment"] = "mobile"
    result = calculate_revenue(report(), inputs)
    assert result["revenue_at_risk_nzd_monthly"]["high"] == "1620.00"
    inputs["segments"]["desktop"] = 0.5
    with pytest.raises(ValueError, match="100%"):
        calculate_revenue(report(), inputs)


def test_no_defaults_unknown_defects_and_zero_values():
    assert calculate_revenue(report())["revenue_at_risk_nzd_monthly"] is None
    inputs = assumption()
    assert (
        calculate_revenue(report(findings=[defect("unknown")]), inputs)["status"] == "unquantified"
    )
    inputs["monthly_visitors"] = 0
    zero = calculate_revenue(report(), inputs)
    assert zero["revenue_at_risk_nzd_monthly"]["high"] == "0.00"
    assert zero["payback_months"]["high"] is None
    inputs["hourly_rate_nzd"] = 0
    assert calculate_revenue(report(), inputs)["profit_roi_percent"]["high"] is None


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_bad_financial_inputs(value):
    inputs = assumption()
    inputs["monthly_visitors"] = value
    with pytest.raises(ValueError):
        calculate_revenue(report(), inputs)


def test_no_unreviewed_or_invalid_loss_rates():
    inputs = assumption()
    inputs["impacts"]["missing_title"]["relative_conversion_loss"]["high"] = 1.5
    with pytest.raises(ValueError):
        calculate_revenue(report(), inputs)
    inputs = assumption()
    del inputs["impacts"]["missing_title"]["source"]
    with pytest.raises(ValueError, match="source"):
        calculate_revenue(report(), inputs)


def test_csv_formula_is_escaped():
    d = defect()
    d["defect"] = '=IMPORTXML("evil")'
    assert "'=IMPORTXML" in roi_csv(calculate_revenue(report(findings=[d]), assumption()))


def test_expiring_tls_has_no_automatic_loss():
    value = calculate_revenue(report(findings=[defect("tls-expiry")]), assumption())
    assert value["status"] == "unquantified"
    assert value["rows"][0]["risk_nzd_monthly"] is None


def test_monthly_complete_records_pdf_fallback_and_idempotency(tmp_path, monkeypatch):
    seed(tmp_path)
    cfg = config()
    first = generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False)
    second = generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False)
    assert first["id"] == second["id"]
    assert first["health_delta"] == 14
    assert first["delivery"] == {"status": "draft", "sent": False}
    message = BytesParser(policy=policy.default).parsebytes(
        Path(first["artifacts"]["email"]).read_bytes()
    )
    assert message["To"] == "client@example.com"
    assert message["X-Unsent"] == "1"
    assert len(list(message.iter_attachments())) == 1
    monkeypatch.setattr(
        "auditor_toolkit.monthly.export_pdf",
        lambda *a: (_ for _ in ()).throw(ImportError("no Playwright")),
    )
    failed = generate_monthly(tmp_path, cfg, "one", "2026-08")
    assert failed["status"] == "partial" and failed["pdf"]["status"] == "error"
    assert "pdf" not in failed["artifacts"]
    assert Path(failed["artifacts"]["html"]).exists()
    assert len(MonthlyStore(tmp_path).list()) == 2


def test_latest_partial_not_hidden_and_other_clients_excluded(tmp_path):
    history = seed(tmp_path)
    history.save(report("bad", "2026-08-31T01:00:00+00:00", status="partial", health_score=None))
    history.save(report("other", "2026-08-31T02:00:00+00:00", url="https://other.example/"))
    data = collect_month(history, config()["clients"][0], "2026-08", "Pacific/Auckland")
    assert data["current"]["run_id"] == "bad"
    assert data["health_delta"] is None
    assert "other" not in data["source_run_ids"]
    no_audit = generate_monthly(tmp_path, config(), "one", "2026-06", pdf=False)
    assert no_audit["data_status"] == "no_audit"
    assert no_audit["revenue"]["revenue_at_risk_nzd_monthly"] is None


def test_month_boundary_nz_and_verified_work_only(tmp_path):
    history = seed(tmp_path)
    history.save(report("fixed", "2026-08-20T12:00:00+00:00", findings=[], health_score=100))
    history.transition("finding-a", "verified", {"verification_run": "fixed"})
    with history.connect() as db:
        # Sep 1 in NZ; must NOT count as August work.
        db.execute("UPDATE events SET timestamp='2026-08-31 13:00:00'")
    data = collect_month(history, config()["clients"][0], "2026-08", "Pacific/Auckland")
    assert data["fixes_verified"] == []
    with history.connect() as db:
        db.execute("UPDATE events SET timestamp='2026-08-20 13:00:00'")
    data = collect_month(history, config()["clients"][0], "2026-08", "Pacific/Auckland")
    assert len(data["fixes_verified"]) == 1
    assert data["fixes_verified"][0]["verification_run"] == "fixed"


def test_no_network_delivery_even_with_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Must not send"))
    )
    from website_auditor.reporting.email_sender import send_report_email

    result = send_report_email(
        "client@example.com",
        "Report",
        "Review this",
        smtp_config={"smtp_host": "live", "smtp_user": "u", "smtp_password": "p"},
    )
    assert result["status"] == "draft" and not result["sent"]


def test_branding_injection_and_email_validation(tmp_path):
    cfg = config()
    cfg["agency"]["name"] = "<script>alert(1)</script>"
    seed(tmp_path)
    result = generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False)
    assert "<script>alert(1)</script>" not in Path(result["artifacts"]["html"]).read_text()
    cfg["agency"]["primary_color"] = "red; background:url(https://evil)"
    with pytest.raises(ValueError):
        validate_config(cfg)
    cfg = config()
    cfg["clients"][0]["email"] = "one@example.com\nBcc:evil@example.com"
    with pytest.raises(ValueError):
        validate_config(cfg)


def test_monthly_policy_cancellation_and_watchdog_preview(tmp_path):
    seed(tmp_path)
    cfg = config()
    jobs = due_monthly(tmp_path, cfg, datetime(2026, 8, 31, 12, tzinfo=timezone.utc))
    assert jobs[0]["month"] == "2026-08" and jobs[0]["mode"] == "draft"
    assert due_monthly(tmp_path, cfg, datetime(2026, 9, 3, tzinfo=timezone.utc)) == []
    blocked = SimpleNamespace(
        evaluate=lambda *a, **k: SimpleNamespace(allowed=False, reason="Policy disabled")
    )
    assert (
        generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False, policy=blocked)["status"]
        == "blocked"
    )
    result = generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False)
    assert result["status"] == "ready"
    assert due_monthly(tmp_path, cfg, datetime(2026, 8, 31, 12, tzinfo=timezone.utc)) == []
    (tmp_path / "monthly/CANCELLED").write_text("stop")
    assert generate_monthly(tmp_path, cfg, "one", "2026-08", pdf=False)["status"] == "blocked"


def test_monthly_artifact_allowlist_and_integrity(tmp_path):
    seed(tmp_path)
    result = generate_monthly(tmp_path, config(), "one", "2026-08", pdf=False)
    store = MonthlyStore(tmp_path)
    assert store.artifact(result["id"], "html").exists()
    with pytest.raises(KeyError):
        store.artifact(result["id"], "../../portal-auth.json")
    Path(result["artifacts"]["html"]).write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        store.artifact(result["id"], "html")


def test_cli_config_and_wrong_client(tmp_path, capsys):
    seed(tmp_path)
    path = tmp_path / "agency.json"
    path.write_text(json.dumps(config()))
    assert load_config(path)["clients"][0]["id"] == "one"
    assert (
        main(
            [
                "monthly",
                "--config",
                str(path),
                "--client",
                "one",
                "--month",
                "2026-08",
                "--html-only",
                "--output-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)[0]["status"] == "ready"
    rpath = tmp_path / "audit.json"
    rpath.write_text(json.dumps(report(url="https://different.example/")))
    with pytest.raises(SystemExit):
        main(["revenue", str(rpath), "--config", str(path), "--client", "one"])


def test_root_url_without_trailing_slash_is_same_client(tmp_path):
    history = History(tmp_path)
    history.save(report(url="https://example.com"))
    data = collect_month(history, config()["clients"][0], "2026-08", "Pacific/Auckland")
    assert data["current"]["run_id"] == "current"


def test_delivery_cannot_be_enabled_by_config():
    cfg = config()
    cfg["reporting"]["auto_send"] = True
    with pytest.raises(ValueError, match="drafts only"):
        validate_config(cfg)
