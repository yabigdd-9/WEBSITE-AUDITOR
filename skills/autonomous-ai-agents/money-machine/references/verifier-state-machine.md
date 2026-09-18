# Verifier State Machine

## States

```
┌─────────────┐
│  OBSERVED   │ ← External high-confidence source (Hunter, directory)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  CANDIDATE  │ ← External medium-confidence or pattern-derived
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                      VERIFIED_HIGH                           │
│  score >= 90                                                │
│  AND syntax_valid = 1                                       │
│  AND mx_valid = 1                                           │
│  AND business_match = 1                                     │
│  AND first_party_observed = 1                               │
│  AND disposable = 0                                         │
│  AND smtp_status != 'rejected'                              │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                   VERIFIED_MEDIUM                            │
│  score >= 75 (missing one HIGH gate)                        │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                     UNVERIFIED                               │
│  score < 75, or missing first-party observation,            │
│  or MX lookup inconclusive                                  │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                     REJECTED                                 │
│  Hard failure: disposable domain, vendor role,              │
│  wrong branch, parked domain, identity rejected,            │
│  syntax error, SMTP rejection                               │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    SUPPRESSED                                 │
│  Override from mm_suppression or contacts.do_not_contact    │
└─────────────────────────────────────────────────────────────┘
```

## Hard Gates

Each gate is a hard requirement. Missing any one drops the candidate:

| Gate | Requirement | Failure Result |
|------|-------------|----------------|
| syntax_valid | Email passes RFC validation | REJECTED |
| mx_valid | Domain has routable MX records | UNVERIFIED |
| business_match | Email domain matches canonical domain | UNVERIFIED |
| first_party_observed | Email seen on captured canonical page | UNVERIFIED |
| disposable | Domain not in blocklist | REJECTED |
| smtp_status | Not 'rejected' (not required to be 'accepted') | REJECTED if rejected |
| wrong_branch | Address belongs to a different business branch | REJECTED |
| former | Context indicates former employee | REJECTED |
| vendor | Domain/role indicates third-party vendor | REJECTED |

## Score Weights

| Component | Weight | Condition |
|-----------|--------|-----------|
| first_party | 55 | Exact address observed in captured official source |
| identity | 15 | Business/domain identity has multiple agreeing signals |
| mx | 10 | Current routable MX records |
| fresh | 5 | Observed within 7 days |
| relevant_contact | 8 | Role is suitable for general business outreach |
| independent_source | 20 | External corroboration (multiple sources) |
| person | 10 | Named person supported by context |
| smtp_non_catchall | 5 | SMTP accepted AND catch-all=no |
| second_official_page | 5 | Same email on 2+ distinct pages |

## First-Party Observation Requirements

An email is "first-party observed" when:

1. It appears in a captured page from the business's canonical domain
2. The capture hash matches the stored SHA-256
3. The capture was made within 7 days
4. The capture path is valid (artifact exists)
5. The email is found via: mailto link, visible text, obfuscated text, cloudflare obfuscation, structured data (LD+JSON), or PDF text

## External Enrichment Mapping

| Hunter Confidence | Money Machine Status |
|-------------------|----------------------|
| >= 80 | OBSERVED |
| >= 50 | CANDIDATE |
| < 50 | UNVERIFIED |

External sources never reach VERIFIED_HIGH on their own. They merge into `legacy` for evaluation.
