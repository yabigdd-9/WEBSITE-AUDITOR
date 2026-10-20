"""Screenshot subprocess inputs, evidence cache and truthful completion."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def screenshot(tmp_path, monkeypatch):
    specification = importlib.util.spec_from_file_location(
        "synthetic_screenshot", Path(__file__).with_name("screenshot_worker.py")
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "SCREENSHOT_DIR", tmp_path / "screenshots")
    monkeypatch.setattr(module, "MANIFEST_PATH", tmp_path / "screenshots/manifest.json")
    monkeypatch.setattr(module, "get_pending_businesses", lambda limit: [
        {"id": 1, "name": "Synthetic fixture", "public_website": "https://fixture.example"}
    ])
    return module


def test_untrusted_url_is_data_not_executable_python(screenshot, monkeypatch, tmp_path):
    malicious_url = "https://fixture.example/';raise RuntimeError('injected');#"
    captured = []

    def run(command, **kwargs):
        captured.append(command)
        return SimpleNamespace(returncode=0, stdout='{"status":"ok"}', stderr="")

    monkeypatch.setattr(screenshot.subprocess, "run", run)
    screenshot.capture_with_browser_toolkit(malicious_url, tmp_path / "quoted'path")
    command = captured[0]
    assert command[4] == malicious_url
    assert malicious_url not in command[2]
    compile(command[2], "<worker>", "exec")


@pytest.mark.parametrize("code,stdout", [(1, '{"status":"ok"}'),
                                        (0, '{"status":"error"}'), (0, "invalid")])
def test_failed_capture_is_nonzero_even_when_old_png_exists(screenshot, monkeypatch, code, stdout):
    folder = screenshot.SCREENSHOT_DIR / "business-1"
    folder.mkdir(parents=True)
    (folder / "old.png").write_bytes(b"synthetic old artifact")
    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", lambda *args: (code, stdout, ""))
    assert screenshot.main() == 1
    report = json.loads((screenshot.SCREENSHOT_DIR / "screenshot_report.json").read_text())
    assert report["screenshots_failed"] == 1
    assert report["screenshots_captured"] == 0


def test_verified_cached_hash_and_url_avoid_duplicate_capture(screenshot, monkeypatch):
    folder = screenshot.SCREENSHOT_DIR / "business-1"
    folder.mkdir(parents=True)
    artifact = folder / "fixture.png"
    artifact.write_bytes(b"synthetic fixture image")
    manifest = {"screenshots": [{"business_id": 1, "url": "https://fixture.example",
                                "path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
    screenshot.MANIFEST_PATH.write_text(json.dumps(manifest))
    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", lambda *args: pytest.fail("duplicate"))
    assert screenshot.main() == 0


def test_tampered_cached_artifact_requires_new_capture(screenshot, monkeypatch):
    folder = screenshot.SCREENSHOT_DIR / "business-1"
    folder.mkdir(parents=True)
    artifact = folder / "fixture.png"
    artifact.write_bytes(b"tampered")
    screenshot.MANIFEST_PATH.write_text(json.dumps({"screenshots": [{
        "business_id": 1, "url": "https://fixture.example", "path": str(artifact), "sha256": "bad"
    }]}))
    calls = []
    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", lambda *args:
                        (calls.append(args) or 1, '{"status":"error"}', ""))
    assert screenshot.main() == 1
    assert len(calls) == 1


@pytest.mark.parametrize("artifact_kind", ["old", "empty", "symlink", "missing"])
def test_success_status_cannot_adopt_an_old_or_invalid_artifact(
    screenshot, monkeypatch, artifact_kind
):
    folder = screenshot.SCREENSHOT_DIR / "business-1"
    folder.mkdir(parents=True)
    old = folder / "old.png"
    old.write_bytes(b"old synthetic capture")

    def capture(url, attempt):
        artifact = old
        if artifact_kind == "empty":
            artifact = attempt / "empty.png"
            artifact.touch()
        elif artifact_kind == "symlink":
            artifact = attempt / "link.png"
            artifact.symlink_to(old)
        elif artifact_kind == "missing":
            return 0, json.dumps({"status": "ok"}), ""
        return 0, json.dumps({"status": "ok", "evidence": {"screenshot": str(artifact)}}), ""

    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", capture)
    assert screenshot.main() == 1
    assert screenshot.load_manifest()["screenshots"] == []


def test_new_reported_artifact_is_hashed_and_reused(screenshot, monkeypatch):
    def capture(url, attempt):
        artifact = attempt / "screenshot.png"
        artifact.write_bytes(b"fresh synthetic capture")
        return 0, json.dumps({"status": "ok", "evidence": {"screenshot": str(artifact)}}), ""

    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", capture)
    assert screenshot.main() == 0
    entry = screenshot.load_manifest()["screenshots"][0]
    assert entry["sha256"] == hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
    monkeypatch.setattr(screenshot, "capture_with_browser_toolkit", lambda *args: pytest.fail("duplicate"))
    assert screenshot.main() == 0
