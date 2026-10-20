#!/usr/bin/env python3
"""Deprecated filename; command-line audits use the canonical toolkit.

The previous standalone library implementation is retained as a source archive.
Importing this wrapper does not create caches, fetch pages or run an audit.
Use auditor_toolkit.pipeline.run_audit for the current library contract.
"""


def main(argv=None):
    from auditor_toolkit.compat import legacy_main

    return legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
