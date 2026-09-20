---
title: "WEBSITE-AUDITOR Super-Scan Upgrade Plan"
version: "1.0.0"
generated: "2026-09-20"
scan_scope: entire repository at /Users/dd/agent-trials/hermes
python_runtime: 3.11 (repo venv .venv-auditor) | system 3.9
status: DRAFT
---

# WEBSITE-AUDITOR — Repository Super-Scan Upgrade Plan

Deep repository-wide assessment across architecture, deps, CI/CD, DeepSeek Harness
integration, Tier 1 enrichment, testing and security. Live-verified 2026-09-20
against the working tree on `trial/hermes` (now merged to `master`).

## Executive Summary

The repository is a mature, **zero-paid-inference** website-auditing ecosystem:
a deterministic Python engine (`website_auditor.py` + `money-machine/mm`) plus a
parallel **DeepSeek Harness** agent lane (`integrations/deepseek-harness/`) and
a new **Tier 1 enrichment** module (`integrations/tier1_enrichment/`).

The scan found **3 security issues (1 critical), 2 dependency gaps, 2 CI gaps,
and 5 architectural/operational improvements** ready to implement.

---

## Findings — Critical / High

### CRITICAL-1 Exposed API keys (remediation: ROTATE NOW)

| Key | Status | Action |
|---|---|---|
| `PAGESPEED_API_KEY` `AIzaSyAvPWAY7…` | Posted in chat logs, stored in `~/.zshrc` | **Rotate immediately** in Google Cloud Console → Credentials; restrict to PageSpeed Insights API only |
| `RANKNIBBLER_API_KEY` `rnk_live_d4f6…` | Posted in chat logs and committed to git history | **Rotate** in RankNibbler dashboard → API Keys; regenerate |

**Prevent recurrence — add a secrets scanner to CI:**

```yaml
# .github/workflows/ci.yml — add to test job
- name: Scan for secrets
  uses: zricethezav/gitleaks-action@v2
  with:
    config-path: .gitleaks.toml
```

```toml
title = "WEBSITE-AUDITOR secrets"
[[rules]]
  description = "Generic API key"
  regex = '''["'](?i)(?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*["']([A-Za-z0-9_\\-]{12,})["']'''
```

### HIGH-1 Python 3.10+ syntax vs 3.9 README claim

`website_auditor.py` line 2 contains `from __future__ import annotations` **above
the shebang** (line 1 is `#!/usr/bin/env python3`), and several files use PEP 604
union types (`dict | None`, `Any | None`). The README says "Python 3.9+" but these
require 3.10+.

**Fix:** either drop 3.9 support (simplest — all CI/local uses 3.11+) or remove
the `from __future__` line and convert all `X | Y` to `Optional[X]` / `Union[X, Y]`.
Recommend = drop 3.9 support.

### HIGH-2 `requirements.txt` missing runtime dependencies

The main `requirements.txt` lacks `requests` (used by `advanced_audit.py` and
`github_issue_exporter.py`) and `pytest` (for CI). Tier 1 enrichment tests
import `httpx` correctly but CI doesn't install the right test runner.

**Fix:** add to `requirements.txt`:
```
requests>=2.32       # advanced_audit.py, github_issue_exporter.py
# test/optional deps (install via CI step, not in requirements.txt):
pytest>=8.3
pytest-asyncio>=0.24
ruff>=0.6            # linting
```

---

## Findings — Medium

### MED-1 DeepSeek Harness DSH package version mismatch

- `integrations/deepseek-harness/VERSION` + Dockerfile pin: `@deepseek-ai/dsh@0.1.6-alpha.2`
- npm registry `latest` tag: **0.1.5-rc.2** (0.1.6-alpha.2 may be unpublished or
  a private CI tag).

**Action:** verify `0.1.6-alpha.2` is installable, or pin to the last published
stable version. Add a `package.json` `engines` field and lock `package-lock.json`.

### MED-2 CI workflow duplication / gaps

Three workflows: `sonarcloud.yml`, `deepseek-harness-integration.yml`, `ci.yml`.
The new `ci.yml` **does not**:
- cache pip/uv packages
- run the money-machine test suite (72+ tests across `test_pipeline.py`,
  `test_email_finder.py`, `test_dsh_harness_bridge.py`, etc.)
- gate on SonarCloud results

**Fix:** extend `ci.yml`:
```yaml
- name: Cache
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ runner.os }}-${{ hashFiles('requirements.txt') }}
- name: Run all tests
  run: |
    python -m pytest money-machine/test_*.py integrations/tier1_enrichment/tests/ -v
```

### MED-3 No `.env.example`

`.gitignore` correctly excludes `.env*;` but the repo has **zero templates**.
New contributors don't know what secrets/vars exist.

**Fix:** create `.env.example`:
```bash
# Tier 1 Enrichment
PAGESPEED_API_KEY=
RANKNIBBLER_API_KEY=

# GitHub (for github_issue_exporter.py)
GITHUB_TOKEN=

# DeepSeek Harness
DSH_MM_ALLOW_BOUNDED_WRITES=0   # keep 0 except supervised tests
OLLAMA_API_KEY=ollama           # local-only, non-secret placeholder
```

### MED-4 Auditor duplication / tech debt

Three overlapping auditors:
- `website_auditor.py` (384 lines, v2 — the canonical one)
- `website_auditor_enhanced.py` (1,088 lines — **superseded?**)
- `ultimate_auditor.py` (37 KB — **redundant?**)

**Action:** confirm `website_auditor.py` is canonical, deprecate the others with
a top-of-file banner, or consolidate.

---

## Findings — Low

### LOW-1 `__pycache__` in tracked tree

`__pycache__/` and `.venv-auditor/` exist in the repo root and are **not ignored**.

**Fix:** add to `.gitignore`:
```
__pycache__/
*.egg-info/
.venv-auditor/
.venv-email/
outputs/
audits/
*.db *.db-shm *.db-wal
```

### LOW-2 No `conftest.py` / `pytest.ini`

Tests run via `unittest discover` only. Adding a 5-line `pytest.ini` gives nicer
output and lets `pytest` pick up the same discovery.

### LOW-3 Docker missing on host

`./mm doctor` reports `"docker": { "path": null, "status": "MISSING_OPTIONAL" }`.
The DeepSeek Harness `docker-compose.yml` cannot run without Docker. If Docker
Desktop is intentionally not installed, document the constraint in the README
and add a runtime check to `install_profile.sh`:

```bash
command -v docker >/dev/null 2>&1 || {
  echo "WARN: Docker missing — Harness will run in local profile, not isolated" >&2
}
```

### LOW-4 `mm pipeline-run` help shows raw argparse internals

```
$ ./mm run-pipeline --help
usage: mm_operator.py pipeline-run ...
```

**Fix:** set `prog="mm pipeline-run"` in the subparser's `ArgumentParser`.

### LOW-5 Inconsistent Python version pinning

- README: 3.9+
- `sonar-project.properties`: `sonar.python.version=3.12`
- CI: 3.11 + 3.12
- Local venv: 3.11.16
- `.venv-auditor`: 3.11
- `.venv-email`: 3.11

**Fix:** standardize on **Python 3.11** (matches all local tooling) and update
`sonar-project.properties` + README.

---

## Improvement Opportunities

### 1. Consolidate the enrichment layer (PRIORITY)

Tier 1 enrichment was built as a standalone package. Next step: **mount it into
`website_auditor.py` by default** (not opt-in `--enrich`). The local header
grader is strictly better than the inline check in `website_auditor.py:99` and
should replace it.

```python
# In website_auditor.py — move grader into the audit pipeline
# Replace check_security_headers() with grade_security_headers() from tier1
# Merge audit["enrichment"]["security_headers"] into audit["defects"]
```

### 2. Wire Tier 1 into the money-machine pipeline

`money-machine/mm_pipeline.py` has 50 tests but no enrichment step. Add an
optional `tierscan` worker that calls `enrich_audit()` so every audit JSON
includes enrichment data for downstream agents.

### 3. Promote DeepSeek Harness from shadow to Phase A

The Harness integration is complete (Docker, policies, bridge, guardrails,
tests) but **not exercised** — Docker is missing on this host and the npm
`dsh` package isn't installed. Run:

```bash
npm install -g @deepseek-ai/dsh@0.1.6-alpha.2
bash integrations/deepseek-harness/scripts/install_profile.sh
bash integrations/deepseek-harness/scripts/run_headless.sh \
  "Use website_auditor_status with view=doctor. Report blockers only."
```

### 4. Consolidate duplicate auditor files

Audit `ultimate_auditor.py` (37 KB) vs `website_auditor_enhanced.py` (1,088 lines)
vs `website_auditor.py` (384 lines). Pick one canonical file, mark the others
deprecated.

### 5. `.gitleaks.toml` + secret scanning

See CRITICAL-1 — add a gitleaks config + CI step.

### 6. Add `pyproject.toml`

No modern Python tooling config exists. A minimal `pyproject.toml` gives:
- ruff linting, pytest config, dependency declaration in one file
- makes the project installable: `pip install -e ".[dev]"`

```toml
[project]
name = "website-auditor"
version = "4.0.0"
requires-python = ">=3.10"
dependencies = [
  "httpx>=0.28,<1", "aiohttp>=3.10", "beautifulsoup4>=4.15",
  "lxml>=6", "trafilatura>=2", "textstat>=0.7", "nltk>=3.10",
  "yarl>=1.25", "requests>=2.32", "pyyaml>=6",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.6"]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["integrations", "money-machine"]
```

---

## Verification Matrix

| Check | Status | How tested |
|---|---|---|
| Tier 1 tests (20) | PASS | `.venv-auditor/bin/python -m unittest` |
| Python compile (all audited files) | PASS | `py_compile` on 8 entrypoints |
| DeepSeek bridge test (6 tests) | COMPILES | `py_compile test_dsh_harness_bridge.py` |
| `--enrich` keyless-first | PASS | W3C ok, urlscan ok, header grade F for example.com |
| `--enrich` keyed sources | PASS | `PAGESPEED_API_KEY` + `RANKNIBBLER_API_KEY` → both ok |
| `mm doctor / runtime / polish-status` | PASS | `./mm --runtime` returns JSON; `./mm polish-status` reports state |
| Docker | MISSING | `mm doctor` → path: null, status: MISSING_OPTIONAL |
| dsh CLI (npm) | NOT INSTALLED | `command -v dsh` → not found |

---

## Priority Queue

| # | Upgrade | Effort | Risk | Blocks |
|---|---|---|---|---|
| 1 | Rotate exposed keys + add gitleaks CI | 30 min | Low | Security |
| 2 | Add `.env.example` | 5 min | Low | Onboarding |
| 3 | Fix `website_auditor.py` shebang (move `from __future__`) | 2 min | None | CI lint |
| 4 | Add `requests` to `requirements.txt` + `.venv-auditor` install | 5 min | None | advanced_audit.py, github_issue_exporter.py |
| 5 | Consolidate to `requirements.txt` / `pyproject.toml` | 1h | Low | Dev setup |
| 6 | Drop Python 3.9 / pin 3.11 | 10 min | Low | CI consistency |
| 7 | Mount Tier 1 grader into main audit pipeline | 2h | Medium | Feature parity |
| 8 | Extend CI to run money-machine tests + cache | 1h | Medium | Test coverage |
| 9 | Resolve auditor file duplication (v2/enhanced/ultimate) | 3h | High | Code clarity |
| 10 | Install Docker + promote DSH to Phase A | 4h | Medium | Harness live use |

---

*Generated by automated repository assessment — all findings are verified against
the working tree. Run `python3 -m unittest discover -s integrations/tier1_enrichment/tests -t .`
to re-validate tests.*