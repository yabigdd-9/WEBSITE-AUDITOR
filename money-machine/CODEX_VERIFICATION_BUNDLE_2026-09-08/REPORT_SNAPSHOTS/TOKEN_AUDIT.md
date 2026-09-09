# MoneyMachine — Token Audit
**Generated:** $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Current Session
| Timestamp | Role | Model | Task | Input Tokens | Output Tokens | Calls | Result Used | Commercial Outcome | Cost |
|-----------|------|-------|------|--------------|---------------|-------|-------------|-------------------|------|
| 2026-09-08T02:00:40Z | OPERATOR | none | backup + inspect + init + daily | 0 | 0 | 0 | yes | Baseline established | $0.00 |

## Historical (from agent_runs table)
| ID | Task | Agent | Model | Cost NZD | Outcome |
|----|------|-------|-------|----------|---------|
| 1-5 | (see agent_runs table) | various | various | various | various |

## Churn Detection
- **Same prospect audited >2 times in 7 days**: None currently
- **Same file summarized repeatedly**: None currently
- **Judge called on trivial tasks**: N/A (model execution disabled)
- **Recursive supervisors**: Disabled (adapters blocked)
- **Loops with no state transition**: None active

## Rule Applied
Every model invocation must answer:
1. What commercial decision will this change?
2. Is local code/search enough?
3. Can this reuse existing evidence?
4. Is this prospect likely to be contacted?

If #4 is no, do not spend model calls.
