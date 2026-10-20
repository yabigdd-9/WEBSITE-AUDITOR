"""Actual repository entry points fail closed without dispatching a provider."""

import importlib.util
import json
import sys
from pathlib import Path

import mm_financial_admission as admission
import mm_model_router as router
import pytest

from toolkit_tests.financial_admission_fixtures import fixture_coordinator


def load_script(name):
    path = Path(__file__).parent / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("financial_dispatch_" + name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dispatcher():
    return load_script("free_role_router")


@pytest.fixture
def denied(tmp_path, monkeypatch):
    coordinator = admission.Coordinator(tmp_path / "no-account-evidence")
    monkeypatch.setattr(admission, "get_coordinator", lambda: coordinator)
    monkeypatch.setenv("MM_ROOT", str(tmp_path / "worker-runtime"))
    monkeypatch.setenv("HERMES_ALLOW_HOSTED_LLM", "1")
    monkeypatch.setenv("HERMES_ALLOW_PAID_FALLBACK", "1")
    return coordinator


def test_money_fcc_free_suffix_does_not_bypass_missing_account_evidence(denied, monkeypatch):
    monkeypatch.setattr(router, "_open_local", lambda *a: pytest.fail("FCC dispatched"))
    with pytest.raises(router.BlockedCost, match="financial admission"):
        router._fcc_complete("synthetic", "fixture:free", 64, 2)
    assert not denied.directory.exists()


def test_money_hermes_missing_evidence_precedes_subprocess(denied, monkeypatch):
    monkeypatch.setattr(router, "probe_hermes", lambda purpose: "fixture:free")
    monkeypatch.setattr(router.subprocess, "run", lambda *a, **kw: pytest.fail("Hermes dispatched"))
    with pytest.raises(router.BlockedCost, match="financial admission"):
        router._hermes_complete("synthetic", "researcher", 2)


def test_free_role_custom_transport_cannot_bypass_default_denial(dispatcher, denied):
    import yaml
    config = yaml.safe_load((dispatcher.ROOT / "money-machine/config/routing.yaml").read_text())
    slug = config["roles"]["RESEARCHER"]["preferred"]
    catalog = {slug: {"id": slug, "pricing": {"prompt": "0", "completion": "0"}}}
    with pytest.raises(dispatcher.RouteError, match="financial admission"):
        dispatcher.route(config, "RESEARCHER", "synthetic", "synthetic-key", catalog,
                         lambda *a: pytest.fail("custom transport dispatched"))


def test_public_free_role_http_helper_is_admitted(dispatcher, denied, monkeypatch):
    monkeypatch.setattr(dispatcher, "_http_request", lambda *a: pytest.fail("provider HTTP dispatched"))
    with pytest.raises(dispatcher.RouteError):
        dispatcher.request("/chat/completions", "synthetic-key", {"model": "fixture:free", "max_tokens": 16})
    with pytest.raises(dispatcher.RouteError):
        dispatcher.request("/models")


def test_free_role_cli_does_not_read_credentials_or_catalog_when_held(dispatcher, denied, tmp_path, monkeypatch):
    import shutil
    config = tmp_path / "money-machine/config/routing.yaml"
    config.parent.mkdir(parents=True)
    shutil.copyfile(dispatcher.ROOT / "money-machine/config/routing.yaml", config)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("synthetic")
    monkeypatch.setattr(dispatcher, "ROOT", tmp_path)
    monkeypatch.setattr(dispatcher, "credential", lambda: pytest.fail("credential read"))
    monkeypatch.setattr(dispatcher, "_http_request", lambda *a: pytest.fail("external catalog request"))
    monkeypatch.setattr(sys, "argv", ["free_role_router", "--role", "RESEARCHER", "--prompt-file", str(prompt)])
    assert dispatcher.main() == 2


def test_direct_bridge_has_no_cli_or_http_bypass(denied, monkeypatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8082")
    monkeypatch.setenv("MODEL", "fixture:free")
    bridge = load_script("fcc-bridge")
    monkeypatch.setattr(router, "_open_local", lambda *a: pytest.fail("FCC dispatched"))
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: pytest.fail("CLI dispatched"))
    assert bridge.run_claude("synthetic") is False
    assert bridge.run_codex("synthetic") is False
    monkeypatch.setattr(bridge, "run_claude", lambda *a: pytest.fail("fallback invoked"))
    assert bridge.send_to_fcc("synthetic") is False
    assert bridge.start_fcc_server() is False
    assert bridge.stop_fcc_server() is False


def test_external_transport_refuses_redirects_and_proxies(dispatcher, monkeypatch):
    import io
    import urllib.error
    import urllib.request
    request = urllib.request.Request(dispatcher.API + "/chat/completions")
    with pytest.raises(urllib.error.HTTPError):
        dispatcher.NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://other.invalid/")

    class Response(io.BytesIO):
        status = 200

    class Opener:
        def open(self, request, timeout):
            assert timeout == 100
            return Response(b'{"data":[]}')

    def build(*handlers):
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], dispatcher.NoRedirect)
        return Opener()

    monkeypatch.setattr(dispatcher.urllib.request, "build_opener", build)
    assert dispatcher._http_request("/models") == (200, {"data": []})


def test_shared_stop_survives_separate_worker_runtime_roots(tmp_path, monkeypatch):
    coordinator = fixture_coordinator(tmp_path / "financial")
    monkeypatch.setattr(admission, "get_coordinator", lambda: coordinator)
    monkeypatch.setenv("MM_ROOT", str(tmp_path / "runtime-one"))
    monkeypatch.setattr(router, "_open_local", lambda *a: (_ for _ in ()).throw(TimeoutError("synthetic")))
    with pytest.raises(router.CostSafetyStop):
        router._fcc_complete("synthetic", "fixture:free", 64, 2)
    monkeypatch.setenv("MM_ROOT", str(tmp_path / "runtime-two"))
    monkeypatch.setattr(router, "_open_local", lambda *a: pytest.fail("new MM_ROOT bypassed global stop"))
    with pytest.raises(router.CostSafetyStop):
        router._fcc_complete("synthetic", "fixture:free", 64, 2)
    assert json.loads((tmp_path / "runtime-two/state/model-routing-cost-stop.json").read_text())["reason"] == "dispatch_outcome_unknown"
