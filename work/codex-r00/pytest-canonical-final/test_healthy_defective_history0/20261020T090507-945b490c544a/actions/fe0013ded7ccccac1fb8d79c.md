# Proposed remediation

```json
{
  "id": "fe0013ded7ccccac1fb8d79c",
  "finding": {
    "defect_key": "image-alt",
    "defect": "Image missing alt attribute",
    "impact": "b",
    "severity": "high",
    "source_url": "https://example.com/",
    "review_required": true,
    "check": "accessibility_static",
    "selector": "img:nth-of-type(2)",
    "confidence": "observed",
    "evidence_source": "dom:img without alt attribute",
    "observed": "img src=b has no alt",
    "business_impact": "Screen-reader users miss the image meaning; weaker image SEO.",
    "remediation_action": "Add concise descriptive alt text to the image.",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "XS",
    "finding_id": "fe0013ded7ccccac1fb8d79c",
    "evidence_ref": "page",
    "observed_at": "2026-10-20T09:05:07.322344+00:00",
    "evidence_summary": "img src=b has no alt",
    "fault_taxonomy": "unknown",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "unclassified_observation"
  },
  "run_id": "20261020T090507-945b490c544a",
  "status": "preview",
  "mode": "dry_run",
  "connector": "local",
  "review_required": true,
  "verification": "Run the same audit profile after the proposed fix; never infer success from a preview.",
  "fix": {
    "instructions": "Review image purpose. Add descriptive alt text for informative images or empty alt for decorative images. Verify with a screen reader.",
    "patch_kind": "instructions",
    "automatically_applicable": false
  },
  "external_dispatch": false
}
```
