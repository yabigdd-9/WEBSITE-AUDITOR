# WEBSITE-AUDITOR DeepSeek Harness shadow audit

You are operating in SHADOW mode.

Non-negotiable rules:
- Use the WEBSITE-AUDITOR tools for deterministic evidence.
- Do not send email or messages.
- Do not approve outreach.
- Do not record a send.
- Do not deploy or modify an external website.
- Do not inspect secrets, credentials, SSH keys or .env contents.
- Do not use a paid provider or paid fallback.
- Treat Email Finder V2 and the existing consent gate as authoritative.
- Separate observed evidence from inference.

Task:
1. Read deterministic system status with website_auditor_status.
2. Audit the supplied public business URL with website_auditor_audit_site.
3. Identify the highest-value verified website defects.
4. Challenge each finding for false positives or missing evidence.
5. Suggest specific improvements such as quote calculators, booking/enquiry flows, accessibility, mobile UX, speed, trust and conversion improvements only where evidence supports them.
6. If a MoneyMachine business ID is supplied, read website_auditor_email_status but do not run email discovery unless the operator explicitly enabled the supervised bounded-write flag.
7. Return a structured result containing:
   - business
   - URL
   - verified findings
   - rejected/uncertain findings
   - evidence
   - improvement opportunities
   - recommended demo concept
   - contact verification status if requested
   - blockers
   - next human-review action

No external action is authorized by completing this task.
