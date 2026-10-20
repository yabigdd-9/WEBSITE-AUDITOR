# Proposed remediation

```json
{
  "id": "d1fc5389dae0fdae5da4a45e",
  "finding": {
    "defect_key": "missing_open_graph_tags",
    "defect": "Missing Open Graph tags",
    "impact": "Poor social preview",
    "severity": "medium",
    "source_url": "https://example.com/",
    "review_required": true,
    "check": "page",
    "selector": "head > meta[property^=\"og:\"]",
    "confidence": "observed",
    "evidence_source": "dom:no meta[property^=og:] elements",
    "observed": "zero Open Graph tags",
    "business_impact": "Link shares render as plain text; less social traffic.",
    "remediation_action": "Add og:title, og:description, og:image tags.",
    "remediation_automation": "AUTO_PREVIEW",
    "effort_band": "S",
    "finding_id": "d1fc5389dae0fdae5da4a45e",
    "evidence_ref": "page",
    "observed_at": "2026-10-20T09:05:07.322344+00:00",
    "evidence_summary": "zero Open Graph tags",
    "fault_taxonomy": "seo_content",
    "confidence_assessment": {
      "class": "PROVEN",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "content_discovery_configuration_gap"
  },
  "run_id": "20261020T090507-945b490c544a",
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
