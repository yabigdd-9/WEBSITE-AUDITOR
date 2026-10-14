#!/usr/bin/env python3
"""Deprecated build script.

The monthly reporting engine is now implemented in auditor_toolkit.monthly and
website_auditor.reporting. This historical generator used to write an SMTP-capable
email sender into the source tree; that behavior is intentionally removed.

Use:
    wa monthly ...
or the tested draft-only reporting APIs instead.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "DEPRECATED: make_monthly_reporting.py no longer generates or overwrites "
        "reporting source files. Use the canonical 'wa monthly' workflow. "
        "External email dispatch remains disabled.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
