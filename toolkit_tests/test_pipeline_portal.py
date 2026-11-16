import copy
import hashlib
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("argon2")
from fastapi.testclient import TestClient  # noqa: E402

from auditor_toolkit.portal import create_app, setup_password  # noqa: E402
from scripts import cloud_opportunities as opportunities  # noqa: E402
from scripts.pipeline_store import PipelineStore  # noqa: E402

PASSWORD = "synthetic-owner-password-only"


@pytest.fixture
def owner():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = PipelineStore(root / "pipeline.sqlite3")
        identity = hashlib.sha256(b"example.com").hexdigest()
        with store.transaction(bootstrap=True) as state:
            state["prospects"][identity] = dict(
                domain="example.com", status="complete", draft="INTERNAL SCOPE DRAFT - DO NOT SEND",
                discovery={"business_name": "<script>fixture</script>"},
                audit=dict(
                    domain="example.com", status="COMPLETE", run_id="fixture-1",
                    timestamp="2026-01-01T00:00:00Z", findings=[dict(
                        finding_id="finding-1", defect_key="viewport", severity="medium", confidence="observed",
                        observed="Observed fixture", remediation_action="Review viewport", source_url="https://example.com",
                        evidence_ref="html", evidence_check="html", evidence_check_status="ok",
                    )],
                ),
            )
            opportunities.enrich(state, opportunities.load_policy(Path(__file__).resolve().parents[1]), now=1767225600)
        history = root / "history"
        setup_password(history, PASSWORD)
        with TestClient(create_app(history, pipeline_db=store.path)) as client:
            yield client, store, identity, history


def login(client):
    result = client.post("/login", data={"password": PASSWORD}, follow_redirects=False)
    assert result.status_code == 303
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "SameSite=strict" in result.headers["set-cookie"]
    return client.get("/api/session").json()["csrf"]


def test_pipeline_requires_owner_session_everywhere(owner):
    client, store, identity, _ = owner
    for path in ("/pipeline", "/pipeline/prospects", f"/pipeline/prospects/{identity}",
                 "/pipeline/discovery", "/pipeline/health"):
        response = client.get(path)
        assert response.status_code == 401
        assert "example.com" not in response.text
    assert client.post(f"/pipeline/prospects/{identity}/reject", json={}).status_code == 401
    assert store.read()["prospects"][identity]["proposal_version"]


def test_owner_can_review_private_records_without_mutation_or_script_execution(owner):
    client, store, identity, _ = owner
    login(client)
    before = copy.deepcopy(store.read())
    for path in ("/pipeline", "/pipeline/prospects", f"/pipeline/prospects/{identity}",
                 "/pipeline/discovery", "/pipeline/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'name="viewport"' in response.text
        assert response.headers["cache-control"] == "no-store"
        assert "script-src 'none'" in response.headers["content-security-policy"]
        assert "<script>fixture</script>" not in response.text
    assert "&lt;script&gt;fixture&lt;/script&gt;" in client.get(f"/pipeline/prospects/{identity}").text
    assert "Pricing not configured" in client.get(f"/pipeline/prospects/{identity}").text
    assert "&lt;script&gt;" in client.get("/pipeline/prospects", params={"q": "<script>"}).text
    assert client.get("/pipeline/prospects?offset=-1").status_code == 400
    assert client.get("/pipeline/prospects/not-a-hash").status_code == 404
    assert client.get(f"/pipeline/prospects/{identity}/reject").status_code == 405
    assert store.read() == before
    with store.transaction():
        assert client.get("/pipeline").status_code == 200


def test_reject_requires_csrf_exact_version_and_origin(owner):
    client, store, identity, _ = owner
    token = login(client)
    path = f"/pipeline/prospects/{identity}/reject"
    version = store.read()["prospects"][identity]["proposal_version"]
    data = {"version": version, "reason": "Outside supported capabilities"}
    assert client.post(path, json=data).status_code == 403
    assert client.post(path, json={**data, "csrf": "é"}).status_code == 403
    assert client.post(path, json={**data, "csrf": token}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post(path, json={**data, "csrf": token, "version": "0" * 64}).status_code == 409
    assert client.post(path, json={**data, "csrf": token, "actor": "owner"}).status_code == 400
    assert client.post(path, json={**data, "csrf": token, "reason": ""}).status_code == 400
    assert store.read()["prospects"][identity]["proposal_version"] == version
    response = client.post(path, data={**data, "csrf": token}, follow_redirects=False)
    assert response.status_code == 303
    saved = store.read()["prospects"][identity]
    assert saved["proposal_version"] is None
    assert saved["opportunity"]["status"] == "owner_rejected"
    assert saved["recommendation_reviews"][0]["reason"] == data["reason"]
    assert client.post(path, json={**data, "csrf": token}).status_code == 409


def test_review_size_rate_and_session_controls(owner):
    client, store, identity, history = owner
    token = login(client)
    path = f"/pipeline/prospects/{identity}/reject"
    assert client.post(path, content=b"x" * 4097, headers={"content-type": "application/json"}).status_code == 413
    for _ in range(20):
        assert client.post(path, json={"version": "stale", "reason": "fixture", "csrf": token}).status_code == 409
    assert client.post(path, json={"version": "stale", "reason": "fixture", "csrf": token}).status_code == 429
    with TestClient(create_app(history, session_seconds=-1, pipeline_db=store.path)) as expired:
        expired.post("/login", data={"password": PASSWORD}, follow_redirects=False)
        assert expired.get("/pipeline").status_code == 401


def test_dashboard_refuses_missing_or_public_database(owner):
    _, store, _, history = owner
    with pytest.raises(ValueError):
        create_app(history, pipeline_db=store.path.with_name("missing.sqlite3"))
    store.path.chmod(0o644)
    with pytest.raises(ValueError):
        create_app(history, pipeline_db=store.path)


def test_cli_pipeline_option_is_explicit():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "auditor_toolkit.cli", "dashboard", "--help"],
                            check=True, capture_output=True, text=True)
    assert "--pipeline-db" in result.stdout
