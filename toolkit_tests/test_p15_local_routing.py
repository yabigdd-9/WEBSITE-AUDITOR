import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "money-machine"))

import mm_model_router as router


@pytest.mark.parametrize("base", [
    "https://api.example.com",
    "http://192.168.1.1",
    "http://127.0.0.1@evil.example",
    "file:///tmp/model",
    "http://127.0.0.1/?redirect=remote",
])
def test_fcc_rejects_non_loopback_endpoint_before_prompt_send(base):
    with patch.object(router, "FCC_BASE", base), patch.object(
        router.urllib.request, "build_opener"
    ) as send:
        with pytest.raises(router.BlockedCost):
            router._fcc_complete(
                "synthetic public prompt",
                "fixture/claude:free",
                max_tokens=16,
                timeout=2,
            )
    send.assert_not_called()


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:8082", "http://127.0.0.1:8082"),
    ("http://localhost:8082", "http://127.0.0.1:8082"),
    ("http://[::1]:8082", "http://[::1]:8082"),
])
def test_fcc_endpoint_accepts_loopback_only(url, expected):
    assert router._loopback_url(url) == expected


def test_fcc_redirect_refused():
    handler = router.LocalRedirectRefused()
    with pytest.raises(router.BlockedCost, match="redirects"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://remote.example")


def test_probe_fcc_requires_explicit_model():
    with patch.object(router, "_env_value", return_value=""), patch.object(
        router, "_open_local"
    ) as open_local:
        assert router.probe_fcc() is None
    open_local.assert_not_called()


def test_routes_report_hides_unusable_configured_fcc_model():
    with patch.object(router, "probe_fcc", return_value=None), patch.object(
        router, "_env_value", return_value="stale/configured:free"
    ):
        report = router.routes_report()
    for routes in report["routes"].values():
        assert routes[0]["model"] is None


def test_active_routes_are_fcc_then_hermes_only():
    report = router.routes_report()
    assert report["policy"]["primary"] == "CLAUDE_VIA_FCC"
    assert report["policy"]["fallback"] == "HERMES_VERIFIED_FREE_THEN_DEFER"
    assert report["policy"]["llamacpp_enabled"] is False
    assert report["policy"]["ollama_enabled"] is False
    for routes in report["routes"].values():
        assert [item["provider"] for item in routes] == [
            router.FCC_PROVIDER,
            router.HERMES_PROVIDER,
        ]
