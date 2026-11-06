"""Record fixture-suite results and compare executed modules to fresh source."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from _pytest.assertion.rewrite import _rewrite_test

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "evidence/codex"


def signature(value):
    if isinstance(value, types.CodeType):
        return (
            value.co_code, signature(value.co_consts), value.co_names,
            value.co_varnames, value.co_freevars, value.co_cellvars,
            value.co_flags, value.co_argcount, value.co_kwonlyargcount,
            value.co_posonlyargcount,
        )
    if isinstance(value, tuple):
        return tuple(signature(item) for item in value)
    return value


def hashes():
    paths = subprocess.check_output(
        ["git", "ls-files", "*.py"], cwd=ROOT, text=True
    ).splitlines()
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in paths if (ROOT / name).is_file()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["canonical", "money"], default="canonical")
    options = parser.parse_args()
    prefix = "q10-" + options.suite
    before = hashes()
    executed = {}
    rewritten = []
    active_config = None
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    sys.path[:0] = [str(ROOT), str(ROOT / "money-machine")]

    class Configuration:
        def pytest_configure(self, config):
            nonlocal active_config
            active_config = config

    def observe(frame, event, _argument):
        if event != "call" or frame.f_code.co_name != "<module>":
            return
        filename = frame.f_code.co_filename
        if not filename.endswith(".py"):
            return
        path = Path(filename).resolve()
        if not path.is_relative_to(ROOT):
            return
        relative = str(path.relative_to(ROOT))
        if relative not in before:
            return
        try:
            fresh = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
            matches = signature(frame.f_code) == signature(fresh)
            if not matches and (
                path.name.startswith("test_") or path.name == "conftest.py"
            ):
                _, expected = _rewrite_test(path, active_config)
                matches = signature(frame.f_code) == signature(expected)
                if matches:
                    rewritten.append(relative)
            executed[relative] = matches
        except (OSError, SyntaxError):
            executed[relative] = False

    targets = ["toolkit_tests", "tests"] if options.suite == "canonical" else ["money-machine", "-m", "not slow"]
    args = targets + [
        "-q", "-p", "no:cacheprovider",
        "--basetemp=" + str(ROOT / ("work/codex-r00/pytest-" + options.suite + "-final")),
        "--junitxml=" + str(OUTPUT / (prefix + ".xml")),
    ]
    sys.setprofile(observe)
    try:
        exit_code = int(pytest.main(args, plugins=[Configuration()]))
    finally:
        sys.setprofile(None)
    after = hashes()
    receipt = {
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "started_at_utc": started,
        "duration_seconds": round(time.monotonic() - timer, 3),
        "pytest_arguments": args,
        "exit_code": exit_code,
        "changed_during_run": sorted(
            name for name in before.keys() | after.keys()
            if before.get(name) != after.get(name)
        ),
        "executed_module_comparisons": executed,
        "verified_pytest_rewritten_modules": sorted(set(rewritten)),
        "loaded_mismatches": sorted(name for name, matches in executed.items() if not matches),
        "limitations": [
            "Execution attestation covers observed parent-process tracked Python modules",
            "Child-process code and production runtime are not attested",
            "Opt-in browser coverage retains its own skip conditions",
        ],
    }
    (OUTPUT / (prefix + "-receipt.json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items()
                      if key != "executed_module_comparisons"}, indent=2))
    return exit_code or int(bool(receipt["changed_during_run"] or receipt["loaded_mismatches"]))


if __name__ == "__main__":
    sys.exit(main())
