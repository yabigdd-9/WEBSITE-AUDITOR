#!/usr/bin/env python3
"""CATALYX Labs outbound email sender (Gmail SMTP app-password auth).

Verified live 2026-08-18: test send team.catalyxlabs@gmail.com -> yabigdd@gmail.com OK.

Usage:
  from catalyx_send import send_email
  send_email(to="prospect@biz.co.nz", subject="...", body="...",
             sender_name="CATALYX Labs")

App password is read from macOS Keychain (service: catalyx_gmail_app_pw) — never
hard-coded here. Falls back to env CATALYX_GMAIL_APP_PW if Keychain unavailable.
Rotate the app password in Keychain if this chat is ever exposed.
"""
import os
import smtplib
import ssl
import subprocess
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SENDER = "team.catalyxlabs@gmail.com"
SENDER_NAME = "CATALYX Labs"


def _keychain_app_pw() -> str | None:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", SENDER,
             "-s", "catalyx_gmail_app_pw", "-w"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def send_email(to: str, subject: str, body: str, sender_name: str = SENDER_NAME,
               app_pw: str | None = None) -> dict:
    app_pw = app_pw or os.environ.get("CATALYX_GMAIL_APP_PW") or _keychain_app_pw()
    if not app_pw:
        raise RuntimeError("CATALYX Gmail app password not found (Keychain/env)")
    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{SENDER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(SENDER, app_pw.replace(" ", ""))
        s.send_message(msg)
    return {"ok": True, "to": to, "from": SENDER}


if __name__ == "__main__":
    import sys
    # quick self-test: python3 catalyx_send.py <to>
    t = sys.argv[1] if len(sys.argv) > 1 else SENDER
    r = send_email(t, "CATALYX Labs send-path self-test", "Self-test from catalyx_send.py")
    print(r)
