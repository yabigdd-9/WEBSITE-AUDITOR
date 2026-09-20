import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

class ComplianceGate:
    """Ensures outreach is lawful before any send."""

    BLOCKED_WORDS = ["guaranteed", "act now", "free money", "urgent reply required"]
    REQUIRED_ELEMENTS = ["sender_identity", "opt_out", "physical_address"]

    def check_draft(self, draft):
        issues = []
        text = (draft.get("subject", "") + " " + draft.get("body", "")).lower()

        for word in self.BLOCKED_WORDS:
            if word in text:
                issues.append(f"Spam trigger word: '{word}'")

        for element in self.REQUIRED_ELEMENTS:
            if element not in draft:
                issues.append(f"Missing required element: {element}")

        if not draft.get("lawful_basis"):
            issues.append("No lawful basis recorded")

        if not draft.get("suppression_checked"):
            issues.append("Suppression list not checked")

        return {"passed": len(issues) == 0, "issues": issues}


class OutreachEngine:
    """Generates evidence-based outreach drafts. Sending is blocked by default."""

    def __init__(self, output_dir="outputs/outreach"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.compliance = ComplianceGate()
        self.suppression_path = self.output_dir / "suppression.jsonl"

    def load_suppression(self):
        if not self.suppression_path.exists():
            return set()
        emails = set()
        for line in self.suppression_path.read_text().splitlines():
            if line.strip():
                emails.add(json.loads(line).get("email_hash", ""))
        return emails

    def is_suppressed(self, email):
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        return email_hash in self.load_suppression()

    def generate_draft(self, domain, defects, contact_email=None):
        """Generate a personalized, evidence-based outreach draft."""
        top_defect = defects[0] if defects else {"issue": "website health issues"}
        issue_text = top_defect.get("issue", str(top_defect))

        subject = f"Quick note about {domain}"
        body = f"""Hi,

I ran a free website audit on {domain} and noticed:

• {issue_text}

This may affect how visitors trust and find your site. There are quick fixes (most under 30 minutes).

Happy to send the full evidence-backed report if useful — no obligation.

Regards,
[Your Name]
[Agency Name]
[Physical Address]

---
Reply STOP to opt out. We respect your inbox.
"""

        draft = {
            "domain": domain,
            "to": contact_email or f"info@{domain}",
            "subject": subject,
            "body": body,
            "sender_identity": "[Your Name] - [Agency Name]",
            "opt_out": "Reply STOP to opt out",
            "physical_address": "[Your Business Address]",
            "lawful_basis": "legitimate_interest_b2b_nz",
            "suppression_checked": True,
            "evidence_refs": [str(d) for d in defects[:3]],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "draft",
        }

        # Compliance check
        compliance_result = self.compliance.check_draft(draft)
        draft["compliance"] = compliance_result

        if self.is_suppressed(draft["to"]):
            draft["status"] = "suppressed"
            draft["compliance"]["passed"] = False
            draft["compliance"]["issues"].append("Recipient is on suppression list")

        return draft

    def save_draft(self, draft):
        draft_id = hashlib.sha256(
            f"{draft['domain']}:{draft['to']}:{draft['generated_at']}".encode()
        ).hexdigest()[:12]
        path = self.output_dir / f"draft_{draft_id}.json"
        path.write_text(json.dumps(draft, indent=2))
        return path

    def send_draft(self, draft_id):
        """BLOCKED by default. Policy engine must explicitly allow."""
        return {
            "status": "blocked",
            "reason": "Outreach sending is disabled by policy. Set allow_external_emails=true and provide ESP credentials to enable.",
        }
