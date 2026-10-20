# Pipeline validation

Discovery → entity resolution/duplicate guards → audit → qualification → evidence → demo → draft → human approval was exercised with existing deterministic unit/integration tests plus a connected synthetic loopback evidence-to-packet run. No real prospect was crawled by this assignment. Source discovery tests use injected search results; they do not establish current public-source recall or accuracy.

`evidence/discovery-qualification.txt`: 80 passed. Tests cover NZ homepage/service acceptance, directory/social/job/document filtering, ambiguous-candidate review, deterministic scoring, duplicates and evidence freshness. `evidence/database-queue.txt`: 62 passed, 2 missing legacy fixture skips.

`evidence/browser.txt`: 15 passed with real Chromium, screenshot/PDF/portal and demo/preparation tests. Sample run `20261014T144657-052d7d276c1f` completed with 18 scoped observations on the intentionally defective loopback page. Screenshot hash `512d0d28ad6c602bc653dec3699636e494181d9d51993f6a3d2c2c21802dbe3b` matches the saved PNG, which was visually inspected. The sample is explicitly fictional Canterbury plumbing content.

The existing toolkit produced `sample/remediation`, `sample/demo/index.html`, `sample/demo/demo.json`, and `sample/packet`. Demo is CONCEPT_ONLY, live_site_changed=false and improvement_claim_valid=false. No prices selected. The packet binds audit/remediation/demo by hash; no verified email or consent is asserted. A new synthetic review item is in the candidate's existing `approval/APPROVAL_QUEUE.yaml`, with a dedicated fixture queue under `approval/reliability-review`. The live approval queue was not edited.

`evidence/approval-safety.txt` validates exact approval, suppression, provider receipt, redaction and no-send gates. Sending remains disabled and the sample is outreach_eligible=false. Real-business capture quality, source recall, commercial demand and unattended production handoffs remain unproven.
