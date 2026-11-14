# Proposed implementation batch for the human integration owner

This is a proposal, not a populated shared source-ownership register or approval
to modify production. Codex continues on `agents/codex-r00`; Opus's source and
branch remain untouched. Integrate accepted commits sequentially, never by an
automatic merge from this worktree.

## First: reconcile the existing candidate

Candidate `a365d6b1ed301cb85d5ade58aa2ae042aa693fcd` already changes seventeen
files around runner locking/deadlines, screenshot provenance, outreach approval
preservation, reporting and router cost responses. The integrator must decide
its disposition before assigning those paths for another patch. Its historical
green checks do not validate this baseline or its live runtime.

## A10-1 — extend existing runtime identity receipts

- Proposed sole source writer: Codex.
- Exact proposed files: `money-machine/runtime_bootstrap.py` and
  `money-machine/test_runtime_bootstrap.py`; evidence stays in `evidence/codex/`.
- Reuse the existing opt-in bootstrap and checked import loader. Do not create a
  second supervisor, scheduler or mandatory platform service.
- Extend identity to explicit DB target, approved configuration fingerprints and
  source/process context. Missing evidence stays UNKNOWN and denies acceptance;
  disk Git HEAD alone never becomes a live-process attestation.
- Tests use a disposable Git repository, synthetic configs/DB paths and owned
  subprocesses. Cover wrong SHA, wrong configuration, unexpected DB target,
  duplicate/stale process metadata and source/import drift.
- Dependencies: R00, reviewed R01 mapping, explicit exclusive assignment of these
  two files, and the integrator's approved receipt/manifest contract.
- No launchd/config changes, service restart, production execution or provider
  invocation is included. Actual live attestation requires a later approved
  activation; preserve UNKNOWN for existing unattested processes.

## C20/C30 — shared financial admission

- Proposed owner: Codex after C10 and R01 acceptance.
- Existing boundary: `money-machine/mm_model_router.py`; deterministic tests
  currently live in `money-machine/test_pipeline.py`. These overlap a365d6b1 and
  must not be edited until the integrator resolves that candidate.
- Cover every observed global Hermes, direct FCC and fallback call site, rather
  than claiming complete protection from a MoneyMachine-only response latch.
- Shared atomic reservations precede dispatch; unknown/nonzero cost, missing
  quota telemetry, exhausted capacity, races and uncertain outcomes deny or
  defer. Retries and flags cannot bypass the gate.
- C10 entitlement evidence and global-config ownership are missing. No external
  route activation, billing probe, credit purchase or shared config change is
  authorized by this proposal.

## S30/E10 — preventative controls and fake-transport acceptance

- S30 depends on Opus S10 findings and assigned CI/security-test files.
- E10 depends on the actual outbound call graph and exact ownership of transport
  tests. Reuse `mm_transport`, approval state and existing fake-network tests.
- Test exact message approval, suppression precedence, persistent emergency
  stops, restart/retry refusal and unknown delivery reconciliation. No real SMTP,
  API sends, recipient contact or production schema migration.

## Remaining human and independent gates

The existing no-send and NZ$0 constraints remain active. S20 rotation scope,
24h/72h G30 soaks, G40 pinned production canary and G50 recipient/message sends
need their specific evidence and separate approvals. The user owns integration;
Codex submits commits, changed-file summaries and receipts without merging.
