# Historical security holds — disposition draft

**Prepared:** 2026-10-29 20:05 NZDT · **Source:** `8599e893` · **Status: DRAFT — no decision recorded, no action taken**

All 16 items remain `decision: null` in the owner template. Nothing below is a clearance,
a rotation authorization, or a claim that a credential is inactive. Every item needs an
owner answer before it can close.

## What the evidence actually shows

The 16 holds split into three groups with very different profiles.

### Group A — false positives from a regex scanner (12 items)

`triage-047`, `triage-049`, `triage-050`, `triage-058`, `triage-060`, `triage-061`,
`triage-062`, `triage-066`, `triage-068`, `triage-069`, `triage-083`

These were flagged by `generic-api-key` / `gcp-api-key` / `google-api-key` rules against
**captured third-party email HTML** — pages we received in, not pages we own. The
"key" is a 39-character base64 blob that decodes to `AIzaSyCBTROq6LuvF_IE1r46-T4AeT…`,
i.e. a Google Maps embed key that appears **once per capture**, inside a Squarespace
`data-context` attribute or a WordPress form. It is the website owner's key, embedded in
their own page, captured in our inbox.

- **We do not own it.** It belongs to whoever runs that website.
- **We did not create it, store it intentionally, or use it.** It is present only because
  an email we received happened to contain the page.
- **It is not in our source code, config, or runtime.** It lives in fixture captures
  under `money-machine/fixtures/email_captures/`.

**Recommended disposition: not ours — no action.** The only residual concern is that the
raw captures are tracked in Git, so the value persists in history. That is a historical
artifact of inbound email capture, not a live secret. Removing it from history would require
a rewrite, which is disproportionate for a third-party key we never possessed.

### Group B — one real-looking Google Maps key in a tracked file (1 item)

`triage-044` — `money-machine/fixtures/email_captures/11-1.html`, line 39, `google-api-key`

Unlike Group A this one is **plaintext**, in an `<iframe>` map embed:
`https://www.google.com/maps/embed/v1/place?key=AIzaSy…&q=357+Brougham+Street,+Sydenham,+C…`

Same provenance as Group A (captured inbound email, third-party page), same conclusion
(not ours), but it is the only one a secret scanner can see without decoding. If anyone
later wants to reduce scanner noise, this is the file to handle.

### Group C — absent from the current tree (4 items)

`triage-007`, `triage-085`, `triage-086`, `triage-087`

- `triage-007` is a Stripe access-token example in `skills/code-security/rules/secrets.md`
  — a documentation example, flagged from a commit (`a159dd2`) that is **not** an ancestor
  of the frozen source. The file no longer exists in the tree.
- `triage-085`, `triage-086`, `triage-087` are from `outputs/.cache/*.json` — cached HTML
  captures of `davidrobertson.co.nz` and `prodecorators.co.nz`, also from a non-ancestor
  commit. The cache files are not tracked.

**Recommended disposition: historical only — no action.** Absence from the current tree
does not erase Git history, and we have not established these were ever ours.

## What I have not done

- No key has been tested against any provider.
- No key has been rotated.
- No credential value has been printed into any log or this document.
- No Git history has been rewritten.
- No file has been deleted.

## What needs an owner decision

For each item, one of:

1. **Not ours** — third-party content captured in inbound email. No action.
2. **Ours, intentional** — would need purpose, restriction evidence, and (if exposed)
   explicit rotation authorization.
3. **Unknown — owner to confirm** — if you recognize the source, say so.

I can only reach (1) for 15 of 16, and only because the provenance is unambiguous.
`triage-007` is a documentation example rather than a capture, so it needs your call
separately.