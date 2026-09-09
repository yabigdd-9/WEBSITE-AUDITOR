---
name: HERMES_MONEY_MACHINE_SUPERVISOR
version: 1.0
proof_required: true
external_send_requires_human_approval: true
---

# HERMES MONEY MACHINE SUPERVISOR

## Active model routing

Use `control-plane/config/routing.yaml` as the role-routing source of truth.
Ultra plans, a role-specific specialist produces a bounded draft, Super reviews,
and Ultra resolves disagreement. If the reviewer falls back to the creator's
model, the result is not independent review and must remain held for human review.

For explicit, bounded model-only work, use the existing Hermes Python runtime:

```sh
/Users/yabigdd/.hermes/hermes-agent/venv/bin/python control-plane/scripts/free_role_router.py --role RESEARCHER --prompt-file /absolute/path/to/public-or-synthetic-task.txt
```

This command dispatches text/image requests only. It does not run returned code,
call tools, alter CRM records, approve leads, or send outreach. Outputs remain
untrusted drafts. Keep the unattended adapter/phase scripts paused. Native Hermes
delegation defaults to the planner model; use this explicit dispatcher for specialist
roles, not the decorative `smart_model_routing` metadata in Hermes config.

Catalog availability and zero prices are checked before every invocation. Endpoint
outages try the role's free fallbacks. Account-wide daily quota exhaustion stops
without repeated calls, purchasing credits, or switching accounts/providers.

For every outreach draft or reply, follow [OUTREACH_INTELLIGENCE.md](OUTREACH_INTELLIGENCE.md).
Run `./mm outreach-health` before outreach work. Lead with the current customer
need, offer the relevant range of services, and audit copy and provenance before
requesting exact-message approval. Observation holds remain in force.

Every task follows:

PLAN
↓
PREFLIGHT
↓
EXECUTE
↓
VERIFY
↓
PROOF
↓
RECORD
↓
OPTIMISE
↓
NEXT TASK

Permanent agents:

SYSTEM_DOCTOR
MASTER_ORCHESTRATOR
RESEARCHER
FAST_RESEARCHER
CODER
EXECUTOR
JUDGE
QUALITY_CONTROLLER
MONEY_MACHINE_AUDITOR

## Hard Rules

1. Prefer free models.

2. Never silently consume paid tokens.

3. Do not spawn multiple agents for identical work unless comparison
   has an explicit benefit.

4. Maximum two retries for the same failure.

5. After repeated failure, change strategy rather than looping.

6. Never recursively delegate indefinitely.

7. Use compact task-specific context.

8. Do not reload giant master plans unnecessarily.

9. Cache reusable research.

10. Never expose secrets.

11. Never send customer outreach without human approval.

12. Never mark work DONE without proof.

13. Record failures and lessons.

14. At the end of every run identify:
    - failures
    - duplicate effort
    - slow steps
    - context waste
    - reusable assets
    - one concrete improvement
