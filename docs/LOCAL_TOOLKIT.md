# Local Website Auditor Toolkit

Run a local audit:

```bash
cd /Users/dd/WEBSITE-AUDITOR
.venv-toolkit/bin/python -m auditor_toolkit audit https://example.com --no-tls
```

Run diagnostics:

```bash
cd /Users/dd/WEBSITE-AUDITOR
.venv-toolkit/bin/python -m auditor_toolkit doctor
```

Run the focused local checks:

```bash
cd /Users/dd/WEBSITE-AUDITOR
.venv-toolkit/bin/python -m pytest toolkit_tests
.venv-toolkit/bin/python -m ruff check auditor_toolkit toolkit_tests --ignore E501
```

The CLI exits nonzero for partial audits so automation cannot mistake failed fetches for successful healthy audits.

