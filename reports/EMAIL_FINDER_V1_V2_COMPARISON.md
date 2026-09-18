# V1 / V2 shadow comparison

Read-only replay of all 18 real prospects; no outreach, approvals or CRM changes.

V1 consists of preserved historical DB/report addresses. No executable historical finder exists to rerun. V2 uses frozen public captures and dated DNS. Report confidence is not mailbox verification.

| Business | V1 recorded address(es) | V2 selected | Reason |
|---|---|---|---|
| Blizzard HVAC & Electrical | info@blizzard.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Trident Electrical & Air Conditioning | info@trident.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| ATL Heat Pumps | info@atlelectrical.co.nz | NO_VERIFIED_EMAIL | Suppression preserved |
| Heat Force | info@heatforce.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| BA Heat Pumps | office@baheatpumps.co.nz, quotes@baheatpumps.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| AES | yes@aes.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Simpson Climate Control | ben@simpsoncc.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Kiwi Heat Pumps | jason@kiwiheatpumps.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Imperial HVAC | None recorded | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| New Zealand Heat Pumps | None recorded | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Superior Renovations | None recorded | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Christchurch Renovations | hello@chchrenovations.nz | NO_VERIFIED_EMAIL | Suppression preserved |
| Butterfield Bathrooms | design@butterfield.co.nz | NO_VERIFIED_EMAIL | Suppression preserved |
| Evoke Renovations | aw@evoke-reno.co.nz | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Modern Age Kitchens | None recorded | NO_VERIFIED_EMAIL | Business name not confirmed in title/headings/organization; Business name not confirmed in visible page text; Location/phone/address/structured corroboration missing; Third-party or unrecognized domain |
| Kitchen Studio Christchurch | None recorded | NO_VERIFIED_EMAIL | Multiple branches: exact branch association requires review |
| Best Nest Building Co | None recorded | NO_VERIFIED_EMAIL | Only VERIFIED_HIGH addresses are eligible; role relevance determines selection |
| Fendalton Construction | None recorded | NO_VERIFIED_EMAIL | Recorded region conflicts with site location evidence |

## Measured results

```json
{
  "prospects_discovered": 18,
  "domains_identified": 15,
  "domain_identity_failures": 3,
  "raw_emails_observed": 103,
  "candidates_generated": 0,
  "verified_high": 0,
  "verified_medium": 0,
  "rejected": 2,
  "suppressed": 3,
  "no_verified_email": 18,
  "catch_all_domains": 0,
  "smtp_hard_rejects": 0,
  "third_party_only_candidates": 0,
  "vendor_developer_emails_rejected": 0,
  "duplicate_emails": 83,
  "stale_evidence_count": 16,
  "selected_email_count": 0,
  "true_positive": 0,
  "false_positive": 0,
  "golden_publicly_confirmed_emails": 15,
  "eligible_public_emails": 12,
  "old_supported_emails": 12,
  "old_total_reported_emails": 12,
  "old_unknown_emails": 0,
  "unsupported_guesses_promoted": 0,
  "external_sends": 0,
  "model_calls": 0,
  "paid_inference_cost": 0,
  "precision": null,
  "false_positive_rate": null,
  "recall_all_public_emails": 0.0,
  "recall_eligible_public_emails": 0.0,
  "average_evidence_sources_per_selected_email": 0,
  "catch_all_unknown_domains": 13,
  "smtp_probed_mailboxes": 0,
  "new_prospects_discovered": 0
}
```

## Interpretation

Precision is for every VERIFIED_HIGH candidate, not just the one selected per business. Suppressed businesses contribute no high contacts. Recall is reported both over all public addresses and after excluding suppressed businesses. Unknown/ambiguous truth is never treated as correct. Synthetic regressions are excluded from all real-business accuracy numbers.

The existing historical selected addresses are mostly publicly attributable; this sample does not establish the user-reported overall high false-positive rate. The reproduced V1 flaw and live placeholder/fragment captures demonstrate why the old admission policy is unsafe. Do not invent a before/after delivery improvement.

See `EMAIL_FINDER_METRICS.json` for per-address reasons, provenance, raw observations, score components, catch-all/SMTP uncertainty and exact benchmark hashes.

## Limitations

- 18 businesses, not 100; existing database is insufficient for 100.
- Three unknown/ambiguous businesses; no invented expected answers.
- No known wrong-person historical raw capture; synthetic tests cover it.
- No verified real free-mail case in existing population; controlled regression tests cover it.
- Golden set used once as evaluation; weights fixed using separate synthetic policy cases, not optimized for these names.
- V1 is the retained legacy output, not a rerun of an unavailable historical LLM finder.
- Public attribution benchmark does not measure live mailbox delivery. SMTP is not probed.
