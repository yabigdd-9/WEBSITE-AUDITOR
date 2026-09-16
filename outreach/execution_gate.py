"""The audit/repair run prepares packets; no legacy transport is released."""

def require_external_release():
    raise PermissionError(
        "HUMAN_APPROVAL_REQUIRED: legacy send transports are held during the "
        "WEBSITES/BUISNESSaudits audit. A command-line flag or a generated packet "
        "cannot release sending; exact-message human approval and a separately "
        "reviewed transport integration are required."
    )
