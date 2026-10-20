# Bounded email-record candidate

**Prepared source only. Not installed, executed, regression tested or promoted.**

## Intended change

The legacy plugin hardcodes a Python 3.9 command in a particular user's home
directory, converts every failure to `False`, and assigns low spoofing risk
whenever DMARC is valid. A valid policy may be monitoring-only, and a DNS error
does not prove an invalid record.

The candidate adds `auditor_toolkit.email_auth` as the shared parent adapter,
an owned checker child, an optional exact `checkdmarc==6.0.3` extra and a legacy
output adapter. The canonical deep DNS observation embeds `email_security`
without replacing existing A/AAAA/MX/TXT observations. The DNS registry version
becomes 2. No new score deduction or security finding is inferred.

All four advanced plugins now have proposed shared canonical implementations.
The advanced launcher now proposes canonical bounded fetch/check orchestration
through a lazy wrapper, as described in ADVANCED_COMMAND_CANDIDATE.md.
Whole-workflow and downstream format parity are unaccepted.

## Target and checker scope

The exact HTTP(S) hostname or supplied fully qualified domain is retained,
lowercased and IDNA normalized; URL ports are validated and excluded from DNS.
Credentials, control characters, malformed labels, IP literals, local/reserved
suffixes and ambiguous inputs are rejected. No `www` removal or guessed sending
domain occurs. DNS-only selection does not verify that the hostname is the
business's actual email domain. The checker discovers DMARC location and policy
tags under its own versioned rules, including inherited policy. No homemade
partial SPF/DMARC parser substitutes for protocol validation.

Only `checkdmarc.spf.check_spf` and `checkdmarc.dmarc.check_dmarc` are invoked.
`check_domains` is excluded: no SMTP/TLS connection, message submission,
MTA-STS/BIMI HTTP fetch, mailbox probe or provider request is requested.
Normal DNS queries may inspect SPF dependencies and DMARC reporting destinations.
Public DNS values, parsed policies, warning/error diagnostics and effective
policy location are retained as checker evidence.

## Truthful states

| State | `valid` | Meaning |
| --- | --- | --- |
| `validated_record` | true | The pinned checker accepts the observed record under its semantics; no recorded material lookup failure or exhausted budget. |
| `checker_rejected` | false | The checker rejects the record or reports no usable record, with its error preserved. This is not a website-defect or spoofing claim. |
| `unknown` | null | Dependency unavailable/unsupported, invalid target/configuration, DNS lookup failure, deadline/query/output cap, checker exception or malformed output. |

`reported_valid` and `checker_result` preserve a checker conclusion even when
the normalized result is unknown. The resolver records successful answer
counts/hashes, NoAnswer/NXDOMAIN and transport/programming failures. A swallowed
material lookup failure cannot be promoted to a known validity state. The
deprecated SPF RR courtesy query may fail without tainting a later successful
TXT-based SPF check; exhaustion still taints it. All other lookup failures are
conservatively held, including courtesy CNAME or policy-report destination
queries. This may hold a usable policy for review rather than claiming certainty.

Legacy keys `spf_valid` and `dmarc_valid` become boolean-or-null in format 2.
Consumers must distinguish null from false. `spoofing_risk` is always
`NOT_ASSESSED`, including with `p=none`, reject, quarantine or inherited policy.
DKIM, actual message alignment/authentication, enforcement, delivery, consent
and business identity are not assessed. A completed base DNS check does not
establish successful optional email validation; inspect its nested status.

## Ownership and limits

- Missing or unsupported checker returns unknown before importing it or spawning
  a worker. The optional dependency is declared but has not been installed.
- The child uses the parent's Python with bytecode writes disabled, the package
  root as its working directory, and a small environment allowlist without
  API keys or inherited provider configuration.
- Requested timeout must be finite, 1–30 seconds. Parent owns the overall child
  timeout and kills/reaps it on timeout or interruption.
- One shared deadline and at most 64 resolver calls cover SPF and DMARC. Each
  resolution lifetime is capped at two seconds and remaining time; checker
  retries are zero. This is a resolver-call cap, not an exact DNS packet count.
- Once exhausted, later protocol checks are unknown. Parent startup/import time
  also consumes its outer deadline. No detached child or automatic retry exists.
- Output is file-backed and parent reads at most 1 MiB plus one byte. Worker
  checks serialized size and holds overlarge output instead of claiming partial
  validation. Third-party internal memory use is not independently bounded.

## Required regression and integration evidence

Not run; earlier approval covered identity/contact, metadata and local demo.
Pending expanded regression authorization must include this candidate.

Use synthetic checker responses and mocked resolver/process services first:

1. HTTP(S), domain, IDNA, uppercase and trailing-dot normalization; ports;
   exact subdomain retention; credentials, IP/local/malformed input rejection.
2. Missing/unsupported dependency causes no child/no lookup and null validity.
3. Valid SPF including recursive includes/redirects and checker warning fields;
   absence, syntax errors, include loops and protocol lookup limits.
4. DMARC tags/location, inherited policies, valid `p=none`, quarantine/reject;
   duplicate/unrelated records and reporting destination checks. None implies
   low spoofing risk or verified mailbox/consent/delivery.
5. NoAnswer/NXDOMAIN versus timeout/SERVFAIL/OSError; swallowed material errors
   remain unknown even when checker reports true or false; SPF RR courtesy
   failure does not mask later material failures or exhausted limits.
6. Shared deadline and call exhaustion, startup timeout, owned child kill/reap,
   interrupt cleanup, unavailable child, malformed/oversized output, version and
   domain mismatch, wrong/missing validity/record/tags/parsed fields.
7. Canonical deep DNS observations/registry and legacy format 2 consumer handling;
   no changes to prior score/finding fields or false green email result.
8. Acceptance with the actual pinned package in a separately authorized isolated
   dependency environment, with all network operations mocked. Static source
   inspection cannot prove dependency/API/runtime compatibility.

## Primary sources consulted

- [checkdmarc 6.0.3 API](https://domainaware.github.io/checkdmarc/api.html)
- [SPF implementation](https://domainaware.github.io/checkdmarc/_modules/checkdmarc/spf.html)
- [DMARC implementation](https://domainaware.github.io/checkdmarc/_modules/checkdmarc/dmarc.html)
- [Resolver implementation](https://domainaware.github.io/checkdmarc/_modules/checkdmarc/utils.html)
- [Pinned release and Python compatibility](https://pypi.org/project/checkdmarc/6.0.3/)

Documentation was inspected on 3 October 2026 NZDT. Current checkdmarc documentation
explicitly allows `valid: false` on DNS errors; the candidate preserves uncertainty
through a resolver transcript. The source remains an untested proposal.
