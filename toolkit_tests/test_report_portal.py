import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("argon2")
from fastapi.testclient import TestClient  # noqa: E402

from auditor_toolkit.portal import create_app, setup_password  # noqa: E402
from scripts.pipeline_store import PipelineStore  # noqa: E402
from scripts.report_archive import EncryptedReportArchive, import_ciphertext  # noqa: E402
from toolkit_tests.test_report_archive import envelope  # noqa: E402

PASSWORD = "synthetic-archive-owner-password"


@pytest.fixture
def owner_archive():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive_root = root / "sealed"
        archive_root.mkdir(mode=0o700)
        archive = EncryptedReportArchive(archive_root)
        store = PipelineStore(root / "pipeline.sqlite3")
        prospect_id = hashlib.sha256(b"example.com").hexdigest()
        audit_id = hashlib.sha256(b"archive-fixture-audit").hexdigest()
        now = datetime.now(timezone.utc)
        with store.transaction(bootstrap=True) as state:
            state["prospects"][prospect_id] = {"domain": "example.com", "status": "complete", "draft": None}
            state["audit_runs"] = [{"audit_id": audit_id, "prospect_id": prospect_id, "status": "complete",
                                    "canonical_run_id": "canonical-archive-fixture",
                                    "execution_timestamp": now.isoformat()}]
        data = envelope()
        source = root / "download.enc.json"
        source.write_bytes(data)
        identity = import_ciphertext(
            store, archive, source, expected_sha256=hashlib.sha256(data).hexdigest(), audit_ids=[audit_id],
            source_run_id="123", source_artifact_id="456", created_at=now.isoformat(),
            source_expires_at=(now + timedelta(days=30)).isoformat(),
            retain_until=(now + timedelta(days=60)).isoformat(), owner_reviewed=True,
            actor="fixture-owner", reason="Synthetic archive reviewed", now=now.timestamp(),
        )
        history = root / "history"
        setup_password(history, PASSWORD)
        app = create_app(history, pipeline_db=store.path, report_archive_root=archive_root)
        with TestClient(app) as client:
            yield client, store, archive, identity, prospect_id, history


def login(client):
    assert client.post("/login", data={"password": PASSWORD}, follow_redirects=False).status_code == 303


def test_report_pages_and_ciphertext_require_owner_authentication(owner_archive):
    client, _, _, identity, _, _ = owner_archive
    for path in ("/pipeline/reports", f"/pipeline/reports/{identity}/ciphertext"):
        result = client.get(path)
        assert result.status_code == 401
        assert identity not in result.text


def test_owner_downloads_only_verified_ciphertext_and_views_do_not_change_state(owner_archive):
    client, store, _, identity, prospect_id, _ = owner_archive
    login(client)
    before = store.read()
    page = client.get("/pipeline/reports", params={"prospect": prospect_id})
    assert page.status_code == 200
    assert "AVAILABLE" in page.text
    assert "envelope_and_checksum_only" in page.text
    assert "https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/123/artifacts/456" in page.text
    assert 'name="viewport"' in page.text
    response = client.get(f"/pipeline/reports/{identity}/ciphertext")
    assert response.status_code == 200
    assert response.content == envelope()
    assert hashlib.sha256(response.content).hexdigest() == identity
    assert response.headers["content-type"] == "application/octet-stream"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/pipeline/reports", params={"prospect": "<script>"}).status_code == 400
    assert client.get("/pipeline/reports?offset=-1").status_code == 400
    assert client.get("/pipeline/reports/not-a-hash/ciphertext").status_code == 404
    assert store.read() == before
    assert "<script>" not in page.text


def test_expired_corrupt_missing_and_unconfigured_downloads_fail_closed(owner_archive, monkeypatch):
    client, store, archive, identity, _, history = owner_archive
    login(client)
    path = f"/pipeline/reports/{identity}/ciphertext"
    archive.path(identity).write_bytes(envelope() + b" ")
    assert client.get(path).status_code == 409
    archive.path(identity).unlink()
    assert client.get(path).status_code == 404
    archive.put(envelope())
    with TestClient(create_app(history, pipeline_db=store.path)) as unconfigured:
        login(unconfigured)
        assert unconfigured.get(path).status_code == 503
    from auditor_toolkit import report_portal

    future = datetime.now(timezone.utc) + timedelta(days=61)
    monkeypatch.setattr(report_portal.time, "time", lambda: future.timestamp())
    # Existing session expires in this clock jump; log in again before checking retention.
    login(client)
    assert client.get(path).status_code == 410
    assert archive.path(identity).is_file()


def test_download_rate_limit_and_invalid_archive_configuration(owner_archive):
    client, _, archive, identity, _, history = owner_archive
    login(client)
    path = f"/pipeline/reports/{identity}/ciphertext"
    for _ in range(10):
        assert client.get(path).status_code == 200
    assert client.get(path).status_code == 429
    # Test that invalid archive configuration (non-existent directory) raises ValueError
    with pytest.raises(ValueError):
        create_app(history, report_archive_root=history / "nonexistent_archive")
    # Test that archive with wrong permissions raises ValueError
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bad_archive = Path(tmp) / "bad_archive"
        bad_archive.mkdir(mode=0o755)  # Wrong permissions (not 0700)
        with pytest.raises(ValueError):
            create_app(history, report_archive_root=bad_archive)
