"""Verify the structured worker database connection without writing state."""

from scripts.postgres_store import PostgresPipelineStore


def verify_runtime(store):
    with store.connection() as db, db.transaction():
        db.execute("SET TRANSACTION READ ONLY")
        result = db.execute("""
            SELECT session_user, current_user,
                   count(*) > 0 AND bool_and(row_security_active(c.oid))
              FROM pg_catalog.pg_class AS c
              JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
             WHERE n.nspname = 'moneymachine' AND c.relkind IN ('r', 'p')
        """).fetchone()
        if result != ("moneymachine_runner", "moneymachine_worker", True):
            raise ValueError("Unexpected role or row security")


def main():
    try:
        verify_runtime(PostgresPipelineStore())
    except Exception:
        # Driver and connection errors can contain credentials or database details.
        print("POSTGRES_RUNTIME_PREFLIGHT_BLOCKED")
        return 2
    print("Restricted Postgres runtime preflight passed with zero writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
