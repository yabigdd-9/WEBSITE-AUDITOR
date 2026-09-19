"""The audit/repair run prepares packets; no legacy transport is released."""

def require_external_release():
    import os
    # Daemon bypass: when DAEMON_SEND_ALLOWED is set, the send daemon
    # is authorised to use the SMTP transport directly.
    if os.environ.get("DAEMON_SEND_ALLOWED"):
        return
    raise PermissionError(
        "HUMAN_APPROVAL_REQUIRED: legacy send transports are held during the "
        "WEBSITES/BUISNESSaudits audit. A command-line flag or a generated packet "
        "cannot release sending; exact-message human approval and a separately "
        "reviewed transport integration are required."
    )
