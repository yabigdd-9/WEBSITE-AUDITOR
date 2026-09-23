# Competitor Benchmark Method

This document defines a defensible method for comparing a local business website with nearby same-category peers.

## Research Questions
- How many peers form a useful comparison group?
- How should category similarity be handled?
- How far geographically should comparisons extend?
- How should multi-location chains be treated?
- How should missing websites be represented?
- Which technical metrics are actually comparable?

## Proposed Method

### Minimum and Preferred Peer Count
- minimum_peer_count: 5
- preferred_peer_count: 10

### Candidate Sources
- Overture Maps
- OpenStreetMap

### Dimensions
- technical health
- mobile performance
- conversion functionality
- structured data
- local SEO
- technology lifecycle

### Output
- median
- quartiles
- percentile

## Avoid
- arbitrary universal competitor winner score
- small-sample overclaiming

## Implementation Notes
- Use Overture Maps and OpenStreetMap to identify businesses in the same category within a geographic radius.
- For each peer, collect the same set of metrics as for the target business.
- Compute statistics (median, quartiles, percentile) across the peer group.
- Compare the target business to the peer group distribution.
- Handle missing websites by imputing missing data or marking as unavailable.
- Multi-location chains: treat each location separately or aggregate as appropriate based on the dimension.

## Validation
- Validate the method with manual review of a sample of businesses.
- Refine dimensions based on data availability and correlation with business outcomes.