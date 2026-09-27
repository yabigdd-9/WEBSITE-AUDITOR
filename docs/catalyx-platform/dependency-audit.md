# CatalyxLabs Website Auditor dependency audit

**Date:** 2026-09-28
**Scope:** Selected hosted web runtime (`web` + `portal` extras), plus a separate
all-extras inventory. This does not assess application source code.

## Hosted web runtime

- `uv.lock` records the resolved full-project graph.
- `requirements-catalyx-web.lock` is the exact hash-pinned dependency export
  used for the Website Auditor web runtime. It includes the base project
  dependencies, FastAPI/Uvicorn, PostgreSQL driver, form handling, Argon2, and
  `cryptography` for authenticated encryption of administrator TOTP seeds.
- The export excludes the root editable package, development tools, browser
  tooling, optional SMTP, and local-model extras. The deployment must install
  the project itself and this selected dependency profile from the same commit.
- `pip-audit -r requirements-catalyx-web.lock --no-deps --disable-pip
  --require-hashes --strict`: **no known vulnerabilities found**.
- `uv sync --dry-run --frozen --no-dev --extra web --extra portal --python
  /Users/dd/WEBSITE-AUDITOR/.venv/bin/python`: resolved successfully for Python
  3.11.16; planned 54 packages for the selected profile.

The base lock was resolved on Python 3.14 and contains interpreter markers;
the Python 3.11 dry run confirms the selected runtime profile resolves for the
project's supported production target. A real isolated Python 3.11 sync was
started with development tools included, but the macOS Intel environment began
building `cryptography` from source and that local build was interrupted. Do
not treat a complete isolated package installation as verified. The existing
preview continues to run with the previously working local environment.

## Optional extras

The separate all-extras audit returned two records for `diskcache==5.6.3`, a
dependency of optional local-model support. The advisory database describes
unsafe pickle deserialization if an attacker already has write access to the
cache directory: [OSV PYSEC-2026-2447](https://osv.dev/vulnerability/PYSEC-2026-2447).
The package is excluded from the hosted web profile. Do not add the `ai` extra
to the public app until its cache ownership/isolation and an acceptable
dependency path are reviewed. The SMTP dependency was upgraded to `5.1.3`;
the all-extras audit did not report an SMTP advisory after that change.

## Limits

This result is a point-in-time package advisory check, not a source scan, SBOM
sign-off, maintainer trust review, or guarantee against unknown vulnerabilities.
It does not clear the separate release blockers for PostgreSQL integration,
worker isolation, backup/restore, independent security review, legal/privacy
approval, or production operations.
