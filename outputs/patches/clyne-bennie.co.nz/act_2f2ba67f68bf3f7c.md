# Automated Remediation: Propose HSTS header change

**Domain:** clyne-bennie.co.nz
**Risk:** medium
**Category:** security
**Status:** dry_run

## Defect Evidence

```json
{
  "defect": {
    "issue": "Missing X-Frame-Options",
    "raw": {
      "defect": "Missing X-Frame-Options",
      "impact": "Missing X-Frame-Options \u2014 reduces XSS/clickjacking protection",
      "priority": 99,
      "fix": {
        "title": "Missing X-Frame-Options",
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

- Action ID: `act_2f2ba67f68bf3f7c`
- Requires approval: True
- Reversible: True

## Verification

- [ ] security.hsts_present
