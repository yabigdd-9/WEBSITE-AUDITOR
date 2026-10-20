"""Thin compatibility entrypoint; importing this file performs no audit."""


def main(argv=None):
    from auditor_toolkit.advanced import main as canonical_main

    return canonical_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
