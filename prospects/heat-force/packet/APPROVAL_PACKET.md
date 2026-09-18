# Heat Force — HUMAN_APPROVAL_REQUIRED

**Created:** 2026-09-19 02:15 NZST  
**Status:** Research and preparation complete — pending owner review  
**Business:** Heat Force | Christchurch | https://www.heatforce.co.nz/  

---

## 1. Why this prospect survived

Heat Force has been re-audited after a historical NZ$750 pilot was invalidated (missing-form premise was refuted — the Tradify form exists). The current packet focuses on a narrower, defensible observation: the contact page promotes an online form but no form fields appear in static HTML captures, suggesting a potential mobile friction point.

Score: **61.5/100** (eligible for commercial work)  
Fit: **Mobile Conversion Upgrade** — a focused enquiry-flow improvement with persistent labels and keyboard focus.

---

## 2. Strongest evidence

| Claim | Source | Hash |
|-------|--------|------|
| Contact page states 'online form' but no form fields in static HTML | `case/heatforce-1.html` | `a2da9363...` |
| `info@heatforce.co.nz` published as mailto | `case/heatforce-1.html` | `a2da9363...` |
| `heatforce.co.nz` has MX records | DNS check | — |
| Business identity: HIGH confidence | 3 pages analyzed | — |
| Demo passes static QA (100/100) | `prospects/heat-force/demo/index.html` | `b9fe04aa...` |

---

## 3. Proposed smallest fix

**Service:** Mobile Conversion Upgrade  
**Problem:** Potential friction in contact form rendering on mobile (form not visible in static HTML)  
**Deliverables:**
- One verified mobile bottleneck with before/after QA
- Persistent field labels and keyboard focus indicators
- One revision round and documented browser/keyboard acceptance checks

**Exclusions:** Full website rebuild, CRM/payment integration, ongoing hosting, guaranteed traffic/leads/revenue, production publication without separate approval.

**Price:** Internal cost scenario only — NZ$975 floor / NZ$1,400 recommended (5-12 hours). Requires owner approval and scope confirmation before issuing.

---

## 4. Contact state

| Dimension | State |
|-----------|-------|
| Attribution | PUBLIC (mailto on contact page) |
| Deliverability | UNKNOWN (MX present, mailbox unconfirmed) |
| Permission | UNKNOWN |
| Overall | **UNVERIFIED** |

**Note:** Email is UNVERIFIED because the capture is 11+ days old and mailbox existence hasn't been confirmed. This is a valid and desirable result under V2 architecture.

---

## 5. Skeptic objections

1. Email is UNVERIFIED (stale, mailbox existence unconfirmed)
2. No direct evidence of buying budget or decision-maker access
3. Static HTML observation — rendered behavior may differ; form may be embedded via Wix and require JS
4. No proof that any issue causes lost revenue
5. Business may already have adequate enquiry process via Tradify form
6. Historical pilot (NZ$750) was explicitly invalidated — missing-form premise was refuted

---

## 6. Local demo

A working static demo has been built at `prospects/heat-force/demo/index.html` with:
- 100/100 static QA score
- Responsive layout, persistent labels, visible focus
- Content-Security-Policy: connect-src 'none' (no external calls)
- No form submission, no live payments, no production credentials

**View:** Open `prospects/heat-force/demo/index.html` in a browser.

---

## 7. Draft message (unsent)

```
Subject: Heat Force — a few practical improvements

Hi Heat Force team,

I'm Dion from WEBSITES Business Audits. I'd like to explore a few practical
improvements for Heat Force, starting with customer proof and review
presentation.

Depending on your current setup, we could build:
- Clearer presentation of genuine customer reviews and completed work.
- Clearer service pages and a smoother mobile enquiry journey on your
  existing website.
- A guided enquiry form that collects job details and files before your
  team prepares a quote.

We could start with one small example, confirm the scope and cost, and build
around the tools you already use.

Which completed projects or customer feedback best show your work?

Cheers,
Dion | WEBSITES Business Audits

If this isn't relevant, reply "no thanks" and I'll leave it there.
```

Word count: 133 | Copy audit: PASSED

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
