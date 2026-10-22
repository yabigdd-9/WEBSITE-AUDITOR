"""CATALYX replacement Gmail bridge: authentication and read-only header sync.

No mail-send implementation. No writes to the auditor database or approval state.
Credentials are accepted only via a hidden local dialog and macOS Keychain.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import email
import email.policy
import email.utils
import fcntl
import hashlib
import imaplib
import json
import os
import plistlib
import re
import smtplib
import sqlite3
import ssl
import subprocess
import sys
from pathlib import Path

ACCOUNTS = ("team.catalyxlabs@gmail.com", "yabigdd@gmail.com")
SERVICE = "CATALYX WEBSITE-AUDITOR Gmail Bridge replacement-v2"
CONFIG = Path.home() / ".config/website-auditor/google/gmail-bridge.json"
STATE = Path.home() / ".local/share/website-auditor/gmail-bridge"
REPO = Path(__file__).resolve().parents[1]
LABEL = "com.catalyxlabs.website-auditor.gmail-readonly"
FETCH = "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES FROM TO DATE)])"
ID_PATTERN = re.compile(r"<[^<>\s]{1,998}>")


class LoginRejectedError(Exception):
    """Redacted provider login failure."""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def private_dir(path):
    if path.is_symlink():
        raise ValueError("Private directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise ValueError("Private directory belongs to another user")
    path.chmod(0o700)


def private_write(path, data):
    private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def install():
    private_dir(STATE)
    expected = {
        "version": 2, "accounts": list(ACCOUNTS),
        "smtp": {"host": "smtp.gmail.com", "port": 587, "security": "STARTTLS"},
        "imap": {"host": "imap.gmail.com", "port": 993, "security": "SSL"},
        "folder": "INBOX", "batch_limit": 200, "external_send_allowed": False,
        "keychain_service": SERVICE, "credential_source": "replacement_only",
    }
    if CONFIG.exists() and json.loads(CONFIG.read_text()) != expected:
        raise ValueError("Existing bridge configuration differs; preserve and review it")
    private_write(CONFIG, (json.dumps(expected, indent=2) + "\n").encode())
    with store():
        pass
    return {"installed": True, "config": str(CONFIG), "state": str(STATE),
            "external_send_allowed": False, "original_zip_available": False}


def config():
    if CONFIG.is_symlink() or CONFIG.stat().st_mode & 0o077:
        raise ValueError("Configuration must be private and not a symlink")
    doc = json.loads(CONFIG.read_text())
    if (doc.get("version") != 2 or doc.get("accounts") != list(ACCOUNTS)
            or doc.get("smtp") != {"host": "smtp.gmail.com", "port": 587, "security": "STARTTLS"}
            or doc.get("imap") != {"host": "imap.gmail.com", "port": 993, "security": "SSL"}
            or doc.get("external_send_allowed") is not False
            or doc.get("keychain_service") != SERVICE or doc.get("folder") != "INBOX"
            or doc.get("batch_limit") != 200
            or doc.get("credential_source") != "replacement_only"):
        raise ValueError("Bridge configuration does not match the safe fixed policy")
    return doc


def keychain():
    if sys.platform != "darwin":
        raise RuntimeError("macOS Keychain is required")
    from keyring.backends.macOS import Keyring
    return Keyring()  # Never select a plaintext or fallback backend.


def secret(account):
    value = keychain().get_password(SERVICE, account)
    if not value:
        raise LookupError("Replacement app password required")
    return value


def setup(account):
    config()
    prompt = ("Paste a NEW replacement Google app password for " + account
              + ". Revoke the exposed SMTP.rtf password first. This saves only to macOS Keychain.")
    script = ('on run argv\nactivate\nset resultDialog to display dialog (item 1 of argv) '
              'default answer "" with hidden answer buttons {"Cancel", "Save to Keychain"} '
              'default button "Save to Keychain" cancel button "Cancel" giving up after 300\n'
              'if gave up of resultDialog then error number -128\n'
              'return text returned of resultDialog\nend run')
    # Secret stays in captured process memory, never in argv, logs, files or chat.
    result = subprocess.run(["/usr/bin/osascript", "-e", script, prompt],
                            capture_output=True, text=True, timeout=310, check=False)
    if result.returncode:
        return {"account": account, "saved": False, "status": "cancelled_or_mac_dialog_unavailable"}
    value = "".join(result.stdout.split())
    if not re.fullmatch(r"[a-z]{16}", value):
        return {"account": account, "saved": False, "status": "invalid_app_password_format"}
    keychain().set_password(SERVICE, account, value)
    return {"account": account, "saved": True, "storage": "macOS Keychain"}


def imap_connection(password, account):
    client = imaplib.IMAP4_SSL("imap.gmail.com", 993,
                              ssl_context=ssl.create_default_context(), timeout=20)
    try:
        try:
            client.login(account, password)
        except imaplib.IMAP4.error:
            raise LoginRejectedError("IMAP login rejected") from None
        return client
    except Exception:
        with contextlib.suppress(Exception):
            client.logout()
        raise


def smtp_check(password, account):
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as client:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(account, password)
    return "authenticated_no_message_sent"


def failure(exc):
    # Provider exceptions may embed headers, addresses or credentials. Never print them.
    if isinstance(exc, LookupError):
        return "replacement_app_password_required"
    if isinstance(exc, (smtplib.SMTPAuthenticationError, LoginRejectedError)):
        return "gmail_login_rejected"
    if isinstance(exc, imaplib.IMAP4.error):
        return "authentication_or_imap_protocol_failed"
    if isinstance(exc, ssl.SSLError):
        return "tls_verification_failed"
    if isinstance(exc, TimeoutError):
        return "connection_timeout"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "smtp_connection_closed"
    if isinstance(exc, (OSError, TimeoutError)):
        return "network_or_mac_access_unavailable"
    return "local_configuration_or_keychain_error"


def check(account):
    config()
    result = {"account": account, "smtp": "not_checked", "imap": "not_checked",
              "external_messages_sent": 0}
    try:
        password = secret(account)
    except Exception as exc:
        result["smtp"] = result["imap"] = failure(exc)
        return result
    try:
        result["smtp"] = smtp_check(password, account)
    except Exception as exc:
        result["smtp"] = failure(exc)
    try:
        client = imap_connection(password, account)
        try:
            typ, _ = client.select("INBOX", readonly=True)
            if typ != "OK":
                raise imaplib.IMAP4.error("Read-only select failed")
            result["imap"] = "authenticated_inbox_readonly"
        finally:
            with contextlib.suppress(Exception):
                client.logout()
    except Exception as exc:
        result["imap"] = failure(exc)
    return result


@contextlib.contextmanager
def store():
    private_dir(STATE)
    target = STATE / "headers.sqlite3"
    if target.is_symlink():
        raise ValueError("Store must not be a symlink")
    fd = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    os.close(fd)
    db = sqlite3.connect(target, timeout=5)
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS cursors (
          account TEXT, folder TEXT, validity TEXT, last_uid INTEGER NOT NULL,
          PRIMARY KEY(account,folder));
        CREATE TABLE IF NOT EXISTS headers (
          account TEXT, dedupe_key TEXT, message_id TEXT, sender TEXT,
          references_json TEXT, observed_at TEXT,
          PRIMARY KEY(account,dedupe_key));
        CREATE TABLE IF NOT EXISTS observations (
          account TEXT, folder TEXT, validity TEXT, uid INTEGER, dedupe_key TEXT,
          PRIMARY KEY(account,folder,validity,uid));
        ''')
        yield db
    finally:
        db.close()


def header_data(raw, validity, uid):
    if len(raw) > 65536:
        raise ValueError("Header size limit exceeded")
    message = email.message_from_bytes(raw, policy=email.policy.default)
    ids = ID_PATTERN.findall(str(message.get("Message-ID", "")))
    mid = ids[0] if len(ids) == 1 else ""
    senders = email.utils.getaddresses([str(x) for x in message.get_all("From", [])])
    sender = senders[0][1].lower() if len(senders) == 1 else ""
    refs = list(dict.fromkeys(ID_PATTERN.findall(" ".join(
        str(x) for name in ("In-Reply-To", "References") for x in message.get_all(name, [])))))
    # Include header hash so malicious/colliding Message-IDs do not hide other messages.
    digest = hashlib.sha256(raw).hexdigest()
    key = "mid:" + mid + ":" + digest if mid else f"uid:{validity}:{uid}"
    return key, mid, sender, refs


def ingest(db, account, validity, uid, raw):
    key, mid, sender, refs = header_data(raw, validity, uid)
    inserted = db.execute("INSERT OR IGNORE INTO headers VALUES(?,?,?,?,?,?)",
                          (account, key, mid, sender, json.dumps(refs), now())).rowcount
    db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)",
               (account, "INBOX", validity, uid, key))
    return inserted


def sync(account, recent_days=None):
    doc = config()
    result = {"account": account, "status": "not_synced", "fetched": 0,
              "inserted": 0, "external_messages_sent": 0, "remote_mailbox_writes": 0}
    if recent_days is not None and not 1 <= recent_days <= 365:
        raise ValueError("Recent window must be 1 to 365 days")
    cursor_scope = "INBOX" if recent_days is None else f"INBOX:recent{recent_days}"
    result["scope"] = "INBOX all history" if recent_days is None else f"INBOX last {recent_days} days"
    try:
        password = secret(account)
        private_dir(STATE)
        fd = os.open(STATE / "sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            client = imap_connection(password, account)
            try:
                if client.select("INBOX", readonly=True)[0] != "OK":
                    raise imaplib.IMAP4.error("Read-only select failed")
                values = client.response("UIDVALIDITY")[1]
                validity = values[0].decode() if values and values[0] else ""
                if not validity.isdigit():
                    raise ValueError("UIDVALIDITY required")
                with store() as db:
                    cursor = db.execute("SELECT validity,last_uid FROM cursors WHERE account=? AND folder=?",
                                        (account, cursor_scope)).fetchone()
                    last = cursor[1] if cursor and cursor[0] == validity else 0
                    criteria = ["UID", f"{last + 1}:*"]
                    if recent_days is not None:
                        since = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=recent_days)
                        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
                        criteria += ["SINCE", f"{since.day:02d}-{months[since.month - 1]}-{since.year}"]
                    typ, data = client.uid("search", None, *criteria)
                    if typ != "OK":
                        raise imaplib.IMAP4.error("UID search failed")
                    all_uids = sorted({int(x) for x in data[0].split() if int(x) > last})
                    uids = all_uids[:doc["batch_limit"]]
                    inserted = 0
                    with db:
                        for offset in range(0, len(uids), 25):
                            group = uids[offset:offset + 25]
                            typ, fetched = client.uid("fetch", ",".join(map(str, group)), FETCH)
                            if typ != "OK":
                                raise imaplib.IMAP4.error("Header fetch failed")
                            parts = [x for x in fetched if isinstance(x, tuple)]
                            received = {}
                            for metadata, raw in parts:
                                match = re.search(rb"\bUID (\d+)\b", metadata)
                                if not match or int(match[1]) not in group or int(match[1]) in received:
                                    raise ValueError("Fetched UID does not match request")
                                received[int(match[1])] = raw
                            if set(received) != set(group):
                                raise ValueError("Header fetch incomplete")
                            for uid in group:
                                inserted += ingest(db, account, validity, uid, received[uid])
                        db.execute("INSERT OR REPLACE INTO cursors VALUES(?,?,?,?)",
                                   (account, cursor_scope, validity, uids[-1] if uids else last))
                    result.update(status="synced_headers_readonly", fetched=len(uids), inserted=inserted,
                                  duplicates=len(uids) - inserted, remaining=len(all_uids) - len(uids))
            finally:
                with contextlib.suppress(Exception):
                    client.logout()
    except Exception as exc:
        result["status"] = failure(exc)
    return result


def reply_candidates(refs, sender, receipts):
    matches = {row[0] for row in receipts
               if row[1] in refs and sender and row[2].strip().lower() == sender}
    return {"status": "candidate" if len(matches) == 1 else "ambiguous" if matches else "unmatched",
            "message_ids": sorted(matches), "human_review_required": True}


def audit_links(path):
    # Strictly read-only; remote headers are untrusted and cannot authorize state changes.
    path = Path(path).resolve(strict=True)
    with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as auditor:
        auditor.execute("PRAGMA query_only=ON")
        receipts = list(auditor.execute('''SELECT m.id,r.external_id,m.recipient
          FROM mm_messages m JOIN mm_receipts r ON CAST(r.id AS TEXT)=m.send_receipt
          WHERE m.sent_at IS NOT NULL AND r.kind='send' AND r.object_id=m.id
          AND r.business_id=m.business_id AND r.content_hash=m.approved_hash'''))
        receipts = [r for r in receipts if ID_PATTERN.fullmatch(r[1] or "")]
    counts = {"candidate": 0, "ambiguous": 0, "unmatched": 0}
    with store() as db:
        for refs, sender in db.execute("SELECT references_json,sender FROM headers"):
            counts[reply_candidates(json.loads(refs), sender, receipts)["status"]] += 1
    return {"status": "audited_readonly", "counts": counts,
            "eligible_rfc_message_id_receipts": len(receipts), "auditor_database_writes": 0,
            "human_review_required": True, "automatic_suppression": False,
            "note": "Header matches are candidates, not authenticated replies. Opaque provider IDs cannot match RFC Message-IDs."}


def launchd_template():
    # Prepared only: no launchctl, no automatic activation, no Keychain prompt from scheduler.
    private_dir(STATE)
    doc = {"Label": LABEL, "ProgramArguments": [str(REPO / ".venv/bin/python"),
            str(Path(__file__).resolve()), "sync", "--recent-days", "30"], "StartInterval": 900,
           "RunAtLoad": False, "WorkingDirectory": str(REPO), "ProcessType": "Background",
           "StandardOutPath": str(STATE / "sync.log"), "StandardErrorPath": str(STATE / "sync-error.log")}
    path = STATE / (LABEL + ".plist")
    private_write(path, plistlib.dumps(doc))
    return {"template": str(path), "loaded": False, "interval_seconds": 900,
            "activation_requires": "Successful authentication and two verified manual syncs"}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "setup", "check", "sync", "audit-links", "launchd-template"])
    parser.add_argument("--account", choices=ACCOUNTS)
    parser.add_argument("--recent-days", type=int, help="Separate cursor for a bounded recent INBOX window")
    parser.add_argument("--db", type=Path, default=REPO / "database/money_machine.db")
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install()
        elif args.command == "audit-links":
            result = audit_links(args.db)
        elif args.command == "launchd-template":
            result = launchd_template()
        else:
            fn = {"setup": setup, "check": check, "sync": sync}[args.command]
            result = [fn(a, recent_days=args.recent_days) if args.command == "sync" else fn(a)
                      for a in ([args.account] if args.account else ACCOUNTS)]
        print(json.dumps(result, indent=2))
        if args.command == "check":
            return 0 if all(r["smtp"] == "authenticated_no_message_sent" and
                            r["imap"] == "authenticated_inbox_readonly" for r in result) else 2
        if args.command == "sync":
            return 0 if all(r["status"] == "synced_headers_readonly" for r in result) else 2
        if args.command == "setup":
            return 0 if all(r["saved"] for r in result) else 2
        return 0
    except Exception as exc:
        print(json.dumps({"status": failure(exc), "external_messages_sent": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
