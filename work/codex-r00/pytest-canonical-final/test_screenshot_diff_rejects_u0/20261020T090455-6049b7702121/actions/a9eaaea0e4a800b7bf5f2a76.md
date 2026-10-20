# Proposed remediation

```json
{
  "id": "a9eaaea0e4a800b7bf5f2a76",
  "finding": {
    "defect_key": "images-missing-dimensions",
    "defect": "Images missing width/height (1)",
    "impact": "Layout shift risk; images without explicit dimensions cause CLS",
    "severity": "medium",
    "source_url": "https://example.com/",
    "review_required": true,
    "check": "images",
    "selector": "",
    "confidence": "observed",
    "evidence_source": "dom:img element",
    "observed": "1 of 1 images lack width and height attributes",
    "business_impact": "Images without explicit dimensions cause Cumulative Layout Shift (CLS), a Core Web Vital that hurts user experience and SEO.",
    "remediation_action": "Add explicit width and height attributes to all images.",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "S",
    "finding_id": "a9eaaea0e4a800b7bf5f2a76",
    "evidence_ref": "images",
    "observed_at": "2026-10-20T09:04:55.268489+00:00",
    "evidence_summary": "1 of 1 images lack width and height attributes",
    "fault_taxonomy": "unknown",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "unclassified_observation"
  },
  "run_id": "20261020T090455-6049b7702121",
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
