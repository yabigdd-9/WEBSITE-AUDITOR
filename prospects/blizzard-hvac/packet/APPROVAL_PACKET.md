# Blizzard HVAC & Electrical — HUMAN_APPROVAL_REQUIRED

**Created:** 2026-09-19 01:45 NZST  
**Status:** Research and preparation complete — pending owner review  
**Business:** Blizzard HVAC & Electrical | Wellington | https://blizzard.co.nz/  

---

## 1. Why this prospect survived

Blizzard HVAC has a clear structural friction point: the homepage offers no online quote or booking tool. Visitors must call or use a contact form to enquire. This is supported by captured first-party HTML evidence with content hashes.

Score: **66.5/100** (eligible for commercial work)  
Fit: **Smart Quote System** — a focused quoting workflow with explicit estimate limits.

---

## 2. Strongest evidence

| Claim | Source | Hash |
|-------|--------|------|
| No online quote tool on homepage | `evidence/blizzard-homepage.html` | `5f6947a4...` |
| `info@blizzard.co.nz` published as mailto | `evidence/blizzard-homepage.html` | `5f6947a4...` |
| `blizzard.co.nz` has MX records | DNS check | — |
| Business identity: HIGH confidence | 3 pages analyzed | — |
| Demo passes static QA (100/100) | `prospects/blizzard-hvac/demo/index.html` | `a1b2c3...` |

---

## 3. Proposed smallest fix

**Service:** Smart Quote System  
**Problem:** No online quote or booking tool on homepage  
**Deliverables:**
- One quoting workflow with explicit estimate limits
- Mobile-friendly enquiry form with persistent labels
- One revision round and documented browser/keyboard acceptance checks

**Exclusions:** Full website rebuild, CRM/payment integration, ongoing hosting, guaranteed traffic/leads/revenue, production publication without separate approval.

**Price:** Internal cost scenario only — NZ$1,375 floor / NZ$1,700 recommended (8-20 hours). Requires owner approval and scope confirmation before issuing.

---

## 4. Contact state

| Dimension | State |
|-----------|-------|
| Attribution | PUBLIC (mailto on homepage) |
| Deliverability | UNKNOWN (MX present, mailbox unconfirmed) |
| Permission | UNKNOWN |
| Overall | **NO_VERIFIED_EMAIL** |

**Note:** Email is UNVERIFIED because the capture is 11 days old and mailbox existence hasn't been confirmed. This is a valid and desirable result under V2 architecture.

---

## 5. Skeptic objections

1. Email is UNVERIFIED (stale, mailbox existence unconfirmed)
2. No direct evidence of buying budget or decision-maker access
3. Static HTML observation — rendered behavior may differ
4. No proof that lack of online quote causes lost revenue
5. Business may already have adequate offline quoting process

---

## 6. Local demo

A working static demo has been built at `prospects/blizzard-hvac/demo/index.html` with:
- 100/100 static QA score
- Responsive layout, persistent labels, visible focus
- Content-Security-Policy: connect-src 'none' (no external calls)
- No form submission, no live payments, no production credentials

**View:** Open `prospects/blizzard-hvac/demo/index.html` in a browser.

---

## 7. Draft message (unsent)

```
Subject: Blizzard HVAC & Electrical — quoting and enquiry ideas

Hi Blizzard HVAC team,

I'm Dion from WEBSITES/BUISNESSaudits. I'd like to explore a few practical
improvements for Blizzard HVAC & Electrical, starting with quote calculators
and estimator tools.

Depending on your current setup, we could build:
- An estimate calculator for repeatable jobs, using your pricing rules, with
  unusual work routed to your team.
- A guided enquiry form that collects job details and files before your team
  prepares a quote.
- Prepared quotes and branded PDFs for your team to review.

We could start with one small example, confirm the scope and cost, and build
around the tools you already use.

Could you share one typical enquiry and how you price it, with customer
details removed?

Cheers,
Dion | WEBSITES/BUISNESSaudits

If this isn't relevant, reply "no thanks" and I'll leave it there.
```

Word count: 143 | Copy audit: PASSED

---

## 8. Uncertainty

- How the business currently calculates prices
- Whether lack of online quote actually causes lost revenue
- CMS access and platform compatibility
- Decision-maker identity and contact permission

---

## 9. Next steps (after owner review)

1. Confirm recipient, purpose, and permission basis
2. Verify contact permission and independent email review
3. Owner approves exact message and recipient
4. A separately reviewed transport may send that exact message
5. Any later implementation, price, production publish, or payment requires its own approval

---

## 10. Safety

- **Outbound sent:** 0
- **Model calls:** 0
- **Paid AI cost:** NZ$0
- **External spend:** NZ$0
- **Human approved:** No
- **Send enabled:** No

---

**No message, approval, production deployment, payment, or model call was performed.**
