"""Legacy output adapter for the canonical bounded email-record checker."""

from auditor_toolkit.email_auth import inspect_email_auth


def audit_email_security(url):
    observation = inspect_email_auth(url)
    return {
        "format_version": 2,
        "spf_valid": observation["spf"]["valid"],
        "dmarc_valid": observation["dmarc"]["valid"],
        "spoofing_risk": "NOT_ASSESSED",
        "status": observation["status"],
        "observation": observation,
    }
