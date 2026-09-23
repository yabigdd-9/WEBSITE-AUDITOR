# Expected Confidence States

This document defines the expected confidence states for various audit checks.

## Confidence States
- TECHNOLOGY_DETECTED: Technology fingerprint found but version unknown.
- VERSION_INFERRED: Version inferred from indirect evidence (e.g., comments, metadata).
- VERSION_CONFIRMED: Version confirmed via direct evidence (e.g., version header, file hash).
- VULNERABILITY_CANDIDATE: Technology and version match a known vulnerability advisory.
- VULNERABILITY_SUPPORTED: Vulnerability is supported by evidence (e.g., exploit attempt, advisory match).
- KNOWN_EXPLOITED_CONTEXT: Vulnerability is listed in CISA KEV or similar exploited list.

## Usage
Each check should output a confidence state along with a numeric confidence score (0-100).
The confidence state provides categorical context for the score.

## Validation
- Validate confidence states with manual review of sample checks.
- Ensure consistency across similar technologies and vulnerabilities.