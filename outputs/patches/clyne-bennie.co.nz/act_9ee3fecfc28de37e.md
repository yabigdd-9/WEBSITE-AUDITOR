# Automated Remediation: Propose HSTS header change

**Domain:** clyne-bennie.co.nz
**Risk:** medium
**Category:** security
**Status:** dry_run

## Defect Evidence

```json
{
  "defect": {
    "issue": "Missing Referrer-Policy",
    "raw": {
      "defect": "Missing Referrer-Policy",
      "impact": "Missing Referrer-Policy \u2014 reduces XSS/clickjacking protection",
      "priority": 99,
      "fix": {
        "title": "Missing Referrer-Policy",
        "effort": "TBD",
        "cost": "TBD",
        "code": null,
        "docs": null,
        "steps": [
          "Investigate manually"
        ]
      }
    }
  }
}
```

## Proposed Fix

- Action ID: `act_9ee3fecfc28de37e`
- Requires approval: True
- Reversible: True

## Verification

- [ ] security.hsts_present
