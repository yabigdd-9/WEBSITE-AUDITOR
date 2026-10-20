# Advanced audit command and operator namespace

**Isolated source candidate. No command/import, audit or regression executed.**

## Source gap addressed

The previous `advanced_audit.py` reads process arguments and performs a request
during import. It uses a separate requests fetch, accepts HTTP error/non-HTML
responses as input to plugins, prints a banner before JSON and returns success
after plugin output without a completed-check contract. Its byte-exact frozen
baseline remains archived. Each plugin's proposed canonical implementation
exists, but the old orchestration bypasses the canonical fetcher.

## Prepared commands

```text
./mm toolkit <canonical command and arguments>
./mm toolkit advanced https://example.com --timeout 8
./mm toolkit advanced https://www.example.com --email-domain example.com
python advanced_audit.py https://example.com --timeout 8
```

These are proposed commands, not evidence that they have run. The `toolkit`
namespace is new on the canonical operator launcher. Its advanced route enters
`auditor_toolkit.advanced.main`; other toolkit commands enter the existing
canonical CLI. Existing `mm audit <id> --observation ...` keeps its meaning as
an evidence-recording command. No command-name collision is introduced.

The project Python selection/version gate remains in the shell launcher. Toolkit
dispatch occurs before the operator's database imports, explicitly selects
source from the launcher's checkout, preserves the caller's current directory,
passes arguments without a shell evaluation and propagates the Python exit
status. The root `advanced_audit.py` is a lazy thin wrapper. Its import performs
no audit, argument parsing, dependency import, cache creation or output.

## One shared implementation per feature

The new orchestration fetches once through existing `common.Fetcher` and calls
the canonical technology, UX, image and bounded email-record APIs once each.
It adds no signature matching, consent/image inference or SPF/DMARC parser.
Legacy-format presentation is output adaptation only; each canonical observation
is retained in `evidence`, including UX observations with no flagged finding.

Default fetch inherits the canonical URL/private-address and redirect validation,
TLS verification, disabled environment proxies, rate interval and redirect cap.
Capture is capped at two million decoded body bytes. HTTP errors, soft-404
responses, non-HTML content and empty documents are rejected; no downstream
plugin is called after unusable capture. A supplied fetcher remains caller-owned;
the internally created fetcher is closed in `finally`, including interruption.

Technology, UX and images use the final fetched URL. Email records default to
the **requested** URL hostname, matching the former advanced plugin's domain
selection. `--email-domain` explicitly selects another domain; it is not guessed
from website redirects. This differs from the canonical full audit's deep DNS
check, which inspects the final hostname. Neither proves the business's sending
domain. Timeout must be finite and between 1 and 30 seconds.

The existing fetcher timeout/redirect behaviour is reused. This command does
not claim an independently bounded overall wall-clock time: resolver/capture
and multiple redirect/check stages have separate limits. Full-process deadline
acceptance and DNS pinning/rebinding protections remain broader review scope.

## Output and exit contract

- One JSON document on stdout, with `format_version: 2`, scope, timestamp,
  requested/final URLs, capture hashes, check records and canonical evidence.
- Former result keys remain: `tech_stack_detected`, `email_security_dns`,
  `ux_dark_patterns`, `image_performance`. They are null when unexecuted/failed,
  rather than empty results that imply no findings.
- Each requested check is required. A missing optional email checker or unknown
  SPF/DMARC result produces an unknown check and an **incomplete** advanced run.
- Checker rejection is a completed observation with its error preserved; it
  does not automatically infer a website defect or spoofing-risk grade.
- Return 0 only when fetch and all four requested checks completed; return 2
  for incomplete capture/checks or invalid arguments. Defects can occur in a
  complete observation. This is not a green release/compliance claim.
- Per-check failures preserve other successful observations. Report-assembly
  failures retain successful fetch status and receive a separate error record.
- Fetch exception strings/response bodies are not echoed. Credential-bearing
  rejected URLs are not echoed. Owned-fetcher cleanup failures remain explicit.

Full browser/crawl/TLS/Lighthouse/Lychee audit coverage is not requested by this
four-feature command. Those capabilities remain available through the existing
canonical audit route; this does not replace the seventeen-step legacy workflow.
The version 2 consumers, import/argument/format compatibility and all P2 routes
still require acceptance before promotion.

## Pending regression evidence

Earlier human approval covered identity/contact, metadata and local-demo tests.
Expanded entrypoint regression authorization remains pending. No tests added/run
for this source work. Required focused checks include:

1. Importing the wrapper creates no files or network activity and reads no args.
2. Root wrapper and `mm toolkit advanced` select the same canonical function;
   ordinary toolkit arguments/exit codes pass through, current directory stays
   unchanged, and operator database imports do not occur on these routes.
3. Invalid/extra args, timeout bounds and credential/private targets; normal
   redirects, redirects to private targets, response size/time caps, HTTP error,
   soft 404, non-HTML and empty body produce truthful nonzero results.
4. Mocked fetch/checkers demonstrate one invocation each, capture hashes and
   final/requested domain selection, explicit email domain and full UX evidence.
5. Unknown email state, missing dependency and each checker exception preserve
   successful siblings, produce incomplete/null failed output and exit 2.
6. Findings and checker rejection do not masquerade as incomplete execution;
   assembly and cleanup failures do not overwrite successful fetch evidence.
7. Owned/borrowed fetcher lifetimes and interruption cleanup; malformed response
   structures, static-check limits, legacy-format consumer comparisons.
8. All requests/resolvers/processes mocked or synthetic loopback where explicitly
   authorized. No live soak, canonical database, paid provider or external send.

The operator shell has been inspected for syntax only. Static compile/lint
provides no executable command, dependency or workflow parity proof.
