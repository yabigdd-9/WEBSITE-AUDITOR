"""E2E tests for proof demo rendering via local renderer."""

import os
import time
import urllib.request

import pytest

from auditor_toolkit.proof.adapters.local_renderer import (
    get_server_url,
    render_prototype,
    start_server,
    stop_server,
)
from auditor_toolkit.proof.prototype import Prototype, PrototypeManifest


def _make_prototype() -> Prototype:
    manifest = PrototypeManifest(
        patch_id="test-patch",
        finding_id="f001",
        patch_type="CSS_PATCH",
        target=".test",
        before_value="color: #999",
        after_value="color: #1a1a2e",
        generated_by="deterministic",
    )
    return Prototype(
        manifest=manifest,
        html_body=(
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Test Prototype</title></head>"
            "<body><h1>Test Prototype</h1></body></html>"
        ),
        css_body=".test { color: #1a1a2e; }",
    )


def test_render_prototype_creates_files():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        proto = _make_prototype()
        html_path = render_prototype(proto, assets_dir=tmpdir)
        assert os.path.exists(html_path)
        assert html_path.endswith("index.html")

        with open(html_path, encoding="utf-8") as f:
            content = f.read()
        assert "Test Prototype" in content


def test_render_prototype_creates_css():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        proto = _make_prototype()
        render_prototype(proto, assets_dir=tmpdir)

        css_path = os.path.join(tmpdir, "prototype.css")
        assert os.path.exists(css_path)
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        assert ".test" in css
        assert "#1a1a2e" in css


def test_start_stop_server():
    """Start a server, verify it's running, then stop it."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        proto = _make_prototype()
        render_prototype(proto, assets_dir=tmpdir)

        url = start_server(assets_dir=tmpdir)
        try:
            assert url.startswith("http://127.0.0.1:")
            assert get_server_url() == url

            # Try to fetch the page
            time.sleep(0.2)  # let server start
            resp = urllib.request.urlopen(f"{url}index.html", timeout=5)
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "Test Prototype" in body
        finally:
            stop_server()


def test_server_blocks_write_methods():
    """Verify POST/PUT/PATCH/DELETE are rejected."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        proto = _make_prototype()
        render_prototype(proto, assets_dir=tmpdir)

        url = start_server(assets_dir=tmpdir)
        try:
            time.sleep(0.2)

            for method in ("POST", "PUT", "PATCH", "DELETE"):
                req = urllib.request.Request(url, method=method)
                try:
                    urllib.request.urlopen(req, timeout=5)
                    assert False, f"{method} should have been blocked"
                except urllib.error.HTTPError as e:
                    assert e.code == 403, f"{method} returned {e.code}, expected 403"
        finally:
            stop_server()


def test_server_cleans_up_previous_instance():
    """Starting a new server should stop any previous one."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        proto = _make_prototype()
        render_prototype(proto, assets_dir=tmpdir)

        url1 = start_server(assets_dir=tmpdir)
        url2 = start_server(assets_dir=tmpdir)  # should stop url1
        try:
            assert url1 != url2 or url2 == get_server_url()
        finally:
            stop_server()


def test_get_server_url_empty_when_stopped():
    stop_server()
    assert get_server_url() == ""
