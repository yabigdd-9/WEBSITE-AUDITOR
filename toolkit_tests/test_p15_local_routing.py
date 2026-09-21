import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "money-machine"))

import mm_model_router as router


@pytest.mark.parametrize("base", [
    "https://api.example.com", "http://192.168.1.1", "http://127.0.0.1@evil.example",
    "file:///tmp/model", "http://127.0.0.1/?redirect=remote",
])
def test_local_completion_rejects_non_loopback_endpoint_before_prompt_send(base):
    with patch.object(router, "LLAMACPP_BASE", base), patch.object(router.urllib.request, "urlopen") as send:
        with pytest.raises(router.BlockedCost):
            router.local_complete("synthetic private prompt", lookup=lambda kind: "fixture")
    send.assert_not_called()


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("http://localhost:11434", "http://127.0.0.1:11434"),
    ("http://[::1]:8080", "http://[::1]:8080"),
])
def test_local_endpoint_accepts_loopback_only(url, expected):
    assert router._loopback_url(url) == expected


def test_local_redirect_refused():
    handler = router.LocalRedirectRefused()
    with pytest.raises(router.BlockedCost, match="redirects"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://remote.example")
