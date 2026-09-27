# Golden evaluation workflow

`golden_cases.jsonl` holds 16 deterministic policy cases covering unsupported
email guesses, first-party email evidence, catch-all and suppression outcomes,
corroborated and conflicting identity signals including business-name/domain
derivation, all five remediation classes, and local demo behavior.

Run the current implementation against those cases with:

```sh
./mm golden-check
```

The command calls the current `mm_email` verifier and `auditor_toolkit` identity,
remediation, and demo implementations. It creates temporary local preview
artifacts for remediation/demo cases, then removes them. It does not call a
model, network, SMTP server, customer database, or target website. Its result is
current-code conformance only; it cannot show that a challenger improved over a
baseline. Cases use synthetic inputs and never represent real prospect data.

The comparative gate remains:

```sh
# In the baseline checkout:
./mm golden-predict --output /tmp/baseline-predictions.jsonl
# In the challenger checkout:
./mm golden-predict --output /tmp/challenger-predictions.jsonl
# In either evaluation checkout:
./mm challenger-eval \
  --golden evaluation/golden_cases.jsonl \
  --baseline /tmp/baseline-predictions.jsonl \
  --challenger /tmp/challenger-predictions.jsonl \
  --min-improvement 0.01
```

Run `golden-predict` from each isolated baseline/challenger checkout. Each
prediction file has an adjacent `.manifest.json` recording the golden-set,
prediction, and implementation-source hashes, case count, and safety result.
Outputs are synthetic, local-only, and never overwrite existing evidence.
Preserve the checkout revisions and comparator output with the review record.
`challenger-eval` may recommend separate integrator review; it never grants
promotion, merge, production-write, or deployment authority. A real shadow run
is still required before P18 can pass. The recorded comparison in
`runs/p7-domain-compact-comparison.json` shows a 15/16 to 16/16 result with one
synthetic identity case; it is not a production shadow run or evidence of
general business outcomes. It recommends integrator review only and grants no
promotion authority.
