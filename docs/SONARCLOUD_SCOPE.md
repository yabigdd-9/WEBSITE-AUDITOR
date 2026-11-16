# SonarCloud free-tier scope and coverage trade-off

As of 16 November 2026, the GitHub main-branch SonarCloud analysis failed at
the organization's 50,000 source-line allowance. The server reported **33,750**
LOC already in use and **17,340** LOC in this new analysis, totaling **51,090**
before applying exclusions. The failure was **quota exhaustion**, not a pass/fail
assessment of the source.

To keep the project within the free allowance, `sonar-project.properties`
excludes `auditor_toolkit/evaluation/**` from **SonarCloud only**. That directory
holds the offline evaluation harness and supporting schemas/graders; it is
approximately 2,573 physical Python lines in the current checkout. This is a
deliberate reduction in SonarCloud coverage, not a security fix. A source LOC
measure may count fewer lines than the physical-line estimate; verify the
post-merge server result, and re-evaluate if the quota is still exceeded.

The following remain unchanged:
- **GitHub CodeQL** scans Python across the repository, including evaluation.
- **Ruff** and unit/regression tests still cover the existing code and
  evaluation tests as configured in CI.
- Secret scans, dependency audits, website audits, live transport limits,
  state encryption and the durable MoneyMachine worker are not changed.

Risks and limits: excluded files no longer contribute to SonarCloud's code
quality/security metrics or coverage percentages. The other checks are
complementary, not identical substitutes. This does not establish production
readiness or remove the need for peer review and runtime security testing.

Do not silence or disable SonarCloud on failure. If the project grows beyond
the free limit again, either reduce unused legacy code, move workloads to a
separately funded plan with explicit owner approval, or adjust documented
analysis scope while keeping meaningful safeguards. No paid tier is enabled
by this change.
