---
name: data-gap-analysis
description: Analysis of missing data types for website auditor and plan to incorporate them
---

Missing high-value local-first data:
- Technology stack detection (CMS, frameworks, libraries)
- JavaScript library vulnerability detection (local DB like retire.js)
- Enhanced structured data validation (field-level validation for types like LocalBusiness)
- Cookie consent detection (banner patterns)
- hreflang validation
- Language attribute (<html lang>)
- Image optimization (size, format, lazy loading)
- Third-party request enumeration
- Console error collection (from browser)
- Twitter Card meta tags
- Server technology headers (powered-by detection)

Plan:
1. Add new check modules in auditor_toolkit/ (tech.py, vuln_js.py, structured_validation.py, etc.)
2. Extend network.py/hygiene.py for header/cookie analysis
3. Update models.py REGISTRY with new CheckDefinitions
4. Hook new checks into pipeline.py (conditional on profile/flags)
5. Update AuditOptions to enable/disable new categories
6. Ensure evidence collection follows P5 (observed evidence, remediation, effort bands)
7. Keep checks deterministic, zero-paid-token, local-first
8. Write unit tests in toolkit_tests/
9. Validate on sample sites before enabling by default