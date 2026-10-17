# Offline pinned startup reader delivered

Application revision c890cab41b0bb1ebb7e0af832beab788438a3dcb. Exact owned paths and API contract: ../A10_READER_CONTRACT.md and ../OWNERSHIP.md. Adds an optional independently pinned startup identity check in mm_soak.startup_attestation, preserving legacy verified semantics and always retaining runtime UNKNOWN.

## Standards

Independent read-only reviewer found zero actionable standards findings. Focused synthetic fixtures, existing schema helper reuse, bounded scope and source-only compatibility match repository conventions.

## Spec

Initial independent review identified one P2: revision string comparison did not bind receipt source hashes to committed bytes. Corrected by reading the approved committed tree and comparing every receipt module hash. Added coordinated disk/receipt tampering regression and actual synthetic Git commits. Reviewer rechecked and found no remaining actionable findings. Reviewers did not run tests or edit files.

## Fresh verification

94 passed in 13.84 seconds across new contract, existing bootstrap and runtime-readiness suites. Scoped ruff and git diff --check passed. Tests ran on the source bytes then committed as c890cab4; those bytes were checked against the commit afterward. No exact-loaded-code probe or full canonical/money replay is claimed for this increment. The earlier full-suite receipts apply only to the prior application revision.

Shared checkout remains ec86481c with five tracked changes and 241 untracked files; shared launchd job absent. Opus remains dfc5dc39. No shared integration, service restart, soak activation, production DB operation, provider/configuration change, deployment, push or outreach performed.

## Remaining integration boundary

The new approval inputs are not wired into collect_sample or soak acceptance. This package verifies startup evidence, not current process identity. Its approved manifest must be selected independently by a future authorized caller. Full A10 requires PID-reuse-resistant process-start identity, scheduler ownership and actual executable/DB correspondence; until then runtime identity remains UNKNOWN. Integrator must review this new candidate separately before adopting it.
