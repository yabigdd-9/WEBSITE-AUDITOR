# Proposed remediation

```json
{
  "id": "df5d9dede26cfa51123ef04a",
  "finding": {
    "defect_key": "social-meta-twitter-card",
    "defect": "Missing Twitter Card",
    "impact": "No twitter:card declared",
    "severity": "low",
    "source_url": "https://fixture.example/",
    "review_required": true,
    "check": "social_meta",
    "selector": "",
    "confidence": "observed",
    "evidence_source": "dom:meta[name=twitter:card]",
    "observed": "No <meta name=\"twitter:card\"> tag present",
    "business_impact": "Twitter/X shares show no image or rich preview.",
    "remediation_action": "Add a twitter:card meta tag (e.g. \"summary_large_image\").",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "XS",
    "finding_id": "df5d9dede26cfa51123ef04a",
    "evidence_ref": "social_meta",
    "observed_at": "2026-10-20T09:05:22.941540+00:00",
    "evidence_summary": "No <meta name=\"twitter:card\"> tag present",
    "fault_taxonomy": "unknown",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "unclassified_observation"
  },
  "run_id": "20261020T090522-dd75023a11a7",
  "status": "preview",
  "mode": "dry_run",
  "connector": "local",
  "review_required": true,
  "verification": "Run the same audit profile after the proposed fix; never infer success from a preview.",
  "fix": {
    "instructions": "Review the linked evidence and prepare a platform-specific change. Re-audit before marking verified.",
    "patch_kind": "instructions",
    "automatically_applicable": false
  },
  "external_dispatch": false
}
```
