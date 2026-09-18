# Hunter.io Email Verifier Cross-Check Report

**Generated:** 2026-09-18T16:14:17.911498+00:00
**Total VERIFIED_HIGH emails:** 12

## Summary

| Category | Count |
|----------|-------|
| ✅ Agree (deliverable) | 10 |
| ❌ Disagree (undeliverable) | 0 |
| ⚠️ Risky | 1 |
| ⏳ Pending (Hunter 202) | 1 |

**Agreement rate:** 100.0% (10/10) — among emails Hunter returned a definitive result, all agree with our VERIFIED_HIGH label.

## Detailed Results

| Email | Business | Our Label | Hunter Result | Score | SMTP | Disposable | Block | Agreement |
|-------|----------|-----------|---------------|-------|------|------------|-------|-----------|
| yes@aes.nz | AES | VERIFIED_HIGH | deliverable | 92 | ✅ | No | No | ✅ AGREE |
| office@baheatpumps.co.nz | BA Heat Pumps | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| quotes@baheatpumps.co.nz | BA Heat Pumps | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| luke@bestnestbuilding.co.nz | Best Nest Building Co | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| info@blizzard.co.nz | Blizzard HVAC & Electrical | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| aw@evoke-reno.co.nz | Evoke Renovations | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| info@heatforce.co.nz | Heat Force | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| info@imperialhvac.co.nz | Imperial HVAC | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| jason@kiwiheatpumps.co.nz | Kiwi Heat Pumps | VERIFIED_HIGH | pending | N/A | N/A | N/A | N/A | ⏳ PENDING |
| ben@simpsoncc.co.nz | Simpson Climate Control | VERIFIED_HIGH | deliverable | 90 | ✅ | No | No | ✅ AGREE |
| admin@superiorrenovations.co.nz | Superior Renovations | VERIFIED_HIGH | deliverable | 100 | ✅ | No | No | ✅ AGREE |
| info@trident.nz | Trident Electrical & Air Conditioning | VERIFIED_HIGH | risky | 81 | ✅ | No | No | ⚠️ RISKY |

## ⚠️ Risky Emails

Hunter flagged these as risky — proceed with caution.

- **info@trident.nz** (Trident Electrical & Air Conditioning) — Hunter score: 81

## ⏳ Pending Verifications

These emails timed out or received HTTP 202 (verification in progress) from Hunter.io. Manual follow-up needed.

- **jason@kiwiheatpumps.co.nz** (Kiwi Heat Pumps) — Hunter returned HTTP 202 after multiple retries. SMTP server is reachable (verified via direct connection).

## Methodology

- Hunter.io email_verifier endpoint called for each VERIFIED_HIGH email
- Results cached in `.cache/hunter/` for 24 hours
- Agreement: "deliverable" = AGREE, "undeliverable" = DISAGREE, "risky" = RISKY, "unknown" = UNKNOWN
- Retry with 30s timeout for initial timeouts
