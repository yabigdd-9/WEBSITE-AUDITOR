"""Replay isolated integration suites using the existing Q10 execution probe."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
PYTHON = Path("/Users/dd/WEBSITE-AUDITOR/.venv-email/bin/python")

CHILD = """
import importlib.util,sys
from pathlib import Path
root=Path(sys.argv[1]);out=Path(sys.argv[2]);scratch=Path(sys.argv[3]);suite=sys.argv[4]
path=root/'evidence/codex/q10_baseline_probe.py'
spec=importlib.util.spec_from_file_location('integration_q10_probe',path)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
probe.OUTPUT=out
original=probe.pytest.main
def isolated(arguments,plugins):
    for index,argument in enumerate(arguments):
        if argument.startswith('--basetemp='):
            arguments[index]='--basetemp='+str(scratch/('pytest-'+suite))
    return original(arguments,plugins=plugins)
probe.pytest.main=isolated
sys.argv=[str(path),'--suite',suite]
sys.exit(probe.main())
"""


def head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--suite", choices=["canonical", "money", "all"], default="all")
    options = parser.parse_args()
    revision = head()
    if not re.fullmatch(r'[0-9a-f]{40}', options.expected_sha) or revision != options.expected_sha:
        raise SystemExit("Source HEAD differs from the pinned integration revision")
    scratch = ROOT / "work/codex-r00/integration" / revision[:12]
    scratch.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "work/codex-r00/money-source-legacy-final/database/money_machine.db"
    if not fixture.is_file():
        raise SystemExit("Build the reviewed Q10 synthetic fixture before integration tests")
    environment = {key: value for key, value in os.environ.items()
                   if not any(word in key.upper()
                              for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": str(ROOT) + os.pathsep + str(ROOT / "money-machine"),
        "MM_ROOT": str(scratch / "isolated-mm-root"),
        "MM_PYTHON": str(PYTHON),
        "MM_TEST_SOURCE": str(fixture),
        "TMPDIR": str(scratch),
        "MM_EXTERNAL_SEND_DISABLED": "1",
        "HERMES_ALLOW_HOSTED_LLM": "0",
        "HERMES_ALLOW_PAID_FALLBACK": "0",
        "WEBSITE_AUDITOR_OUTREACH_SEND": "0",
    })
    suites = {"canonical": ("canonical",), "money": ("money",),
              "all": ("canonical", "money")}[options.suite]
    for suite in suites:
        if head() != options.expected_sha:
            raise SystemExit("Source HEAD changed between suites")
        with (OUTPUT / ("q10-" + suite + ".log")).open("w") as log:
            result = subprocess.run(
                [str(PYTHON), "-B", "-c", CHILD, str(ROOT), str(OUTPUT), str(scratch), suite],
                cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=600,
            )
        receipt = json.loads((OUTPUT / ("q10-" + suite + "-receipt.json")).read_text())
        print(json.dumps({
            "suite": suite, "source_sha": receipt["source_sha"],
            "process_exit": result.returncode, "pytest_exit": receipt["exit_code"],
            "duration_seconds": receipt["duration_seconds"],
            "changed_during_run": receipt["changed_during_run"],
            "loaded_mismatches": receipt["loaded_mismatches"],
        }), flush=True)
        if result.returncode or receipt["changed_during_run"] or receipt["loaded_mismatches"]:
            return result.returncode or 1
    if head() != options.expected_sha:
        raise SystemExit("Source HEAD changed during validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
