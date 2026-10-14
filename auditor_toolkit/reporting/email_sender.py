"""
Draft-only email compatibility layer.

External SMTP dispatch is intentionally disabled. Reports may be
prepared for operator review, but this function performs no network I/O.
"""

def send_report_email(
    to_email,
    subject,
    body_text,
    attachment_path=None,
    smtp_config=None,
):
    """Prepare delivery metadata without transmitting anything."""
    return {
        "status": "draft",
        "sent": False,
        "to": to_email,
        "subject": subject,
        "attachment": str(attachment_path) if attachment_path else None,
        "reason": "External email dispatch is disabled; draft-only mode",
    }
