# Human-Review Boundaries

This document defines the boundaries of what must remain human review in WEBSITE-AUDITOR.

## Areas Requiring Human Review
- Final approval of audit reports before sending to customers.
- Validation of false positives in edge cases.
- Assessment of business context for prioritization.
- Remediation guidance that requires subjective judgment.
- Interpretation of complex structured data or custom implementations.
- Evaluation of accessibility issues that require manual testing.
- Determination of service-area business boundaries.
- Verification of domain ownership or authorization.
- Assessment of market context for vertical-specific businesses.
- Final decision on vulnerability exploitability.

## Areas Safe for Automation
- Technical checks with clear evidence (e.g., version detection, template matching).
- Performance metrics from automated tools (Lighthouse, CrUX).
- Technology detection via fingerprints.
- Vulnerability matching via known advisories.
- Structured data validation against schema.
- Basic identity verification (NZBN, domain, address consistency).
- Link analysis (orphan detection, redirect chains).
- Duplicate content detection via hashing or similarity.

## Process
- Automated checks produce evidence and confidence scores.
- Human review is triggered for low-confidence or ambiguous results.
- Final report includes both automated findings and human-reviewed notes.
- Customers can request additional human review for specific areas.

## Validation
- Regular audits of false positives and false negatives.
- Feedback loop from customers to improve automation.
- Periodic review of human-review boundaries as technology evolves.