"""Sandbox-proof test capabilities (Master Plan P4).

Environment capability probes, loopback-only (iron constraint: probes never
touch non-loopback endpoints). Dependent tests must SKIP with an explicit
reason instead of erroring — red from environment noise teaches operators to
ignore red, and that is how real regressions slip through.

Exposed constants:
  HAS_SOCKET            loopback TCP connect attempt succeeded or was refused
                        (refused still proves the socket stack works)
  HAS_DNS               loopback name resolution works
  HAS_PLAYWRIGHT        playwright package importable
  HAS_CONTROL_PLANE     control-plane/config/routing.yaml present
  HAS_EMAIL_CASE_FIXTURES  email-observation-evidence case corpus present
  HAS_EMAIL_MIGRATION_SQL  migrations/ rollback fixture present
  HAS_HERMES_SOURCE_DB  legacy agent-trials source DB present
"""
import importlib.util
import socket
from pathlib import Path

MM_DIR = Path(__file__).resolve().parent
REPO = MM_DIR.parent


def _probe_socket():
    """Loopback-only socket probe. A refused connection still proves the
    socket stack is functional; only hard failures (sandbox denial) count
    as HAS_SOCKET=False."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(1.0)
            try:
                sock.connect(("127.0.0.1", 9))  # discard port; refusal is fine
            except ConnectionRefusedError:
                pass  # stack works, nothing listening — that is OK
        finally:
            sock.close()
        return True
    except OSError:
        return False


def _probe_dns():
    """Loopback-only DNS probe: resolving 'localhost' never leaves the host."""
    try:
        return bool(socket.getaddrinfo("localhost", 80, type=socket.SOCK_STREAM))
    except OSError:
        return False


def _probe_playwright():
    try:
        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


HAS_SOCKET = _probe_socket()
HAS_DNS = _probe_dns()
HAS_PLAYWRIGHT = _probe_playwright()
HAS_CONTROL_PLANE = (REPO / "control-plane" / "config" / "routing.yaml").is_file()
HAS_EMAIL_CASE_FIXTURES = (MM_DIR / "reports" / "email-observation-evidence" / "cases").is_dir()
HAS_EMAIL_MIGRATION_SQL = (MM_DIR / "migrations" / "003_email_finder_v2_rollback.sql").is_file()
HAS_HERMES_SOURCE_DB = Path(
    "/Users/dd/agent-trials/hermes/database/money_machine.db").is_file()


def capabilities():
    """Doctor-facing capability report (why-skipped is one command away)."""
    return {
        "HAS_SOCKET": HAS_SOCKET,
        "HAS_DNS": HAS_DNS,
        "HAS_PLAYWRIGHT": HAS_PLAYWRIGHT,
        "HAS_CONTROL_PLANE": HAS_CONTROL_PLANE,
        "HAS_EMAIL_CASE_FIXTURES": HAS_EMAIL_CASE_FIXTURES,
        "HAS_EMAIL_MIGRATION_SQL": HAS_EMAIL_MIGRATION_SQL,
        "HAS_HERMES_SOURCE_DB": HAS_HERMES_SOURCE_DB,
    }
