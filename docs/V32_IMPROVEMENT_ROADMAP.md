# Website Auditor v32 improvement roadmap

Prioritise the approved-URL workflow from read-only audit to evidence-backed report and verified rerun. All items below are open. The local candidate was reconciled against a reconstructed snapshot of GitHub master at `83d23bf0`. Hosted release evidence must identify the actual candidate SHA.

## P0 · Release gates

| Improvement | Work | Acceptance |
| --- | --- | --- |
| Focus the release | Branch from current GitHub master. Retain newer fixes and separate optional orchestration, report delivery, and broad refactors where dependencies allow. Exclude local runtime state and accidental npm additions. | A focused draft PR records the base SHA, candidate SHA, conflict resolutions, and required checks. |
| Hosted CI | Run toolkit, integration, Money Machine acceptance, and Chromium checks on a capable host. Use disposable PostgreSQL, matching Playwright browser binaries, and a research-only doctor run. | All required jobs pass on the same SHA. Required service failures are visible. |
| Unattended operation | Run a 24-hour research-only soak on the verified candidate with controlled audit jobs, one planned restart, and ensure-running supervision. Record heartbeat, queue age, completed reports, attempts, and dead-letter queue status. | Reports complete, queued work recovers, and evidence shows zero duplicate work, zero paid calls, and zero external sends. |
| Audit entry point and discovery | Exercise a supplied approved URL with discovery unavailable. Verify SearXNG separately and expose discovery status in operator health. | The approved-URL audit completes where release requirements permit degraded discovery. The SearXNG check independently verifies the discovery path and records any remaining typed skips. |

The integrator reviews evidence and performs the final squash merge. Tie verification to the final candidate and recheck changed code or configuration before merging.

## P1 · Reliability and report quality

| Improvement | Work | Acceptance |
| --- | --- | --- |
| Monitor outcomes | Extend existing schedule health with expected run, latest successful report, oldest queued job, and hold reason. | A missed run or ageing queue produces an actionable alert. |
| Prove recovery | Extend the existing archive verification workflow with a disposable PostgreSQL restore. Compare representative jobs, reports, and request accounting. | The drill records recovered data, recovery time, and snapshot age. |
| Enforce audit boundaries | Review approved-target scope, private network restrictions, permissions, secret access, redaction, and workflow dependency pinning. Keep state-changing actions and report delivery behind approval. | Defensive CI covers access boundaries, redacted artifacts, and approval enforcement. |
| Verify report findings | Record page, timestamp, evidence, business impact, suggested fix, and retest for each finding. Show Lighthouse lab and CrUX field data separately. Flag accessibility findings that require manual review. | A reviewer can confirm the top findings from the evidence, and a rerun shows which fixes held. |

## P2 · Commercial validation and targeted refactoring

| Improvement | Work | Acceptance |
| --- | --- | --- |
| Validate one offer | Create one sample mobile enquiry audit and run a small opted-in pilot with a single customer group. Provide a prioritised fix list and a follow-up check. | Record accepted findings, completed fixes, willingness to pay, delivery time, and per-report cost. |
| Refactor measured bottlenecks | Prioritise migration fixtures, typed errors, and structured failure logs. Use per-stage timings and operator workload to decide where operator decomposition and async work help. | Each change improves an observed failure, measurable cost, or maintenance burden. Defer multi-region and broader plugin work until workload or demand justifies it. |

## References

- [GitHub Actions schedule behaviour](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
- [Playwright CI](https://playwright.dev/docs/ci)
- [PostgreSQL backup verification and test restores](https://www.postgresql.org/docs/16/app-pgverifybackup.html)
- [Chrome lab and field performance data](https://developer.chrome.com/docs/crux/guides/pagespeed-insights)
- [W3C accessibility evaluation](https://www.w3.org/WAI/test-evaluate/)
