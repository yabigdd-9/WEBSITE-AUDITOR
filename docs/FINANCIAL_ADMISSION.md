# Financial admission: isolated candidate

External model activation remains **held**. No verified account entitlement,
billing, quota or reset evidence has been supplied. This candidate does not
create a live policy, review receipt, ledger or provider request.

## Implemented boundary

`money-machine/mm_financial_admission.py` is a shared SQLite coordinator for
bounded chat-completion calls. MoneyMachine FCC calls, the direct Python FCC
bridge and the repository free-role dispatcher use it. Raw Claude/Codex agent
CLIs are held because their internal requests and billing are unbounded by this
adapter. A model's `:free` name, an environment allowlist, a zero price cap or a
green provider health response cannot replace account evidence.

The legacy `full-pipeline.py` external image function now reports held and cannot
substitute a cached image as fresh proof. Image billing is unsupported by this
chat adapter, so no image provider is enabled. The shell bridge defaults to
status and delegates inference to the admitted Python path; service start/stop
and unmetered CLI agents remain held. The complete legacy pipeline still has an
unmet `tenacity` dependency and pre-existing lint debt. Function-level image
tests do not establish full legacy CLI execution.

The control directory is `<git-common-dir>/financial-admission`. Resolving Git's
`commondir` makes primary and linked checkouts use the same accounting state.
`MM_ROOT`, provider feature flags and worker-specific databases cannot select a
different production coordinator. Tests explicitly inject temporary coordinators
and synthetic review records; no test record is an independent entitlement.

No request initializes accounting. Missing policy, receipt, marker, ledger,
schema, private ownership, exact route, output bound or valid quota window denies
dispatch. SQLite contention, corruption and uncertain accounting also deny it.
Explicit offline initialization refuses existing files/markers and never creates
an entitlement receipt. It must not be invoked against shared state by an agent
without the operator's exact approved evidence and provisioning authority.

## State transitions

1. Verify one reviewed account/window, included-zero-cost request quota, initial
   usage, exact provider/model/endpoint, output bound and receipt binding.
2. In `BEGIN IMMEDIATE`, count every reserved, dispatched, settled or unknown
   request in that window. Reserve one unit only if capacity remains.
3. Recheck policy, reservation, deadline and stop state, then durably mark the
   reservation dispatched before transport starts. A token can dispatch once.
4. Reconcile the response against exact model identity and a finite, explicit
   zero cost. A successful response consumes the reservation; it is never refunded
   merely because the answer was empty or a later workflow step failed.
5. Missing/nonzero/invalid billing, mismatched model, auth/billing/quota block or
   uncertain transport produces a persistent global hold. A new worker, runtime
   root, process or approved quota window cannot clear that hold.

A crashed reservation that was never dispatched may expire and release capacity.
A dispatched lease with no reconciled outcome becomes unknown and stops further
admission. It is never treated as a free retry. Known-zero-cost server failures
may try a separately approved and separately reserved fallback. A 429 is held;
the adapter does not guess whether an upstream quota is shared.

## Operator evidence and identity

Policy and receipt files are private, bounded, same-owner regular files; links
and duplicate fields are refused. The review receipt hash binds the policy,
account, window, limits, exact routes, reviewer and validity. Changing a policy
within an existing quota window requires independent reconciliation; it cannot
inflate the existing quota automatically. The ledger identity marker prevents
an ordinary missing-ledger event from silently creating a fresh budget.

The receipt is a trusted operator review artifact, not a cryptographic provider
attestation. Its claims still require genuine independently checked billing and
account evidence. This code cannot manufacture or authenticate that evidence.
Do not copy synthetic fixture records into the shared control directory. Do not
restore, delete, reset or replace the financial ledger along with an application
database backup. Any recovery must reconcile outstanding provider outcomes first.

## Remaining C10/C20/C30 work

- Obtain actual account-level evidence and explicit activation authority. No
  current receipt, approved policy or live financial ledger is claimed.
- Complete independent provider receipts and reconciliation against activity
  outside this repository. The current coordinator supports a single reviewed
  account/window; unrelated provider accounts must not be assumed to share it.
- Inspect and integrate installed/global Hermes and any external clients; changes
  in this checkout cannot attest or control those processes or their loaded code.
- Finish independent review, multi-account policy requirements, recovery/incident
  clearance procedures and aggregate release-gate binding before C20 is complete.
- Real hosted/provider acceptance remains held. Offline concurrency, crash and
  error tests demonstrate local behavior only; they do not grant release approval.

Contact/holdout acceptance and quote pricing also remain open: the user has no
independent labels or approved NZD hourly rate yet. These decisions are unrelated
to model eligibility and cannot be inferred from synthetic tests.
