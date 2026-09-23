# Scoring Feature Audit

This document audits every scoring input for evidence quality and prevents weak, duplicate or speculative features from dominating ranking.

## Inspected Features
- technical severity
- business value
- fixability
- contactability
- identity confidence
- peer gap
- market context
- delivery effort

## For Each Feature
We document:
- definition
- evidence source
- range
- missing-data behavior
- confidence
- potential correlation with other features
- risk of double counting

## Outputs
- docs/research/fable/SCORING_FEATURE_AUDIT.md (this file)
- benchmarks/fable/scoring_feature_registry.yaml

## Next Steps
- Review each feature for evidence quality.
- Remove features with weak or speculative evidence.
- Adjust for double counting and correlation.
- Define clear missing-data behavior.