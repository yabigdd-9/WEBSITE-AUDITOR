"""Read-only Supabase connector preflight. No state, schema or secret changes.

Run only after the owner activates a dedicated restricted login and installs a
GitHub Actions secret. This command never prints passwords, DSNs or SQL errors.
"""
from __future__ import annotations

import json
import os

PROJECT_REF = "srymerkhraklwuttzexi"
USERNAME = "mm_pipeline_connector"

# Only static verified metadata and aggregate row counts are retrieved.
READ_ONLY_STATUS_QUERY = """
SELECT current_user,
       rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls,
       pg_has_role(current_user, 'mm_checkpoint_writer', 'USAGE'),
       has_schema_privilege(current_user, 'mm_internal', 'USAGE'),
       has_table_privilege(current_user, 'mm_internal.encrypted_checkpoints', 'SELECT')
         AND has_table_privilege(current_user, 'mm_internal.encrypted_checkpoints', 'INSERT')
         AND has_table_privilege(current_user, 'mm_internal.encrypted_checkpoints', 'UPDATE'),
       has_table_privilege(current_user, 'mm_internal.encrypted_checkpoint_history', 'SELECT')
         AND has_table_privilege(current_user, 'mm_internal.encrypted_checkpoint_history',
                                 'INSERT'),
       has_table_privilege(current_user, 'mm_internal.encrypted_checkpoint_history',
                           'DELETE'),
       (SELECT bool_and(c.relrowsecurity)
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='mm_internal' AND c.relkind='r')
  FROM pg_roles WHERE rolname=current_user
"""
READ_ONLY_COUNTS_QUERY = """
SELECT (SELECT count(*) FROM mm_internal.encrypted_checkpoints),
       (SELECT count(*) FROM mm_internal.encrypted_checkpoint_history)
"""


def verify_status(status: tuple, counts: tuple) -> dict:
    """Refuse admin sessions, unexpected grants or existing state changes."""
    if len(status) != 13 or len(counts) != 2:
        raise ValueError("Unexpected connector preflight metadata")
    (user, can_login, superuser, create_db, create_role, replicate, bypass_rls,
     has_writer, schema_access, checkpoint_rw, history_rw, history_delete, rls_enabled) = status
    if (user != USERNAME
            or can_login is not True
            or any(value is not False for value in
                   (superuser, create_db, create_role, replicate, bypass_rls, history_delete))
            or any(value is not True for value in
                   (has_writer, schema_access, checkpoint_rw, history_rw, rls_enabled))):
        raise ValueError("Database role is not the expected least-privilege connector")
    if (any(type(n) is not int or n < 0 for n in counts)
            or counts[0] not in (0, 1) or counts[1] > 24):
        raise ValueError("Unexpected checkpoint metadata")
    return {
        "read_only_preflight": "PASS",
        "dedicated_role": True,
        "verified_tls": True,
        "rls_access": True,
        "public_key_or_secret_logged": False,
        "saved_checkpoints": counts[0],
        "saved_revisions": counts[1],
        "writes_performed": 0,
        "worker_switched": False,
    }


def safe_failure_category(exc: Exception) -> str:
    """Emit only fixed diagnostic labels; never include exception text or DSNs."""
    from psycopg import OperationalError
    from psycopg.conninfo import conninfo_to_dict  # noqa: F401

    if isinstance(exc, KeyError):
        return "MISSING_CONFIGURATION"
    if isinstance(exc, (ValueError, TypeError)):
        return "CONFIGURATION_OR_POLICY"
    if isinstance(exc, OperationalError):
        # Connection errors may contain credentials, hostnames or certificates.
        # Do not print their text, repr, cause, or SQLSTATE.
        return "DATABASE_CONNECTION"
    return "UNCLASSIFIED"


def main() -> int:
    try:
        from psycopg import connect
        from psycopg.conninfo import conninfo_to_dict

        from scripts.supabase_checkpoint_store import validate_supabase_dsn

        dsn = os.environ["WA_PG_DATABASE_URL"]
        project = os.environ["WA_SUPABASE_PROJECT_REF"]
        if project != PROJECT_REF:
            raise ValueError("Not the owner-approved database project")
        validate_supabase_dsn(dsn, expected_ref=PROJECT_REF)
        supplied_user = conninfo_to_dict(dsn).get("user", "").split(".", 1)[0]
        if supplied_user != USERNAME:
            raise ValueError("This preflight accepts only the dedicated connector role")

        with connect(dsn, connect_timeout=8, application_name="mm-preflight-only") as db:
            with db.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(READ_ONLY_STATUS_QUERY)
                status = cur.fetchone()
                cur.execute(READ_ONLY_COUNTS_QUERY)
                counts = cur.fetchone()
                result = verify_status(status, counts)

        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Never echo exceptions: psycopg errors can contain credential material.
        print("SUPABASE_PREFLIGHT_BLOCKED: " + safe_failure_category(exc)
              + "; no writes or worker activation")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
