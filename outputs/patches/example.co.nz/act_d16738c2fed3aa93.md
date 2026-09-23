# Automated Remediation: Propose HSTS header change

**Domain:** example.co.nz
**Risk:** medium
**Category:** security
**Status:** dry_run

## Defect Evidence

```json
{
  "defect": {
    "issue": "Missing HSTS",
    "severity": "medium"
  }
}
```

## Proposed Fix

- Action ID: `act_d16738c2fed3aa93`
- Requires approval: True
- Reversible: True

## Verification

- [ ] security.hsts_present
