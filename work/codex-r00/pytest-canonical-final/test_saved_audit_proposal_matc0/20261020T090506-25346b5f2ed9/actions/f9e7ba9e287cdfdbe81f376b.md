# Proposed remediation

```json
{
  "id": "f9e7ba9e287cdfdbe81f376b",
  "finding": {
    "defect_key": "header-hsts",
    "defect": "Missing HSTS",
    "impact": "Review HTTPS deployment",
    "severity": "medium",
    "source_url": "https://example.com",
    "review_required": true,
    "check": "headers",
    "selector": "",
    "confidence": "heuristic",
    "evidence_source": "",
    "observed": "",
    "business_impact": "",
    "remediation_action": "",
    "remediation_automation": "HUMAN_REVIEW",
    "effort_band": "M",
    "finding_id": "f9e7ba9e287cdfdbe81f376b",
    "evidence_ref": "headers",
    "observed_at": "2026-10-20T09:05:06.765397+00:00",
    "evidence_summary": "headers",
    "fault_taxonomy": "security_trust",
    "confidence_assessment": {
      "class": "WEAK",
      "observed": true,
      "reproducible": true
    },
    "reproducibility": true,
    "root_cause_candidate": "security_delivery_configuration_gap"
  },
  "run_id": "20261020T090506-25346b5f2ed9",
  "status": "preview",
  "mode": "dry_run",
  "connector": "local",
  "review_required": true,
  "verification": "Run the same audit profile after the proposed fix; never infer success from a preview.",
  "fix": {
    "instructions": "Review HTTPS coverage before configuring HSTS at the reverse proxy. Do not enable preload or includeSubDomains without validation.",
    "patch_kind": "instructions",
    "automatically_applicable": false
  },
  "external_dispatch": false
}
```
