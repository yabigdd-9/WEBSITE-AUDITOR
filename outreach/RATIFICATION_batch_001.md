# PER-PROSPECT CONSENT RATIFICATION — batch 001

_Dion to complete. Each row must be ratified individually. The UEMA gate (`consent_gate.py`)
will remain BLOCK for a business until its `human_ratified_by` field is set and a rationale ≥40
chars exists. Nothing is sent without this._

## The 4 businesses with a published address (the only ones that can be emailed)

For each, I've drafted a rationale from the **real** evidence the collector gathered. You either
confirm it (write your initials in `ratified_by`) or rewrite it. Edit the dossier file directly,
or just tell me "ratify all 4" / "ratify clyne-bennie and prodecorators only".

---

### 1. clyne-bennie.co.nz
- **Address:** service@clyne-bennie.co.nz  (role-ish address on own homepage)
- **Found:** plain text, homepage footer block
- **Context (verbatim):** "…Get in Touch 0800 37 47 37 service@clyne-bennie.co.nz LinkedIn Facebook…"
- **Invites contact:** YES — "Get in Touch" block
- **Verified defects:** NO_WRITTEN_CONTACT (no form/email shown except footer), HEAVY_HTML
- **Draft rationale:** Address is published in a block expressly inviting business contact ("Get in
  Touch"); message concerns a verified defect on their own site (no working contact form). Relevant
  to the address's function.
- **ratified_by:** ____

### 2. jcconstruction.co.nz
- **Address:** jason@jcconstruction.co.nz  (named individual, on own homepage)
- **Found:** mailto: link
- **Context (verbatim):** "Christchurch, New Zealand JASON: 027 378 0000 PAGAN: 027 373 0230 jason@jcconstruction.co.nz"
- **Invites contact:** the address is itself the contact mechanism (no separate "contact us" wording)
- **Verified defects:** HEAVY_HTML
- **Draft rationale:** This is a sole-trader/owner address published as the business's primary contact
  on its own site; the message about a site defect is directly relevant to that contact function.
- **ratified_by:** ____

### 3. tbir.co.nz
- **Address:** tbirgrass@gmail.com  (PERSONAL Gmail, on own homepage)
- **Found:** mailto: link
- **Context (verbatim):** "Based in Lincoln, Christchurch - servicing all of Canterbury tbirgrass@gmail.com +64-273-789-451"
- **Invites contact:** address is the contact mechanism
- **Verified defects:** HEAVY_HTML
- **⚠ Note:** this is a personal Gmail, not a business role address. The inference is weaker. The gate
  permits it (it's their own published contact), but flag it: a personal address is the one most likely
  to feel intrusive. **Recommend: phone first, not email.**
- **Draft rationale:** Owner publishes this address as the business contact on the site; message is
  relevant to a site defect.
- **ratified_by:** ____ (recommend: NO / phone instead)

### 4. prodecorators.co.nz
- **Address:** contact@prodecorators.co.nz  (clean role address, footer)
- **Found:** plain text footer "Email: contact@prodecorators.co.nz"
- **Context (verbatim):** "Contact Phone: 03 3652204 Email: contact@prodecorators.co.nz christchurch, roof, auckland…"
- **Invites contact:** it's in a "Contact" block
- **Verified defects:** NO_WRITTEN_CONTACT, HEAVY_HTML
- **Draft rationale:** Role address published in a Contact block on the business's own site; message
  concerns a verified defect (no working contact form) on their own site.
- **ratified_by:** ____

---

## The 5 with NO published email (cannot be emailed — gate blocks by design)

These route to **phone or post**, or are held as researched leads:

| Business | Verified defects | Channel |
|---|---|---|
| whiteandtaylor.co.nz | STALE_COPYRIGHT, HEAVY_HTML | phone |
| bcplumbers.co.nz | STALE_COPYRIGHT, BROKEN_LINKS | phone |
| greenscapes.co.nz | STALE_COPYRIGHT, HEAVY_HTML | phone |
| dyerdecorating.co.nz | NO_WRITTEN_CONTACT, HEAVY_HTML, NO_SOCIAL_LINKS | phone |
| davidrobertson.co.nz | NO_CONTACT_ON_HOMEPAGE, BROKEN_LINKS, NO_SOCIAL_LINKS | phone (broken link `/_blank`→404 is the hook) |

No address was harvested for any of these from directories or third parties (s.13).

---

## How ratification flows

1. You confirm rows 1–4 (or a subset) by name or "ratify all".
2. I stamp `human_ratified_by: Dion` + `human_ratified: true` + the rationale into the dossier.
3. Gate re-run → those rows flip to PERMITTED.
4. `--draft` builds the email bodies (verified-defect only, no price).
5. You see the drafts, then `--send --i-approve` transmits. **You press send.**
