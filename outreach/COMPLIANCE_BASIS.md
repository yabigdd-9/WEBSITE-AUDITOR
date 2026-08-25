# OUTREACH COMPLIANCE BASIS — UEMA 2007 hard gate

_Rewritten 2026-08-18 on Dion's correction. Supersedes the earlier draft, which wrongly treated
"email conspicuously published on the business website" as sufficient inferred consent._

## Governing principle

**Publication is not permission.** The fact that a business displays an address on its own site
does not mean it agreed to receive marketing. The *context* of publication is what matters, and
under s.9(3) the **onus of proving consent sits on the sender**.

Therefore the consent gate **defaults to DENY**. Hermes may never conclude consent by itself.

## The gate is a hard module, not a guideline

```
FIND NZ BUSINESSES
   ↓
AUDIT WEBSITE / DIGITAL SYSTEM
   ↓
SCORE OPPORTUNITY
   ↓
FIND CONTACT METHOD
   ↓
UEMA CONSENT / CONTEXT CHECK   ← REQUIRED GATE, default DENY
   ↓
├─ PERMITTED  → personalised msg + truthful identity + reason for contact
│                + unsubscribe + suppression check → QUEUE FOR DION TO SEND
│
└─ NOT CLEARLY PERMITTED → DO NOT AUTO-EMAIL
                           → retain lead research (never discarded)
                           → queue for manual human review
                           → route to compliant alternative channel (phone/post)
```

Implemented in `outreach/consent_gate.py`. No email artifact is generated for any prospect the
gate does not clear. There is no override flag in the code — clearing requires a recorded human
ratification.

## What Hermes must record per prospect (all mandatory)

| Field | Why |
|---|---|
| `address` | the exact address proposed |
| `address_source_url` | the specific page it was found on |
| `address_found_where` | e.g. footer, contact page, "email us" CTA, staff bio |
| `surrounding_wording` | verbatim text around it — this is the publication context |
| `invites_contact` | did the wording invite enquiries at all (e.g. "get a quote")? |
| `refusal_statement_present` | any "no unsolicited/marketing emails" notice anywhere |
| `role_or_personal` | role address (info@/office@) vs a named individual |
| `relevance_to_role` | why the message concerns that address's actual business function |
| `prior_relationship` | existing customer/enquiry/transaction, if any |
| `consent_type_claimed` | EXPRESS / PRIOR_RELATIONSHIP / INFERRED / NONE |
| `why_consent_believed` | the written rationale that would be produced if challenged |
| `human_ratified_by` + `ratified_at` | who accepted the rationale |

Missing any field ⇒ **BLOCK**. Unratified inference ⇒ **BLOCK**.

## Automatic hard blocks (no human can wave these through in code)

- Any refusal/anti-marketing statement present anywhere on the source page.
- Address obtained from anything other than the business's own published page — no purchased
  lists, no directory harvesting, no scraped dumps (s.13).
- Address on the suppression list, or previously contacted within 90 days.
- Personal-looking address with no role relevance.
- No specific verified defect for that business (a generic pitch destroys the rationale anyway).

## Message content requirements — apply even where consent exists

- Accurate sender identity: real name, working reply address, working phone (s.10).
- A plain-language **reason for contacting this specific business**.
- Functional opt-out that works by plain reply, honoured immediately and permanently (s.11).
- No price (APR-004 still open). No misleading or unverifiable claim.

## Self-imposed limits

- **20 first-touch emails/day maximum**; one business per 90 days; **one follow-up maximum**.
- Volume is the risk multiplier — the rationale is strongest for low-volume, individually
  researched, genuinely relevant messages and collapses under blasting.

## Residual risk — Dion's accepted position

No solicitor sign-off was obtained. Inference remains an untested grey area and the proof burden
stays with the sender. This module minimises and documents exposure; it does not eliminate it,
and it is compliance engineering, not legal advice.

## Still gated on Dion regardless

- **Pressing send** — Hermes never sends autonomously.
- Final pricing (APR-004).
- Gmail app password for yabigdd@gmail.com does not exist yet, so nothing can physically send.
