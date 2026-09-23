# Source Registry

This document lists the data sources researched for potential use in WEBSITE-AUDITOR. Each source is summarized with key attributes.

## NZ Identity

### New Zealand Companies Office
- **Source ID**: nz_companies_office
- **Authority**: New Zealand Government
- **Homepage**: https://www.companiesoffice.govt.nz/
- **Access Method**: REST API
- **Authentication Required**: false
- **Cost**: free
- **License**: CC BY 4.0
- **Commercial Use**: allowed
- **Refresh Frequency**: real-time
- **Data Format**: JSON
- **Estimated Size**: growing
- **Primary Keys**: company_number
- **Useful Fields**: company_number, company_name, registration_date, status, address
- **Rate Limits**: unknown
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for NZ business identity
- **Last Verified**: 2026-09-23

### New Zealand Business Number (NZBN)
- **Source ID**: nz_nzbn
- **Authority**: New Zealand Government
- **Homepage**: https://nzbn.govt.nz/
- **Access Method**: REST API
- **Authentication Required**: false (basic), required (detailed)
- **Cost**: free (basic), paid (advanced)
- **License**: CC BY 4.0
- **Commercial Use**: allowed with attribution
- **Refresh Frequency**: real-time
- **Data Format**: JSON
- **Estimated Size**: growing
- **Primary Keys**: nzbn
- **Useful Fields**: nzbn, business_name, trading_names, registration_date, status
- **Rate Limits**: unknown
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for NZ business identity
- **Last Verified**: 2026-09-23

## Maps & Places

### Overture Maps
- **Source ID**: overture_maps
- **Authority**: Overture Maps Foundation (Linux Foundation)
- **Homepage**: https://overturemaps.org/
- **Access Method**: AWS Open Data, bulk download
- **Authentication Required**: false (public data)
- **Cost**: free
- **License**: ODbL
- **Commercial Use**: allowed
- **Refresh Frequency**: weekly
- **Data Format**: Parquet, GeoJSON
- **Estimated Size**: large (global)
- **Primary Keys**: id
- **Useful Fields**: id, name, category, confidence, sources, geometry
- **Rate Limits**: N/A for bulk download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for local business locations
- **Last Verified**: 2026-09-23

### OpenStreetMap
- **Source ID**: openstreetmap
- **Authority**: OpenStreetMap Foundation
- **Homepage**: https://www.openstreetmap.org
- **Access Method**: API, bulk download (planet.osm)
- **Authentication Required**: false (read-only API), required (editing)
- **Cost**: free
- **License**: ODbL
- **Commercial Use**: allowed with attribution
- **Refresh Frequency**: continuous
- **Data Format**: XML, JSON, Protobuf
- **Estimated Size**: very large (global)
- **Primary Keys**: id, type
- **Useful Fields**: id, type, tags, latitude, longitude, timestamp
- **Rate Limits**: API usage policy applies
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for local business locations and maps
- **Last Verified**: 2026-09-23

### Land Information New Zealand (LINZ)
- **Source ID**: linz
- **Authority**: New Zealand Government
- **Homepage**: https://data.linz.govt.nz/
- **Access Method**: REST API, bulk download
- **Authentication Required**: false (most data)
- **Cost**: free
- **License**: CC BY 4.0
- **Commercial Use**: allowed
- **Refresh Frequency**: varies by dataset
- **Data Format**: CSV, GeoJSON, Shapefile, etc.
- **Estimated Size**: medium to large (NZ-focused)
- **Primary Keys**: varies
- **Useful Fields**: varies by dataset (e.g., place names: name, latitude, longitude, type)
- **Rate Limits**: API rate limits apply
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for NZ geographic data
- **Last Verified**: 2026-09-23

## Performance

### Chrome User Experience Report (CrUX)
- **Source ID**: crux
- **Authority**: Google
- **Homepage**: https://developer.chrome.com/docs/crux/
- **Access Method**: API (requires Google Cloud project)
- **Authentication Required**: true (API key)
- **Cost**: free up to limits, then paid
- **License**: Google Terms of Service
- **Commercial Use**: allowed with restrictions
- **Refresh Frequency**: daily
- **Data Format**: JSON
- **Estimated Size**: large (global)
- **Primary Keys**: origin, date
- **Useful Fields**: origin, date, metrics, device_form_factor
- **Rate Limits**: API quota applies
- **Privacy Constraints**: aggregated, anonymized
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for real-user performance data
- **Last Verified**: 2026-09-23

### Chrome User Experience Report History (CrUX History)
- **Source ID**: crux_history
- **Authority**: Google
- **Homepage**: https://developer.chrome.com/docs/crux/api/history/
- **Access Method**: API (requires Google Cloud project)
- **Authentication Required**: true (API key)
- **Cost**: free up to limits, then paid
- **License**: Google Terms of Service
- **Commercial Use**: allowed with restrictions
- **Refresh Frequency**: daily (historical data available)
- **Data Format**: JSON
- **Estimated Size**: very large (global, historical)
- **Primary Keys**: origin, date
- **Useful Fields**: origin, date, metrics, device_form_factor
- **Rate Limits**: API quota applies
- **Privacy Constraints**: aggregated, anonymized
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for historical performance trends
- **Last Verified**: 2026-09-23

### HTTP Archive
- **Source ID**: http_archive
- **Authority**: Google, Internet Archive
- **Homepage**: https://httparchive.org/
- **Access Method**: Google BigQuery, public datasets
- **Authentication Required**: true (Google Cloud project for BigQuery)
- **Cost**: free tier, then pay for processing
- **License**: Apache License 2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: monthly
- **Data Format**: JSON (via BigQuery)
- **Estimated Size**: very large (global)
- **Primary Keys**: url, date
- **Useful Fields**: url, date, page_structure, network_requests, javascript_usage
- **Rate Limits**: BigQuery quotas
- **Privacy Constraints**: aggregated, anonymized
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for historical web technology trends
- **Last Verified**: 2026-09-23

## Historical Web

### Common Crawl
- **Source ID**: common_crawl
- **Authority**: Common Crawl Foundation
- **Homepage**: https://commoncrawl.org/
- **Access Method**: AWS Open Data, bulk download (WARC, ARC, WET files)
- **Authentication Required**: false
- **Cost**: free (storage and transfer costs may apply via cloud)
- **License**: Apache License 2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: monthly
- **Data Format**: WARC, ARC, WET, text
- **Estimated Size**: petabytes
- **Primary Keys**: url
- **Useful Fields**: url, timestamp, content, metadata
- **Rate Limits**: N/A for bulk download
- **Privacy Constraints**: contains personal data, handle with care
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for historical web crawl data (use with caution)
- **Last Verified**: 2026-09-23

### Common Crawl Web Graph
- **Source ID**: common_crawl_web_graph
- **Authority**: Common Crawl Foundation
- **Homepage**: https://commoncrawl.org/
- **Access Method**: AWS Open Data, bulk download
- **Authentication Required**: false
- **Cost**: free (storage and transfer costs may apply)
- **License**: Apache License 2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: monthly
- **Data Format**: CSV (graph edges)
- **Estimated Size**: large (global)
- **Primary Keys**: source_url, target_url
- **Useful Fields**: source_url, target_url, anchor_text
- **Rate Limits**: N/A for bulk download
- **Privacy Constraints**: derived from crawl, may contain personal data
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for link graph analysis
- **Last Verified**: 2026-09-23

### Registration Data Access Protocol (RDAP)
- **Source ID**: rdap
- **Authority**: ICANN
- **Homepage**: https://rdap.org/
- **Access Method**: RESTful API (various operators)
- **Authentication Required**: false (public data)
- **Cost**: free
- **License**: varies by operator, generally permissive
- **Commercial Use**: allowed
- **Refresh Frequency**: real-time
- **Data Format**: JSON
- **Estimated Size**: global (domain registration data)
- **Primary Keys**: domain_name
- **Useful Fields**: domain_name, status, events, entities, nameservers
- **Rate Limits**: operator-dependent
- **Privacy Constraints**: redacted personal data (GDPR)
- **Attribution Requirements**: depends on operator
- **Production Recommendation**: evaluate for domain registration data
- **Last Verified**: 2026-09-23

## Market

### Stats NZ Business Demography
- **Source ID**: stats_nz_business_demography
- **Authority**: Statistics New Zealand
- **Homepage**: https://www.stats.govt.nz/
- **Access Method**: Infoshare API, CSV download
- **Authentication Required**: false
- **Cost**: free
- **License**: CC BY 4.0
- **Commercial Use**: allowed
- **Refresh Frequency**: annual
- **Data Format**: CSV, API (JSON)
- **Estimated Size**: medium (NZ businesses)
- **Primary Keys**: year, industry_code, geography_code
- **Useful Fields**: year, industry_code, geography_code, enterprise_count, employee_count
- **Rate Limits**: API rate limits apply
- **Privacy Constraints**: aggregated, confidentialized
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for NZ market context
- **Last Verified**: 2026-09-23

## Domain

### Public Suffix List
- **Source ID**: public_suffix_list
- **Authority**: Mozilla Foundation
- **Homepage**: https://publicsuffix.org/
- **Access Method**: GitHub repository, HTTP
- **Authentication Required**: false
- **Cost**: free
- **License**: MPL-2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: frequent (daily updates)
- **Data Format**: plain text (one rule per line)
- **Estimated Size**: small (~10KB)
- **Primary Keys**: suffix
- **Useful Fields**: suffix, type, comment
- **Rate Limits**: N/A for manual download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for domain parsing and registration detection
- **Last Verified**: 2026-09-23

## Technology

### Wappalyzer Fingerprints
- **Source ID**: wappalyzer_fingerprints
- **Authority**: Wappalyzer (historically open source)
- **Homepage**: https://www.wappalyzer.com/
- **Access Method**: GitHub (mirrors of historical fingerprints)
- **Authentication Required**: false
- **Cost**: free
- **License**: MIT (historical)
- **Commercial Use**: allowed (check license for specific version)
- **Refresh Frequency**: irregular (community updates)
- **Data Format**: JSON
- **Estimated Size**: medium
- **Primary Keys**: app, version
- **Useful Fields**: app, version, cats, implies, script, src, headers, cookies, html, dom
- **Rate Limits**: N/A for manual download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for technology detection (verify license)
- **Last Verified**: 2026-09-23

### endoflife.date
- **Source ID**: endoflife_date
- **Authority**: endoflife.date project
- **Homepage**: https://endoflife.date/
- **Access Method**: REST API, GitHub
- **Authentication Required**: false
- **Cost**: free
- **License**: MIT
- **Commercial Use**: allowed
- **Refresh Frequency**: continuous (community updates)
- **Data Format**: JSON
- **Estimated Size**: small to medium
- **Primary Keys**: cycle
- **Useful Fields**: cycle, releaseDate, eol, latest, link, lts, support
- **Rate Limits**: API rate limits apply (if hosted)
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for technology lifecycle data
- **Last Verified**: 2026-09-23

## Security

### Retire.js
- **Source ID**: retirejs
- **Authority**: RetireJS community
- **Homepage**: https://retirejs.github.io/retire.js/
- **Access Method**: GitHub, npm package
- **Authentication Required**: false
- **Cost**: free
- **License**: Apache License 2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: irregular (as vulnerabilities are reported)
- **Data Format**: JSON
- **Estimated Size**: small to medium
- **Primary Keys**: name, version
- **Useful Fields**: name, version, info, fixed_in
- **Rate Limits**: N/A for manual download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for JavaScript vulnerability detection
- **Last Verified**: 2026-09-23

### Open Source Vulnerabilities (OSV)
- **Source ID**: osv
- **Authority**: OSV project (Google, GitHub, etc.)
- **Homepage**: https://osv.dev/
- **Access Method**: REST API, GitHub, GitLab
- **Authentication Required**: false
- **Cost**: free
- **License**: CC BY 4.0
- **Commercial Use**: allowed
- **Refresh Frequency**: continuous
- **Data Format**: JSON
- **Estimated Size**: growing
- **Primary Keys**: id
- **Useful Fields**: id, modified, published, affected, references
- **Rate Limits**: API rate limits apply (if using hosted instance)
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for open-source vulnerability scanning
- **Last Verified**: 2026-09-23

### Exploit Prediction Scoring System (EPSS)
- **Source ID**: epss
- **Authority**: FIRST (Forum of Incident Response and Security Teams)
- **Homepage**: https://www.first.org/epss/
- **Access Method**: REST API, CSV download
- **Authentication Required**: false
- **Cost**: free
- **License**: CC BY 4.0
- **Commercial Use**: allowed
- **Refresh Frequency**: daily
- **Data Format**: JSON, CSV
- **Estimated Size**: medium (scores for known CVEs)
- **Primary Keys**: cve
- **Useful Fields**: cve, date, score, percentile
- **Rate Limits**: API rate limits apply
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for vulnerability prioritization
- **Last Verified**: 2026-09-23

### CISA Known Exploited Vulnerabilities (KEV)
- **Source ID**: cis_kev
- **Authority**: Cybersecurity and Infrastructure Security Agency (CISA)
- **Homepage**: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **Access Method**: JSON feed, CSV
- **Authentication Required**: false
- **Cost**: free
- **License**: Public Domain (U.S. Government work)
- **Commercial Use**: allowed
- **Refresh Frequency**: frequent (as vulnerabilities are added)
- **Data Format**: JSON
- **Estimated Size**: small to medium
- **Primary Keys**: cveID
- **Useful Fields**: cveID, vendorProject, product, dateAdded, shortDescription, requiredAction, dueDate, knownRansomwareCampaignUse
- **Rate Limits**: N/A for manual download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required (though public domain)
- **Production Recommendation**: evaluate for known exploited vulnerability detection
- **Last Verified**: 2026-09-23

## Privacy & Third Party

### DuckDuckGo Tracker Radar
- **Source ID**: tracker_radar
- **Authority**: DuckDuckGo
- **Homepage**: https://spreadprivacy.com/tracker-radar/
- **Access Method**: GitHub repository, npm package
- **Authentication Required**: false
- **Cost**: free
- **License**: Apache License 2.0
- **Commercial Use**: allowed
- **Refresh Frequency**: irregular (as updates are made)
- **Data Format**: JSON
- **Estimated Size**: medium
- **Primary Keys**: domain
- **Useful Fields**: domain, parentCompany, categories, domestic, prevalence, fingerprinting, cookies, performance, policy
- **Rate Limits**: N/A for manual download
- **Privacy Constraints**: none
- **Attribution Requirements**: Required
- **Production Recommendation**: evaluate for tracker and privacy detection
- **Last Verified**: 2026-09-23