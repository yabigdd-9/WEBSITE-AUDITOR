# Local Website Auditor

The canonical implementation is `auditor_toolkit`; `wa` and the main legacy URL entrypoints call it directly. Existing reports and unrelated integrations are preserved. Git/GitHub connectors now produce local previews; environment tokens do not enable external dispatch.

## Setup on macOS

```sh
cd /Users/dd/WEBSITE-AUDITOR
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,browser,portal]'
.venv/bin/python -m playwright install chromium
.venv/bin/wa doctor
.venv/bin/wa audit https://example.com --deep
.venv/bin/wa audit https://example.com --profile rendered --deep
.venv/bin/wa dashboard --set-password
.venv/bin/wa dashboard
```

The `.command` launcher prompts for a password on first use. The portal binds to localhost. Run audits from the CLI, then search/download their evidence in the portal. HTML downloads are attachments; the portal displays escaped evidence, never an authenticated raw report frame.

Install `.[ai]` separately to enable llama.cpp. The existing model is verified by size and SHA256 before generation. `wa doctor --smoke` attempts browser startup and every AI draft type; timeout is a failed smoke test, even if templates are returned. A model passing its checksum does not mean generation is working.

## Operation

- `wa audit URL --profile rendered --max-pages 10 --max-depth 2 --deep` includes browser evidence, axe-core and PDF. `--allow-private` is only for explicitly selected local fixtures/private sites.
- `wa audit --batch targets.txt --concurrency 2` audits at most 100 explicit URLs with at most four concurrent runs. Robots rules control follow-up crawling. No forms are submitted.
- `--competitor URL` adds explicitly selected comparison sites using the same profile; CLI output presents scores together. It is not a market ranking.
- `--cache` uses validators when provided; reused evidence retains its original observation time. A revalidated response is identified separately.
- `--ai --ai-timeout 120` requests local drafts. All generated/template content requires editorial review, particularly te reo Māori.
- `--brand 'Agency Name' --hourly-rate-nzd 120` produces an illustrative NZD proposal. Hours are disclosed assumptions, not measured effort or lost revenue.
- `wa actions preview path/to/report.json` emits local proposal and request files. `wa actions cancel path/to/report.json` cancels that preview directory. Nothing is applied, committed, pushed or sent.
- `wa history --query example.com` reads stored runs. `--retention-preview 20` lists candidates only; it deletes nothing.

## Contract and limits

JSON schema 2 retains `score` as defect severity. `health_score` is its inverse only when required checks finish. A completed audit can contain serious defects. Disabled checks are visible; category scores remain unavailable when unassessed. Browser and PDF failures in rendered mode make the run partial.

Evidence and artifacts belong to one immutable run. SQLite schema version 1 stores history and remediation state. Partial scans cannot prove resolution. Verification requires a later complete run for the same URL/profile without the finding. Previews never mark a finding fixed. Reports expose exact heuristic score weights; these are not certifications.

The crawler performs bounded GET requests. HEAD-only failures are not treated as broken links. Possible soft 404s require a matching title/H1 and human review. Browser metrics are laboratory observations, not field Core Web Vitals. Consent capture observes pre-interaction cookies; it does not certify compliance. Missing DNS answers differ from DNS failures. Authenticated checkout, screen-reader evaluation, legal/business identity validation and language quality need human review.

URL checks reject credentials and non-global destinations by default, including redirect targets. The toolkit is for trusted local operators; it is not a hosted untrusted-URL service. A separate hardened egress boundary is required before public deployment. Captured response headers are allowlisted, cookie values are excluded, and network evidence omits query strings. Page snippets can still contain personal information; use the retention preview and review artifacts before sharing.

The monthly configuration is disabled. New workflows have no scheduled trigger. Existing unrelated automation files are preserved and are not enabled by setup. Public hosting, payments, production writes and outbound delivery remain outside this release.

## Troubleshooting

A sandbox may prevent localhost server binding or Chromium startup. Run the opt-in fixture browser test in a normal local terminal. Never turn a failure into a passing report. See TOOLKIT_VALIDATION.md for actual validation evidence and CHAT_ACTION_REGISTER.md for roadmap dispositions.
