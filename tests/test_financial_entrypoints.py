"""Legacy image and shell entry points cannot silently enable external models."""

import ast
import json
import os
import subprocess
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("provider", ["pollinations", "openrouter", "both", "unknown"])
def test_legacy_image_generation_is_truthfully_held(tmp_path, monkeypatch, provider):
    # Scope is the actual function body. The complete legacy script has an
    # unmet tenacity dependency, recorded separately; no import success is claimed.
    source = ROOT / "full-pipeline.py"
    function = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "generate_mockup")
    namespace = {"Path": Path, "urllib": urllib, "MOCKUPS": tmp_path, "json": json, "os": os}
    # A compiled fragment must not impersonate execution of the whole file in
    # tracebacks or the parent-process module attestation probe.
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 "<isolated full-pipeline.generate_mockup fragment>", "exec"), namespace)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: pytest.fail("external image request"))
    audit = tmp_path / "synthetic.json"
    audit.write_text('{"domain":"synthetic.invalid","score":50}')
    prior = tmp_path / "synthetic.png"
    prior.write_bytes(b"old-unverified-image")
    name, success, reason = namespace["generate_mockup"](audit, provider)
    assert name == "synthetic" and success is False and "BLOCKED_COST" in reason
    assert prior.read_bytes() == b"old-unverified-image"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["synthetic.json", "synthetic.png"]


@pytest.mark.parametrize("command", ["server", "all", "start", "stop"])
def test_shell_activation_does_not_source_env_or_run_services(tmp_path, command):
    marker = tmp_path / "unexpected-execution"
    fake = tmp_path / "python"
    fake.write_text('#!/bin/sh\nprintf invoked > "$EXECUTION_MARKER"\n')
    fake.chmod(0o700)
    result = subprocess.run(["/bin/bash", str(ROOT / "money-machine/scripts/fcc-bridge.sh"), command],
                            env={"PATH": os.environ.get("PATH", ""), "MM_PYTHON": str(fake),
                                 "EXECUTION_MARKER": str(marker)}, capture_output=True, timeout=5)
    assert result.returncode == 3
    assert b"BLOCKED" in result.stderr
    assert not marker.exists()


def test_shell_defaults_to_status_without_service_activation(tmp_path):
    marker = tmp_path / "arguments"
    fake = tmp_path / "python"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$EXECUTION_MARKER"\n')
    fake.chmod(0o700)
    result = subprocess.run(["/bin/bash", str(ROOT / "money-machine/scripts/fcc-bridge.sh")],
                            env={"PATH": os.environ.get("PATH", ""), "MM_PYTHON": str(fake),
                                 "EXECUTION_MARKER": str(marker)}, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert marker.read_text().splitlines() == [str(ROOT / "money-machine/scripts/fcc-bridge.py"), "status"]
