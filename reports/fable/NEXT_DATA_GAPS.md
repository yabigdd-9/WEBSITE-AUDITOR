# Next Data Gaps

This document identifies remaining gaps in data and intelligence after completing the Fable parallel research phase.

## Identified Gaps
1. **Real-time NZBN API usage**: Need to evaluate rate limits and data freshness for large-scale ingestion.
2. **Historical performance data**: CrUX history is available but requires significant storage and processing.
3. **Link graph data**: Common Crawl web graph is large and requires graph processing capabilities.
4. **Technology fingerprints**: Need to verify license and update frequency for Wappalyzer alternatives.
5. **Vulnerability data feeds**: OSV, EPSS, and KEV require API integration and regular updates.
6. **Tracker data**: DuckDuckGo Tracker Radar requires periodic updates and may have coverage gaps.
7. **Market intelligence**: Stats NZ data is annual and may not reflect real-time conditions.
8. **Structured data validation**: Need to distinguish between missing recommended fields and invalid schema.
9. **False-positive validation**: Requires manual review to confirm false positives in edge cases.
10. **Scoring feature correlations**: Need to measure double-counting and correlation risks with pilot data.

## Recommended Actions
- Prioritize data sources with clear licenses and low cost for initial integration.
- Implement caching and incremental updates for large datasets.
- Develop validation pipelines for each data source.
- Create a data versioning and provenance tracking system.
- Establish a feedback loop for false-positive identification.
- Run correlation analysis on scoring features after collecting sufficient data.

## Open Questions
- How to handle personal data in Common Crawl while maintaining usefulness?
- What is the optimal refresh frequency for each data source?
- How to balance automation with human review for evolving threats?