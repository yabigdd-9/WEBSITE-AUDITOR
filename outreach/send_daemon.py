#!/usr/bin/env python3
"""
Round-the-clock outbound email sender.

Reads outreach/queue.json, sends pending prospects via catalyx_send.py (SMTP),
records each send in the Money Machine DB via the bridge's record-sent action,
and respects the daily cap.

Usage:
  python3 send_daemon.py              # run once, send all pending
  python3 send_daemon.py --daemon    # loop forever (interval from --interval)
  python3 send_daemon.py --selftest  # send one test message to sender address

The daemon writes its own state back to queue.json (sent_at on each prospect)
and logs to outreach/send_daemon.log.

Requires:
  - .env with CATALYX_GMAIL_APP_PW (or Keychain catalyx_gmail_app_pw)
  - MM_BRIDGE_TOKEN set (for record-sent calls)
  - mm_bridge.py running on 127.0.0.1:8787 (for DB recording)
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Authorise the daemon's SMTP transport path
os.environ["DAEMON_SEND_ALLOWED"] = "1"

# Load .env if present
_env_path = ROOT.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k not in os.environ:
                os.environ[k] = v
QUEUE = ROOT / "queue.json"
LOG = ROOT / "send_daemon.log"
CONTACT_LOG = ROOT / "contact_log.csv"

# Bridge config
BRIDGE_HOST = os.environ.get("MM_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("MM_BRIDGE_PORT", "8787"))
BRIDGE_TOKEN = os.environ.get("MM_BRIDGE_TOKEN", "")

# Default interval between sweep cycles when running as daemon
DEFAULT_INTERVAL = 60  # seconds


def log(msg):
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.open("a").write(line + "\n")


def load_queue():
    if not QUEUE.exists():
        raise RuntimeError(f"Queue not found: {QUEUE}")
    data = json.load(QUEUE.open())
    return data


def save_queue(data):
    QUEUE.open("w").write(json.dumps(data, indent=2, ensure_ascii=False))
    QUEUE.open("a").write("\n")


def sent_today_count():
    """Count SENT entries in contact_log.csv for today."""
    if not CONTACT_LOG.exists():
        return 0
    today = datetime.date.today().isoformat()
    count = 0
    with CONTACT_LOG.open() as fh:
        for r in csv.DictReader(fh):
            if r.get("date", "").startswith(today) and r.get("status") == "SENT":
                count += 1
    return count


def record_sent_via_bridge(message_id, receipt_id):
    """Call bridge GET /record-sent?id=<message_id>&receipt=<receipt_id>."""
    if not BRIDGE_TOKEN:
        log("WARN: MM_BRIDGE_TOKEN not set — skipping DB record")
        return False
    url = (f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/record-sent"
           f"?id={message_id}&receipt={receipt_id}")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BRIDGE_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log(f"  Recorded in DB: message_id={message_id} receipt={receipt_id}")
                return True
            log(f"  Bridge record-sent skipped (non-fatal): {result.get('error')}")
            return False
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        log(f"  Bridge record-sent skipped (non-fatal): {e}")
        return False


def send_one(prospect):
    """
    Send one prospect via catalyx_send.py.
    Returns (success, message_id_or_error).
    """
    from catalyx_send import send_email

    to = prospect["address"]
    subject = prospect.get("subject", f"Quick note about the {prospect['business_name']} website")
    body = prospect.get("body", "")
    if not body:
        return False, "NO_BODY"

    log(f"  Sending to {to} — {prospect['business_name']}")
    try:
        result = send_email(to=to, subject=subject, body=body,
                            sender_name="Dion", app_pw=None)
        if result.get("ok"):
            # catalyx_send returns {ok: True, to, from} — no message id.
            # We generate a receipt id for our own tracking.
            receipt_id = int(time.time() * 1000)
            log(f"  SMTP OK — to={to} receipt={receipt_id}")
            return True, receipt_id
        return False, result.get("error", "unknown")
    except Exception as e:
        return False, str(e)[:200]


def send_prospect(prospect, data):
    """Send one prospect, update queue, record in DB, return result dict."""
    pid = prospect["id"]
    if prospect.get("sent_at"):
        return {"id": pid, "status": "already_sent", "sent_at": prospect["sent_at"]}

    daily = sent_today_count()
    cap = data.get("daily_cap", 20)
    if daily >= cap:
        log(f"  Daily cap {cap} reached (sent {daily} today) — skipping id={pid}")
        return {"id": pid, "status": "cap_reached", "daily": daily, "cap": cap}

    ok, result = send_one(prospect)
    now_iso = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    if ok:
        receipt_id = result
        # Mark as sent in queue
        prospect["sent_at"] = now_iso
        # Try to record in MM DB via bridge
        record_sent_via_bridge(pid, receipt_id)
        # Also log to contact_log.csv
        log_contact(prospect, "SENT", f"receipt={receipt_id}")
        return {"id": pid, "status": "sent", "sent_at": now_iso, "receipt": receipt_id}
    else:
        log(f"  SEND FAILED id={pid}: {result}")
        log_contact(prospect, "FAILED", result)
        return {"id": pid, "status": "failed", "error": result}


def log_contact(prospect, status, detail):
    """Append to contact_log.csv."""
    new = not CONTACT_LOG.exists()
    with CONTACT_LOG.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "address", "business", "subject", "status", "detail"])
        w.writerow([
            datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            prospect["address"],
            prospect["business_name"],
            prospect.get("subject", ""),
            status,
            detail,
        ])


def sweep(data):
    """Run one sweep: send all pending prospects. Returns summary."""
    pending = [p for p in data["prospects"] if not p.get("sent_at")]
    sent = 0
    failed = 0
    skipped = 0
    results = []

    log(f"=== Sweep: {len(pending)} pending / {len(data['prospects'])} total ===")

    for prospect in pending:
        r = send_prospect(prospect, data)
        results.append(r)
        if r["status"] == "sent":
            sent += 1
        elif r["status"] == "failed":
            failed += 1
        else:
            skipped += 1

    # Persist queue state
    save_queue(data)

    log(f"  Results: {sent} sent, {failed} failed, {skipped} skipped")
    return {"sent": sent, "failed": failed, "skipped": skipped, "results": results}


def run_daemon(interval=None):
    """Continuous loop: sweep, sleep, repeat."""
    interval = interval or DEFAULT_INTERVAL
    log(f"=== Daemon started (interval={interval}s) ===")
    data = load_queue()
    cycle = 0
    try:
        while True:
            cycle += 1
            log(f"--- Cycle {cycle} ---")
            today = datetime.date.today().isoformat()
            daily = sent_today_count()
            cap = data.get("daily_cap", 20)
            log(f"  Daily count: {daily}/{cap}")
            if daily >= cap:
                log(f"  Daily cap reached — sleeping {interval}s")
                time.sleep(interval)
                continue
            sweep(data)
            log(f"  Next sweep in {interval}s")
            time.sleep(interval)
    except KeyboardInterrupt:
        log("Daemon stopped.")


def run_selftest():
    """Send a test message to the sender address."""
    from catalyx_send import SENDER, send_email
    log("=== Self-test ===")
    result = send_email(to=SENDER, subject="Send daemon self-test",
                        body="This is an automated self-test from the send daemon.\n\nNo prospect has been contacted.",
                        sender_name="Dion")
    log(f"Result: {result}")
    return 0 if result.get("ok") else 1


def main():
    ap = argparse.ArgumentParser(description="Round-the-clock email sender daemon")
    ap.add_argument("--daemon", action="store_true", help="Run continuously")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help=f"Sweep interval in seconds (default: {DEFAULT_INTERVAL})")
    ap.add_argument("--selftest", action="store_true", help="Send a test message")
    ap.add_argument("--once", action="store_true", help="Run one sweep and exit")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    if args.daemon:
        return run_daemon(args.interval)

    # Default: one sweep
    data = load_queue()
    result = sweep(data)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
