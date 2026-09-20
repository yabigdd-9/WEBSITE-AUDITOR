#!/usr/bin/env python3
"""Canonical local pipeline; no external connector dispatch or stale report discovery."""
import sys
from auditor_toolkit.cli import main

if __name__ == '__main__':
    raise SystemExit(main(['audit', *sys.argv[1:]]))
