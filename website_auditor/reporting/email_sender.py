
"""
Email Sender: Sends monthly reports via SMTP.
Falls back to save-only if SMTP is not configured.
"""
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path


def send_report_email(to_email, subject, body_text, attachment_path=None, smtp_config=None):
    """Send the monthly report email with optional PDF attachment."""
    if not smtp_config:
        return {"status": "skipped", "reason": "No SMTP configuration provided"}

    host = smtp_config.get("smtp_host", "")
    port = smtp_config.get("smtp_port", 587)
    user = smtp_config.get("smtp_user", "")
    password = smtp_config.get("smtp_password", "")

    if not host or not user or not password:
        return {"status": "skipped", "reason": "SMTP credentials not configured in config/branding.yaml"}

    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "html"))

        if attachment_path and Path(attachment_path).exists():
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
                part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
                msg.attach(part)

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return {"status": "sent", "to": to_email}
    except Exception as e:
        return {"status": "error", "error": str(e)}
