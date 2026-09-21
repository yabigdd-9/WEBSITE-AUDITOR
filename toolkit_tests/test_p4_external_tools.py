import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from auditor_toolkit.external_tools import _binary, run_lighthouse, run_lychee


@pytest.fixture
def executable(tmp_path):
    binary = tmp_path / "audit-tool"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o700)
    return str(binary)


def test_lychee_success_and_broken_exit_codes(executable):
    ok = SimpleNamespace(returncode=0, stdout=json.dumps({"links": []}), stderr="")
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run", return_value=ok
    ) as run:
        findings, evidence = run_lychee("https://example.com")
    assert findings == []
    assert evidence["returncode"] == 0
    assert run.call_args.args[0][-1] == "https://example.com"
    assert run.call_args.args[0][0] == executable
    assert run.call_args.kwargs["shell"] is False

    broken = SimpleNamespace(returncode=2, stdout=json.dumps({"failures": ["https://example.com/nope"]}), stderr="")
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run", return_value=broken
    ):
        findings, evidence = run_lychee("https://example.com")
    assert [f.defect_key for f in findings] == ["lychee-broken-links"]
    assert evidence["returncode"] == 2


def test_lychee_runtime_failure_is_not_misreported_as_broken_link(executable):
    failed = SimpleNamespace(returncode=1, stdout="", stderr="bad config")
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run", return_value=failed
    ):
        with pytest.raises(RuntimeError, match="runtime/configuration"):
            run_lychee("https://example.com")


def test_lighthouse_scores_create_evidence_backed_findings(executable):
    payload = {
        "lighthouseVersion": "13.0.0",
        "fetchTime": "2026-09-21T00:00:00Z",
        "categories": {
            "performance": {"score": 0.42},
            "accessibility": {"score": 0.91},
            "best-practices": {"score": 0.75},
            "seo": {"score": 0.99},
        },
    }
    result = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run", return_value=result
    ):
        findings, evidence = run_lighthouse("https://example.com")
    keys = {f.defect_key for f in findings}
    assert keys == {"lighthouse-performance-low", "lighthouse-best-practices-low"}
    assert evidence["categories"]["performance"] == 42.0
    assert evidence["categories"]["accessibility"] == 91.0


def test_external_tools_missing_fails_closed_when_requested():
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="not installed"):
            run_lychee("https://example.com")
        with pytest.raises(RuntimeError, match="not installed"):
            run_lighthouse("https://example.com")


@pytest.mark.parametrize("runner", [run_lychee, run_lighthouse])
def test_external_tool_timeout_fails_as_runtime_error(executable, runner):
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["lychee"], 1),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            runner("https://example.com", timeout=1)


def test_unknown_executable_rejected_before_lookup():
    with patch("auditor_toolkit.external_tools.shutil.which") as lookup:
        with pytest.raises(ValueError, match="allow-listed"):
            _binary("sh")
    lookup.assert_not_called()


@pytest.mark.parametrize("name", ["lychee", "lighthouse"])
@pytest.mark.parametrize("invalid_kind", ["missing", "directory"])
def test_invalid_executable_rejected(tmp_path, name, invalid_kind):
    candidate = tmp_path / "missing" if invalid_kind == "missing" else tmp_path
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=str(candidate)), patch(
        "auditor_toolkit.external_tools.subprocess.run"
    ) as run:
        with pytest.raises(RuntimeError, match="executable is invalid"):
            _binary(name)
    run.assert_not_called()


@pytest.mark.parametrize(
    "returncode,stdout,message",
    [(1, "{}", "lighthouse failed"), (0, "invalid", "invalid JSON")],
)
def test_lighthouse_failures(executable, returncode, stdout, message):
    result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
    with patch("auditor_toolkit.external_tools.shutil.which", return_value=executable), patch(
        "auditor_toolkit.external_tools.subprocess.run", return_value=result
    ):
        with pytest.raises(RuntimeError, match=message):
            run_lighthouse("https://example.com")
