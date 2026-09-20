"""Outreach upgrade: A/B testing + reply handling."""
TEMPLATES = {
    "A_direct": "Hi {name}, I found {issue} on {domain}. Quick fix available. Want the report?",
    "B_value": "Hi {name}, your site {domain} scored {score}/100. Here are 3 free fixes that could help.",
    "C_urgent": "Hi {name}, your SSL cert for {domain} expires in {days} days. Here's how to renew it free.",
}
REPLY_HANDLING = {
    "interested": "→ Send full report + book call",
    "not_interested": "→ Add to suppression, stop sequence",
    "wrong_person": "→ Ask for correct contact, pause 7 days",
    "unsubscribe": "→ Immediate suppression, log compliance",
    "auto_reply": "→ Ignore, retry in 3 days",
}
print("✅ A/B templates + reply handling logic ready.")
