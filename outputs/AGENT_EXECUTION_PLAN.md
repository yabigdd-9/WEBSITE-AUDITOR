# Hermes Money Engine Audit + Agent Execution Plan

## 1. Executive audit

### Current status

The repo is in a credible operating state, but it is not yet fully polished for autonomous agent execution.

What is working well:

- The system has a defined operating model and strong anti-risk guardrails in [money-machine/HERMES_MONEY_MACHINE_MASTER_PLAN.md](../money-machine/HERMES_MONEY_MACHINE_MASTER_PLAN.md).
- The execution state is tracked in [state/HERMES_EXECUTION_STATE.yaml](../state/HERMES_EXECUTION_STATE.yaml).
- Approval gating is explicit in [approval/APPROVAL_QUEUE.yaml](../approval/APPROVAL_QUEUE.yaml).
- The legal/compliance risk path is documented carefully in [outreach/COMPLIANCE_BASIS.md](../outreach/COMPLIANCE_BASIS.md).
- The UEMA consent gate is implemented and enforced in [outreach/consent_gate.py](../outreach/consent_gate.py).
- The send path and operational constraints are documented in [outreach/send.py](../outreach/send.py).

The key operational reality is this:

- The system is not blocked by lack of technical capability.
- It is blocked by human approval and missing per-prospect consent evidence.
- The repo still needs a polish pass so the agents can execute in a cleaner, more deterministic way.

### What is already complete

From the project state and report files:

- The project has extracted and scored the portfolio.
- Three active engines are in play.
- The consent gate is implemented and proven to block unsafe sends.
- Gmail send capability is technically available via OAuth.
- The state file clearly shows the repo is at a controlled "ready for next human approval" stage.

### What is not clean yet

The main problems are process and clarity, not product absence:

1. Reporting drift
   - The daily report still describes some tasks as not run, while the execution state already records those tasks as completed or in progress.
   - This creates uncertainty for any agent starting work in the repo.

2. Decision ambiguity
   - The approval queue still contains open pricing and ratification items, which means the agent plan must respect human gating.

3. Lack of a single operational playbook for agents
   - The repo has role guidance, but no concise execution schedule for the actual agents to follow in sequence.

4. Execution plan is not yet layered by agent responsibility
   - Research, proof, compliance, outreach, and final approval are all logically present, but they need to be sequenced as a clear machine-readable flow.

---

## 2. Audit findings by area

### A. Governance and approvals

The critical source of truth is [approval/APPROVAL_QUEUE.yaml](../approval/APPROVAL_QUEUE.yaml).

Current gate status:

- APR-004: pricing commitment is still open
- APR-006: scope ratification is still open
- APR-007: per-prospect consent ratification is still open
- APR-005 is marked resolved by Dion, but the consent basis still requires proof at the prospect level before sending

This means the operational rule is:

- Research and drafting can continue.
- Any actual sending requires explicit human sign-off and recorded consent evidence.

### B. State and execution tracking

The strongest current signal is [state/HERMES_EXECUTION_STATE.yaml](../state/HERMES_EXECUTION_STATE.yaml).

This file shows:

- execution phase is tracked
- active tasks are listed
- completed tasks are recorded
- retry queue is empty
- next action is clear

This is a good foundation. The improvement needed is to make the execution queue more agent-friendly and less dependent on reading multiple files.

### C. Risk and compliance

The compliance layer is mature:

- [outreach/COMPLIANCE_BASIS.md](../outreach/COMPLIANCE_BASIS.md) is strong and explicit
- [outreach/consent_gate.py](../outreach/consent_gate.py) enforces default-deny logic
- [money-machine/HERMES_MONEY_MACHINE_MASTER_PLAN.md](../money-machine/HERMES_MONEY_MACHINE_MASTER_PLAN.md) reinforces the no-paid-model default and no-destructive-action rule

This is the right posture for a real business engine. The only remaining risk is not technical capability, but legal/operational proof quality at the prospect level.

### D. Output quality and polish

The project needs a polish pass to reduce drift between files:

- [outputs/DAILY_OPERATOR_REPORT_2026-08-18.md](../outputs/DAILY_OPERATOR_REPORT_2026-08-18.md)
- [outputs/ACTIVE_3_EXECUTION_QUEUE.md](../outputs/ACTIVE_3_EXECUTION_QUEUE.md)
- [state/HERMES_EXECUTION_STATE.yaml](../state/HERMES_EXECUTION_STATE.yaml)
- [approval/APPROVAL_QUEUE.yaml](../approval/APPROVAL_QUEUE.yaml)

These documents should be reconciled into a single source-of-truth narrative for agent reads.

---

## 3. Recommended polish pass

### Priority 1 — reconcile the source-of-truth files

Update the operational docs so that they all agree on:

- current phase
- active engine
- next action
- blocked approvals
- ready-to-execute tasks
- completed tasks

This should be a documentation-only pass, not a behavior change.

### Priority 2 — add an agent execution digest

Create a short operational brief with:

- objective
- active agents
- queued tasks
- dependencies
- human approvals required
- success conditions
- failure conditions

This makes it easy for the agents to choose the next task without reading five files.

### Priority 3 — formalize agent sequencing

Agents should proceed in this order:

1. Researcher
2. Judge
3. Proofer
4. Compliance ratifier
5. Outreach executor
6. Human approval gate
7. Send + record
8. Revenue review

This sequence keeps the chain compliant and prevents early send attempts.

---

## 4. Agent execution plan

### Agent 1 — Hermes Agent / Orchestrator

Primary responsibilities:

- maintain the global objective
- triage all incoming work
- enforce no-send without approval
- choose the highest-value next action
- assign research, proof, and drafting tasks
- keep the canonical state current

Tasks to execute:

1. Reconcile current state against approvals and open blockers.
2. Confirm which of the three active engines is priority for the next run.
3. Decide whether the next work is website rescue, reputation review, or flooring routing.
4. Queue the next batch only after approval constraints are satisfied.
5. Validate that no external send or offer is created without pricing approval.

Must not do:

- send messages autonomously
- publish offers without approved pricing bands
- conclude consent from public publication alone

### Agent 2 — Researcher / Goose

Primary responsibilities:

- identify prospects and collect evidence
- verify business context
- gather contact details and source URLs
- record public evidence and publication context
- collect proof assets for each business

Tasks to execute:

1. Compile a target list for the active engine.
2. For each prospect, collect:
   - exact address
   - source URL
   - surrounding wording
   - whether the wording invites contact
   - relevance to business function
   - refusal/anti-marketing evidence
3. Mark leads as valid, blocked, or rejected.
4. Produce a per-prospect evidence packet ready for human ratification.
5. Stop at any uncertain consent condition rather than guessing.

Success condition:

- evidence pack is complete enough for approval review

### Agent 3 — Judge

Primary responsibilities:

- assess whether the prospect is commercially valid
- judge relevance and quality of proof
- evaluate whether the business problem is real and specific

Tasks to execute:

1. Review each business profile and evidence packet.
2. Score the opportunity using the repo rubric.
3. Reject weak, generic, or low-relevance leads.
4. Identify the strongest prospects for the next outreach batch.
5. Produce a judge decision record for the proofer and human approver.

Success condition:

- only strong, relevant prospects remain in the candidate set

### Agent 4 — Proofer

Primary responsibilities:

- perform factual verification
- validate the quality of the evidence
- ensure the claim is supported by public evidence
- verify that no unsupported statements enter the draft

Tasks to execute:

1. Check each prospect evidence packet for completeness.
2. Confirm public source quality and specific business relevance.
3. Identify missing proof before outreach is drafted.
4. Flag any issue that breaks the compliance gate.

Success condition:

- every outreach candidate has a verified factual basis

### Agent 5 — Compliance ratifier / consent gate owner

Primary responsibilities:

- validate the consent rationale per prospect
- verify that the business has a legitimate reason for the contact
- ensure the evidence meets the default-deny standard

Tasks to execute:

1. Review each prospect for consent basis.
2. Require explicit ratification before the prospect is eligible for email.
3. Block any ambiguous or borderline case.
4. Route high-risk or unclear leads to phone or non-email contact only.

Success condition:

- each prospect either has a ratified consent basis or is excluded

### Agent 6 — Outreach executor / sales agent

Primary responsibilities:

- build the final outreach draft
- keep the message truthful and specific
- attach the approval record
- prepare only the approved candidate set

Tasks to execute:

1. Pull only ratified, approved prospects.
2. Prepare one tailored draft per candidate.
3. Keep the offer aligned to approved price bands.
4. Ensure the final message respects the consent rationale.
5. Queue only approved send actions.

Success condition:

- no draft is generated for unapproved or non-ratified leads

### Agent 7 — Operational coder / maintainer

Primary responsibilities:

- keep scripts and state consistent
- repair stale docs or mismatched runtime artifacts
- ensure tool and output integrity
- validate automation behavior against repo guardrails

Tasks to execute:

1. Reconcile the stale reports with the state file.
2. Remove or fix contradictory statements across outputs.
3. Keep execution scripts aligned with the legal/compliance gate.
4. Verify output generation stays deterministic and reviewable.

Success condition:

- no contradictory operational files remain

### Agent 8 — Finance / revenue reviewer

Primary responsibilities:

- check pricing bands
- ensure offers do not exceed approved ranges
- review MRR and one-off revenue models
- keep the business side within the approved budget and policy

Tasks to execute:

1. Confirm approved sellable price bands for each active engine.
2. Check whether one-off or recurring pricing matches the active offer.
3. Reject any quote that is not explicitly approved.
4. Record the final revenue model for each successful engagement.

Success condition:

- all final offers are within authorized pricing policy

---

## 5. Recommended sequence for the next execution cycle

### Phase 1 — Stabilize the operating story

- reconcile report vs state
- confirm active engine priority
- confirm open approvals and blockers

### Phase 2 — Complete evidence pack

- research each prospect
- collect source evidence
- verify the contact method and publication context
- score the prospect

### Phase 3 — Compliance gate

- run the consent gate
- require per-prospect ratification
- reject ambiguous cases

### Phase 4 — Approved outreach

- prepare final tailored drafts
- verify price approval and offer scope
- queue for the human approval step

### Phase 5 — Execution and feedback loop

- send only approved outreach
- track replies, interest, and conversion
- update the database and state file
- capture revenue evidence and lessons learned

---

## 6. Hard rules for agents

- Never send a message without a clear human approval path.
- Never infer consent from public publication alone.
- Never use stale output as the source of truth when current state is available.
- Never draft before the evidence packet is complete.
- Never quote a price outside approved pricing bands.
- Never treat a completed task as still open without updating the state file.

---

## 7. Suggested next milestone

The next milestone should be:

- complete the audit polish pass
- align the state and reports
- resolve APR-004 and APR-007 as the gating human approvals
- run one focused, fully evidence-backed prospect batch
- only then move into the send stage

This keeps the engine compliant, executable, and operationally clean without introducing unnecessary business risk.
