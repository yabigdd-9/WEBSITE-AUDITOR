# Hermes Money Engine Agent Task Checklist

## Goal

Run the engine in a compliant, evidence-first sequence without bypassing approval gates or inventing consent.

## Hard rules

- No outbound send without human approval.
- No consent inference from publication alone.
- No final price commitment without APR-004 approval.
- No task should be marked complete without evidence in the state file or a recorded artifact.
- Use the active engine queue only after the current approval state is checked.

---

## Phase 1 — Start of run

### 1. Confirm repo state

- Read [approval/APPROVAL_QUEUE.yaml](../approval/APPROVAL_QUEUE.yaml)
- Read [state/HERMES_EXECUTION_STATE.yaml](../state/HERMES_EXECUTION_STATE.yaml)
- Read the latest report in [outputs](../outputs)
- Confirm whether the active engine is still valid

### 2. Confirm blocker status

Must be checked before any send or final pricing action:

- APR-004: pricing commitment
- APR-006: scope ratification
- APR-007: per-prospect consent ratification

If any are open, route the task to human review and do not continue to send.

---

## Phase 2 — Researcher tasks

### Researcher job

Identify and validate leads for the active engine.

### Required outputs

For each prospect, collect:

- business name
- business website
- exact contact address
- source URL
- surrounding wording
- whether the wording invites contact
- relevance to business role
- any refusal or anti-marketing statement
- evidence of the problem being real

### Completion gate

The lead is not ready until:

- the evidence is specific
- the source is public and attributable
- the problem is real and relevant
- the contact rationale is supportable

---

## Phase 3 — Judge tasks

### Judge job

Score the prospect and reject weak or generic opportunities.

### Required outputs

- strong leads only
- weak leads rejected with reason
- shortlist for next stage
- evidence pack ready for proofer

### Completion gate

Only prospects with real business pain and clear fit move forward.

---

## Phase 4 — Proofer tasks

### Proofer job

Validate the evidence and make the reasoning defensible.

### Required outputs

- fact-checked lead profile
- missing evidence flagged
- risk status recorded
- no unsupported claims in the draft

### Completion gate

No prospect is eligible for outreach if the evidence is incomplete or uncertain.

---

## Phase 5 — Consent gate / compliance

### Required check per prospect

- address exists
- address source URL exists
- surrounding wording exists
- invites_contact is assessed
- refusal_statement_present is checked
- role relevance is confirmed
- consent type claim is recorded
- human ratification is attached

### Do not proceed when

- the prospect is ambiguous
- the source page is unclear
- the contact is personal rather than role-based without a strong rationale
- there is any anti-marketing or refusal statement
- the consent basis is not ratified

---

## Phase 6 — Draft generation

### Outreach executor job

Create only approved, evidence-backed, tailored outreach.

### Required outputs

- one tailored draft per approved prospect
- truthful business problem statement
- exact relevant reason for contact
- no unverifiable claim
- approved pricing only if APR-004 is open and approved

### Completion gate

If the price or consent basis is not approved, do not draft or send.

---

## Phase 7 — Human approval gate

### Before send

The human reviewer must confirm:

- prospect-specific consent rationale
- business relevance of the outreach
- final offer/price is authorized
- the send remains within compliance policy

### Only after approval

The system may move to send.

---

## Phase 8 — Send + record

### Execution requirements

- log send outcome
- record timestamp
- record reply status
- retain source evidence
- preserve the final outbound content as a record

### Do not do

- no mass-send without approval
- no silent override of contact gate
- no rewriting of proof after send

---

## Phase 9 — Revenue and learning review

After each send batch:

- record reply status
- record revenue outcome
- identify which prospect quality signals worked
- update the state and next action
- keep the next batch grounded in actual outcomes

---

## Agent handoff summary

### Hermes Agent / Orchestrator

- owns state and approval gating
- chooses next work
- ensures no bypass of policy

### Researcher

- produces evidence pack
- finds prospects and supports the case

### Judge

- shortlists only real opportunities

### Proofer

- verifies the factual basis

### Compliance / ratifier

- confirms consent basis

### Outreach executor

- drafts only approved prospects

### Revenue reviewer

- tracks results and pricing compliance

### Backup Agent

- maintains a clean recovery snapshot before major changes
- keeps evidence and state artifacts copy-safe and reviewable
- restores the last known good state if a task fails unexpectedly
- verifies the rollback target before any destructive action

### Fast-Path Agent

- handles parallelized low-risk work such as research triage, document sorting, and evidence packaging
- does not bypass approval gates or consent checks
- escalates anything ambiguous to the orchestrator or compliance ratifier
- accelerates the queue without creating new compliance risk

### Boosted Agent

- runs the highest-confidence, low-friction work in parallel when the approval gate is already green
- handles duplicate cleanup, summarization, and structured note generation
- works only on already approved tasks and never on final sending or value commitments
- escalates anything involving money, legal risk, or unclear consent to the orchestrator

### Parallel Batch Agent

- coordinates multiple small research or validation tasks at the same time
- ensures each sub-task remains isolated and evidence-backed
- merges outputs into a single reviewed evidence pack before handoff
- does not combine blocked or ambiguous leads into the final batch

---

## Recommended next run order

1. Backup Agent snapshots repo/state before any batch starts
2. Check approval queue
3. Confirm price approval status
4. Fast-Path Agent and Parallel Batch Agent gather low-risk research sub-batches
5. Boosted Agent handles approved, low-friction parallel tasks
6. Complete research evidence pack
7. Run judge scoring
8. Run proofer review
9. Perform consent ratification
10. Build only approved outreach
11. Human approval
12. Send + log
13. Review reply and revenue outcome

This is the minimum safe operational path for the next execution cycle.
