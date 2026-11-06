# Historical security review reconciliation — 22 October 2026

The retained historical scan summary and its triage inventory match exactly as multisets: **87 scanner inputs, 87 triage records**. Duplicate-looking observations are retained individually. The original historical verdicts are **71 not_actionable and 16 needs_review**. This is a provenance reconciliation, not a new security scan or a new clearance decision.

The 16 holds comprise 14 captured Maps-key observations, one documentation test-key example and one captured form token. These are classifications from the existing review context, not proof that the values are active credentials.

At frozen revision `7c44c9143aea7947f28c3bf13914b70ed4fa1b12`, 12 of the 16 held observations reference tracked blobs that still contain their exact historical source line. Four are absent from the current tracked tree. Removal from the current tree does not erase history or establish that a credential is inactive. No credential values, source lines or captured page content were copied into these deliverables.

| Review ID | Category | Tracked file present | Historical line remains | Owner/restrictions |
| --- | --- | --- | --- |
| triage-007 | documentation_test_key_example | No | No | Not verified |
| triage-044 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-047 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-049 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-050 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-058 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-060 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-061 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-062 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-066 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-068 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-069 | captured_maps_key_observation | Yes | Yes | Not verified |
| triage-083 | captured_form_token | Yes | Yes | Not verified |
| triage-085 | captured_maps_key_observation | No | No | Not verified |
| triage-086 | captured_maps_key_observation | No | No | Not verified |
| triage-087 | captured_maps_key_observation | No | No | Not verified |

What remains to close the security gate:

1. Establish the appropriate owner and intended purpose for each observation. A token captured from a third-party page must not be treated as a credential we own.
2. Review restrictions and active exposure using appropriate owner-provided evidence. Do not infer this from token format, static presence or a successful local test.
3. Record a specific remediation decision or an evidence-backed no-action decision, with who reviewed it and when. The supplied template has null decisions and cannot authorize sending or configuration changes.
4. For any confirmed owned exposure, obtain exact remediation/rotation authorization and retain verification evidence. No rotations, validation requests or history rewriting were performed.
5. Reconcile any separately scoped later inventories before treating their counts as replacements. The 87-input historical scan exited 1; this reconciliation does not turn it into a clean scan or claim a fresh full-history scan. Current CI checks cover their own configured scope.

[Reconciliation receipt and source fingerprints](historical-security-reconciliation.json) · [Blank owner-review template](historical-security-owner-review-template.json)

The original source records remain unchanged. The repository, runtime configuration, approval queue and suppression state were not modified.
