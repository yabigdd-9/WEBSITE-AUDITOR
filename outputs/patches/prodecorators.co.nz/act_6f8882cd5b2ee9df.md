# Automated Remediation: Propose HSTS header change

**Domain:** prodecorators.co.nz
**Risk:** medium
**Category:** security
**Status:** dry_run

## Defect Evidence

```json
{
  "defect": {
    "issue": "Missing X-Content-Type",
    "raw": {
      "defect": "Missing X-Content-Type",
      "impact": "Missing X-Content-Type \u2014 reduces XSS/clickjacking protection",
      "priority": 99,
      "fix": {
        "title": "Missing X-Content-Type",
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

- Action ID: `act_6f8882cd5b2ee9df`
- Requires approval: True
- Reversible: True

## Verification

- [ ] security.hsts_present
