# Opportunity Intelligence Engine

This module implements the opportunity intelligence model for WEBSITE-AUDITOR, separating technical health from commercial opportunity and computing an actionable opportunity score.

## Components

- **features.py**: Implements each feature function (verified_need, identity_confidence, etc.)
- **aggregator.py**: Computes opportunity score from raw data with double-counting controls and confidence
- **scoring.py**: Core opportunity score formula (product of features divided by delivery_effort)
- **bands.py**: Maps opportunity score to bands (EXECUTE_NOW, VALIDATE_NEXT, BACKLOG, HOLD, KILL)
- **confidence.py**: Placeholder confidence score calculation
- **offers.py**: Maps opportunity to primary and secondary offer families
- **explain.py**: Generates explanations for the opportunity score
- **review.py**: Creates a human review packet for the opportunity
- **schema.py**: Defines the opportunity schema (not yet used in code)
- **BASE_INFO.txt**: Basic information about the opportunity engine

## Usage

See `test_aggregator.py` for an example of how to use the aggregator to compute an opportunity score from raw data.

## Feature Groups (for double-counting control)

- **technical_need**: verified_need, fixability, peer_gap, expected_remediation_value
- **commercial_function**: business_value, contactability
- **identity**: identity_confidence, website_confidence
- **market**: market_context
- **meta**: evidence_quality (no double counting)

The opportunity score is computed as:
  score = (technical_need_score * commercial_function_score * identity_score * market_score * evidence_quality_score) / delivery_effort

where each group score is the average of the features in that group.

## Opportunity Score Bands

- EXECUTE_NOW: score >= 0.8
- VALIDATE_NEXT: 0.6 <= score < 0.8
- BACKLOG: 0.4 <= score < 0.6
- HOLD: 0.2 <= score < 0.4
- KILL: score < 0.2

## Notes

This is a preliminary implementation. Some features use placeholder logic and should be replaced with proper implementations based on the data sources (identity engine, website ownership engine, competitor benchmark engine, etc.).