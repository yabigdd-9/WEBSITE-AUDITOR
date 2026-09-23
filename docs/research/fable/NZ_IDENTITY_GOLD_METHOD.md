# NZ Identity Gold Set Methodology

This document describes the methodology for creating a 100-record gold set for NZ entity resolution.

## Objective
Prepare a manually reviewable NZ entity-resolution benchmark before large-scale ingestion.

## Target Records: 100

## Include Cases
- simple single-location business
- multiple trading names
- parent + branch
- service-area business
- shared building/address
- similar business names
- company renamed
- company removed
- website redirects to new domain
- business with booking subdomain
- business with ecommerce subdomain
- multiple businesses under one corporate group

## Labels
- SAME_BUSINESS
- BRANCH
- PARENT_CHILD
- DIFFERENT_BUSINESS
- UNCERTAIN

## Evidence
- NZBN
- authoritative identifier
- legal name
- trading name
- address
- domain
- phone
- location

## Process
1. Collect candidate business pairs from NZBN and Companies Office data.
2. Manually label each pair based on evidence.
3. Ensure inter-annotator agreement (if multiple annotators).
4. Resolve discrepancies through discussion.
5. Validate labels against ground truth where possible.

## Output
- tests/gold/fable/nz_identity_gold.jsonl: JSONL format with records containing:
  - id: unique identifier
  - business_a: {nzbn, legal_name, trading_name, address, domain, phone, location}
  - business_b: {nzbn, legal_name, trading_name, address, domain, phone, location}
  - label: one of SAME_BUSINESS, BRANCH, PARENT_CHILD, DIFFERENT_BUSINESS, UNCERTAIN
  - evidence: list of evidence fields used for labeling
  - notes: any additional context

## Quality Control
- No synthetic guessed labels presented as real truth.
- Each label must be justified by at least two pieces of evidence.
- Records are reviewed by at least one annotator.

## Tools
- Manual review via spreadsheet or custom tool.
- Data sourced from NZBN API and Companies Office API (with appropriate rate limiting).

## Timeline
- Data collection: 2 hours
- Manual labeling: 5 hours
- Review and reconciliation: 2 hours
- Finalization: 1 hour