# Automatic contact review pathway

The standalone `money-machine/mm_contact_review_pathway.py` processes a frozen
capture packet automatically. It provides machine recommendations and a worker
queue. It does not write CRM records, replace human precision labels, alter the
release gate, or send messages.

## Workers

| Worker | Input | Result |
|---|---|---|
| Scout | Frozen businesses, case metadata and raw captures | Checked hashes and acquisition errors |
| Identity | Company, domain, region and captured page signals | Strict identity result and evidence-backed name suggestions |
| Contact verifier | Original business, re-parsed pages and captured DNS | Existing `mm_email` results, using unchanged gates |
| Evidence proofer | Selected email and raw captures | Separate exact publication, contact purpose, unit, freshness and domain checks |
| Judge | All preceding results | Supported recommendation or a named worker for the exception |

The original first-party captures are re-read, checked against their SHA-256
hashes, and checked against the saved packet manifest. The source/configuration
hashes frozen with the frame must still agree at the start and end of the run.
No new network acquisition happens in capture replay. The original collection
uses the existing `email_fresh_validation` crawler and DNS checks.

The proofer uses separate publication predicates from the verifier's scoring.
This is a software cross-check; it is not independent human ground truth.
Routable DNS does not prove individual mailbox delivery.

Company-name suggestions use a prominent first-party name that agrees with the
domain stem and visible page text. They are saved separately and are never
applied to the original frozen cohort, the CRM, or its original acceptance
metrics. A domain-shaped business name may therefore still require identity
resolution. Conflicting location/unit evidence stays unresolved.

## Running the default pathway

Use the project Python 3.11 environment. From the isolated checkout:

```sh
rtk proxy /Users/dd/WEBSITE-AUDITOR/.venv/bin/python -B money-machine/mm_contact_review_pathway.py \
  --packet /absolute/path/to/frozen-contact-packet \
  --output /absolute/path/to/new-review-output
```

The input packet must include `sample.json`, `FRAME_SHA256.txt`,
`PACKET_MANIFEST.json`, `evidence/cases/`, and original page captures.
The output directory must be new and separate from the input packet. There is
a lock against simultaneous reviews of the same packet. No supervisor,
controller, collector, or live service is started or restarted.

Outputs: `SUMMARY.json`, per-case worker receipts, `RECOMMENDATIONS.json`,
`EXCEPTIONS.json`, `WORKER_ASSIGNMENTS.json`, an offline `REVIEW.html`, a source
snapshot and a hash manifest. No release or precision receipt is generated.

## Optional AI advisor

`--free-ai-advice` explicitly opts in to one bounded request through the existing
`mm_model_router`: certified free FCC, then its verified free Hermes role route.
The request uses the orchestrator role and passes only case IDs, routing codes
and required worker names. It does not pass email addresses, company names,
page content, private records or human labels.

The advisor can suggest assignments from the fixed worker registry. An
assignment is accepted only when it agrees with the judge's required worker.
It cannot invent executable workers, run commands, change rules, select a
contact, clear rejection/suppression, or authorize sending. Route failure stops
the optional advisor invocation; there is no paid upgrade or repeated spawn.

The default invocation calls no model. General automatic model execution stays
disabled in the existing routing configuration. The initial captured-data run
did not exercise an AI endpoint, and its availability is unproven.

## Automatic supervisor connection

The existing supervisor calls `mm_recurring_contact_review.tick` after each
pipeline cycle commits. The tick is quick: one owned child does the review
without blocking supervisor heartbeats. No second supervisor or launchd job
is installed.

The worker reads non-dummy, unsuppressed businesses in `IDENTITY_PENDING`,
`CONTACT_PENDING` or `NEEDS_REVIEW`. It excludes rejected businesses. Results
and worker assignments are written separately under `state/contact-review`.
It never transitions an item, opens an email release gate, or approves sending.

The schedule scans every 60 seconds, handles at most two businesses per job,
and refreshes an unchanged business after 24 hours. Changes to recorded
identity, pipeline state or the review implementation trigger another review.
Each child has a 180-second deadline, a shared ownership lock, and bounded
page/DNS collection. Interrupted cases are saved as incomplete and receive
a refresh cooldown. Previous reviews are retained with the job record.

Optional seed packets are listed with their manifest hashes in the local,
ignored `state/contact-review-policy.json`. A matching case with page/DNS
evidence no more than 24 hours old can be reused. Otherwise the worker uses
the existing public GET/DNS crawler, respects robots restrictions, and saves
fresh captures. No paid provider, model, SMTP message or form submission is
used. Unknown telemetry or acquisition failures become exceptions.

The manual capture-replay CLI can also inspect already-rejected businesses;
its recommendations preserve that state and grant no requeue authority. The
automatic supervisor path only reads currently eligible waiting states.

Human precision review, release policy and exact-item send permission remain
separate. AI agreement cannot produce a human label. Existing user labels are
left in their original append-only review records.

No regression tests were added or run for this implementation request. The
standalone pathway was executed against the existing 25-case packet. Runtime
activation evidence is saved separately; these machine recommendations do not
replace the completed historical soak or independent precision acceptance.
