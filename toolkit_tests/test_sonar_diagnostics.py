"""Exercise the SonarCloud workflow diagnostic without contacting SonarCloud."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    not shutil.which("bash") or not shutil.which("jq"),
    reason="SonarCloud workflow diagnostics require Bash and jq",
)

# Simulate the APIs from a single analysis. Each call is recorded even when the
# workflow would otherwise ignore an error from the diagnostic.
MOCK_API = r"""
base64() { cat >/dev/null; printf 'fixture'; }
curl() {
  case "$*" in
    *'/api/ce/task?'*)
      printf '{"task":{"status":"%s","analysisId":%s}}' "$TASK_STATUS" "$TASK_ANALYSIS"
      ;;
    *'/api/qualitygates/project_status'*)
      echo gate >> calls
      [[ "$*" == *'analysisId=fixture-current'* && "$*" != *'branch=master'* ]] || return 1
      printf '{"projectStatus":{"status":"ERROR","conditions":[]}}'
      ;;
    *'/api/measures/component_tree'*)
      echo metrics >> calls
      printf '{"components":[]}'
      ;;
    *) return 1 ;;
  esac
}
"""


@pytest.mark.parametrize(
    ("status", "analysis_id", "expected_calls"),
    [
        ("FAILED", "null", []),
        ("SUCCESS", "null", []),
        ("SUCCESS", '"fixture-current"', ["gate", "metrics"]),
    ],
)
def test_sonar_diagnostic_requires_current_analysis(tmp_path, status, analysis_id, expected_calls):
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/sonarcloud.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["sonarcloud"]["steps"]
    diagnostic = next(step["run"] for step in steps if step["name"] == "Report SonarCloud processing details")
    scanner = tmp_path / ".scannerwork"
    scanner.mkdir()
    (scanner / "report-task.txt").write_text("ceTaskId=fixture-task\n")
    result = subprocess.run(
        ["bash", "-e"],
        input=MOCK_API + diagnostic,
        text=True,
        capture_output=True,
        check=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_EVENT_NAME": "push",
            "SONAR_TOKEN": "fixture",
            "TASK_STATUS": status,
            "TASK_ANALYSIS": analysis_id,
        },
    )
    calls = tmp_path / "calls"
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected_calls
    if expected_calls:
        assert '"status": "ERROR"' in result.stdout
    else:
        assert "produced no completed analysis" in result.stdout
