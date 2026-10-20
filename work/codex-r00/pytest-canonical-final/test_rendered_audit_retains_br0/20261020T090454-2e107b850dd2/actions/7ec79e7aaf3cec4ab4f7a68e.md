# Proposed remediation

```json
{
  "id": "7ec79e7aaf3cec4ab4f7a68e",
  "finding": {
    "defect_key": "social-meta-og-image",
    "defect": "Missing og:image",
    "impact": "No Open Graph image for social sharing",
    "severity": "medium",
    "source_url": "https://example.com/",
    "review_required": true,
    "check": "social_meta",
    "selector": "",
    "confidence": "observed",
    "evidence_source": "dom:meta[property=og:image]",
    "observed": "No <meta property=\"og:image\"> tag present",
    "business_impact": "Social shares show no thumbnail, reducing visual appeal and click-through.",
    "remediation_action": "Add an og:image meta tag pointing to a 1200x630 image.",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "XS",
    "finding_id": "7ec79e7aaf3cec4ab4f7a68e",
    "evidence_ref": "social_meta",
    "observed_at": "2026-10-20T09:04:54.420287+00:00",
    "evidence_summary": "No <meta property=\"og:image\"> tag present",
    "fault_taxonomy": "unknown",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "unclassified_observation"
  },
  "run_id": "20261020T090454-2e107b850dd2",
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
