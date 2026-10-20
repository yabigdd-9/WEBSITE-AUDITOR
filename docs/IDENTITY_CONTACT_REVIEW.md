# Identity and contact review commands

These commands operate on an existing `email_fresh_validation.py` capture directory. They do not access the network, call models, update databases, select production contacts, create release receipts, or send messages.

## 1. Prepare trading-name proposals

```sh
wa identity-review outputs/contact-pilot/captures --output outputs/contact-pilot/name-proposals.json
```

The current workspace bounds all input and output paths. The capture directory must contain `cases/*.json` and content-addressed files under `cache/email-v2`. Between one and fifty cases are supported; each case may reference at most five pages. JSON and response byte limits match the bounded collector.

The command verifies response hashes and checks that page URLs share the recorded business website's registered domain. It extracts organisation names directly from captured JSON-LD, rather than trusting prior result metadata. A name proposal requires a domain placeholder as the current name, no supplied trading name, one observed organisation name, two distinct URL/response captures containing that name, and a title or H1 match. Any invalid evidence holds the proposal. Conflicting or insufficient evidence remains for human review.

Local checksums bind evidence; they do not authenticate the business or website. Proposed names must not be treated as independent truth labels or approved CRM corrections.

## 2. Freeze predictions and evidence before independent labeling

```sh
wa freeze-contact-review outputs/contact-pilot/frame.json outputs/contact-pilot/captures --output outputs/contact-pilot/frozen-dataset.json
```

The output must be new and outside the capture directory. Each frozen case checksum binds its original prediction, business metadata and captured evidence references. Keep the frame, dataset and cases unchanged during review.

The review export must contain the exact `frame_sha256` and `frozen_dataset_sha256`, a reviewer name, ISO review date, an explicit `independent_human_review_attested: true`, and every frame case, including unresolved cases. Each case has:

- `case_id`
- `confirmed_business_name`
- `identity_label`: blank, `CONFIRMED`, `WRONG_BUSINESS`, or `UNRESOLVED`
- `publicly_attributable_emails`: newline-separated addresses, or blank
- `no_email_or_unresolved_reason`
- `evidence_references`

The human-facing review page omits engine predictions. Inspect the evidence before viewing predictions. Public attribution is distinct from deliverability and permission to contact someone. Independence is a reviewer declaration, not authentication by this command.

## 3. Compare the completed or partial review

```sh
wa contact-review outputs/contact-pilot/frame.json outputs/contact-pilot/captures outputs/contact-pilot/independent-contact-review.json --dataset outputs/contact-pilot/frozen-dataset.json --output outputs/contact-pilot/review-comparison.json
```

The comparison rejects changed evidence/predictions, frame mismatches, missing cases, duplicate cases, malformed labels and invalid evidence. Resolved labels need evidence references. Confirmed identities need a business name; confirmed no-email cases need a reason. Wrong or unresolved identities also need a reason.

The report counts true/false positives only among resolved original selections. Unresolved selections remain explicitly counted. Precision is undefined with no reviewed selections; a Wilson interval accompanies measured sample precision. A newest-first pilot does not establish population precision or a certified independent holdout.

The report never unlocks production contacts, authenticates reviewers, creates an email release receipt or grants outreach permission. Partial labels remain incomplete. Even a fully recorded review leaves contact policy unchanged.

## Candidate status

This implementation was prepared in a separate worktree while the canonical checkout remained under soak. The identity command and freeze command were executed on the existing 25-case capture set. Scoped lint passed. No tests were added or run in this step. The label-comparison command has not been exercised with an authentic human review export. Source promotion and regression validation remain pending.
