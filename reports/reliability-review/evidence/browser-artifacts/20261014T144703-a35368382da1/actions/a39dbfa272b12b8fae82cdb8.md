# Proposed remediation

```json
{
  "id": "a39dbfa272b12b8fae82cdb8",
  "finding": {
    "defect_key": "missing_meta_description",
    "defect": "Missing meta description",
    "impact": "Lower CTR",
    "severity": "medium",
    "source_url": "http://127.0.0.1:59106/",
    "review_required": true,
    "check": "page",
    "selector": "head > meta[name=\"description\"]",
    "confidence": "observed",
    "evidence_source": "dom:meta[name=\"description\"] absent or empty",
    "observed": "no usable meta description content",
    "business_impact": "Search snippets fall back to page text; lower click-through.",
    "remediation_action": "Write a 120-155 char meta description per key page.",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "XS",
    "finding_id": "a39dbfa272b12b8fae82cdb8",
    "evidence_ref": "page",
    "observed_at": "2026-10-14T14:47:04.208036+00:00",
    "evidence_summary": "no usable meta description content",
    "fault_taxonomy": "seo_content",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "content_discovery_configuration_gap"
  },
  "run_id": "20261014T144703-a35368382da1",
  "status": "preview",
  "mode": "dry_run",
  "connector": "local",
  "review_required": true,
  "verification": "Run the same audit profile after the proposed fix; never infer success from a preview.",
  "fix": {
    "instructions": "Draft an accurate description in the CMS SEO fields or meta[name=description]. Verify rendered HTML.",
    "patch_kind": "instructions",
    "automatically_applicable": false
  },
  "external_dispatch": false
}
```
