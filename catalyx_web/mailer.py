"""Explicit SMTP delivery for account verification and password recovery."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

from .security import valid_email_address


class MailConfigurationError(ValueError):
    """The configured account-mail transport is incomplete or unsafe."""


class MailDeliveryError(RuntimeError):
    """An account message could not be delivered."""


def _server_tls_context() -> ssl.SSLContext:
    """Create a TLS client context with certificate and hostname checks enabled."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def smtp_configuration(environ=None) -> dict[str, str | int]:
    """Validate SMTP settings without opening a network connection."""
    values = os.environ if environ is None else environ
    host = values.get("CATALYX_SMTP_HOST", "").strip()
    username = values.get("CATALYX_SMTP_USERNAME", "").strip()
    password = values.get("CATALYX_SMTP_PASSWORD", "")
    sender = values.get("CATALYX_SMTP_FROM", "").strip()
    try:
        port = int(values.get("CATALYX_SMTP_PORT", "587"))
    except ValueError:
        raise MailConfigurationError("CATALYX_SMTP_PORT must be 465 or 587.") from None
    parsed_sender = parseaddr(sender)[1]
    if (
        not host
        or len(host) > 253
        or any(char.isspace() for char in host)
        or port not in {465, 587}
        or not username
        or not password
        or "\r" in username
        or "\n" in username
        or "\r" in sender
        or "\n" in sender
        or not valid_email_address(parsed_sender)
    ):
        raise MailConfigurationError(
            "SMTP requires a host, port 465 or 587, username, password, and valid sender address."
        )
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
    }


def send_account_link(recipient: str, kind: str, link: str, *, environ=None) -> None:
    """Send a single account security link using authenticated TLS SMTP."""
    values = os.environ if environ is None else environ
    if values.get("CATALYX_EXTERNAL_SEND_ALLOWED", "false").strip().lower() != "true":
        raise MailConfigurationError("External account email delivery is disabled.")
    if kind == "email_verification":
        subject = "Confirm your CatalyxLabs Website Auditor email"
        explanation = "Use this one-time link to confirm your email address:"
        expiry = "60 minutes"
    elif kind == "password_reset":
        subject = "Reset your CatalyxLabs Website Auditor password"
        explanation = "Use this one-time link to reset your password:"
        expiry = "30 minutes"
    else:
        raise ValueError("Unsupported account message type.")
    if not valid_email_address(recipient) or "\r" in link or "\n" in link:
        raise ValueError("Account message data is invalid.")

    settings = smtp_configuration(values)
    message = EmailMessage()
    message["From"] = settings["sender"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        "Hello,\n\n" + explanation + "\n\n" + link
        + "\n\nIf you did not request this, you can ignore this message. "
        + "The link expires after " + expiry + ".\n"
    )

    try:
        if settings["port"] == 465:
            with smtplib.SMTP_SSL(
                settings["host"], settings["port"], timeout=10,
                context=_server_tls_context(),
            ) as server:
                server.login(settings["username"], settings["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(settings["host"], settings["port"], timeout=10) as server:
                server.ehlo()
                server.starttls(context=_server_tls_context())
                server.ehlo()
                server.login(settings["username"], settings["password"])
                server.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise MailDeliveryError("The account message could not be delivered.") from None
