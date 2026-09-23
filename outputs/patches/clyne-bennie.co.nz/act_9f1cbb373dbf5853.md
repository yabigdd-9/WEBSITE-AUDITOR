# Automated Remediation: Queue defect for human review

**Domain:** clyne-bennie.co.nz
**Risk:** low
**Category:** workflow
**Status:** dry_run

## Defect Evidence

```json
{
  "defect": {
    "issue": "1 broken link(s)",
    "raw": {
      "defect": "1 broken link(s)",
      "impact": "Frustrates visitors; wastes crawl budget",
      "priority": 4,
      "fix": {
        "title": "Fix Broken Links",
        "effort": "10-30 min",
        "cost": "Free",
        "code": null,
        "docs": "https://support.google.com/webmasters/answer/9019367",
        "steps": [
          "Identify broken URLs",
          "Fix or remove links",
          "Set 301 redirects for moved pages",
          "Re-scan to verify"
        ]
      }
    }
  }
}
```

## Proposed Fix

- Action ID: `act_9f1cbb373dbf5853`
- Requires approval: False
- Reversible: True

## Verification

- [ ] review.queued
