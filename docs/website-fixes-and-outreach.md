# Website fix packet and outreach preflight

## Concrete website change prepared

`deliverables/site-fixes/davidrobertson-homepage/` contains a 142-character
homepage description, its HTML tag, a scoped manifest and CMS/source application
and rollback instructions. It is based on the independent page-level source
checks recorded on 2026-11-16. The checked service pages already have usable
standard descriptions, so the packet does not replace them. Existing Open Graph
metadata is left intact. This packet is proposed, not deployed or verified fixed.

Production application requires the relevant site's source/CMS access and its
owner's authorization. Access to WEBSITE-AUDITOR does not provide access to the
third-party websites it audits. No third-party site has been changed by this PR.

## Outreach correction

The old written ratification table disagreed with the JSON: the latter contains
owner ratification for all nine historical records, but includes explicitly
inferred addresses and old defect claims. Ratification is preserved; it does
not turn a guessed address into a directly observed one.

`outreach/consent_gate.py` now requires inferred-consent records to include
`address_verified=true` and the exact email in `surrounding_wording`. A provenance
note explicitly stating that an address was inferred/unconfirmed also blocks.
The normal refusal, relevance, human ratification, suppression and frequency
checks remain in place. This requirement applies to the legacy draft path too;
none of the nine old records is automatically upgraded or sent.

`scripts/cloud_outreach_preflight.py` adds read-only review checks for:

- Active/suppressed target status from the current cloud intake.
- Directly observed recipient, matching own-site HTTPS source and current source
  check timestamp. Thirty-day freshness is an operational review threshold, not
  a legal statement about consent expiry; prior ratification is not removed.
- Current finding IDs, observed confidence, successful evidence checks and
  independent verification. Historical defect labels cannot substitute for them.
- Real sender identity/contact details, verified unsubscribe, and exact-message
  approval matching the supplied body hash.

It reports `candidate_review_ready` only; it always reports `send_enabled=false`
and performs zero network operations. It neither composes nor approves email,
changes consent, contacts businesses, nor releases legacy transport. Existing
transport remains disabled, provider none, cap zero. This is prerequisite review
logic, not a production SMTP/Gmail adapter or an end-to-end delivery test.

Run an aggregate review without exposing addresses or message content:

```bash
python -m scripts.cloud_outreach_preflight --legacy-review
python outreach/consent_gate.py --selftest
```

At implementation time: nine legacy records were blocked. Required remaining
inputs include site owner/source/CMS access; selected sender account and verified
contact details; current recipient publication evidence; current verified finding
references; exact copy review; and functioning unsubscribe/provider integration.
Connected Gmail accounts have not been selected or used to create/send drafts.
Do not copy unrelated CATALYX brand configuration into website-audit outreach.

## Verification

Seven meaningful preflight tests cover ratified-but-guessed recipients,
contradictory provenance, stale defect claims, suppression, exact approval,
freshness, unsubscribe and the no-send invariant. Combined with queue/outcome/
checkpoint tests, 31 tests passed locally. All six consent selftests passed.
The static HTML was parsed to verify exactly one approved standard description
and its 120–155 character scope. No live modification, send or paid call occurred.
