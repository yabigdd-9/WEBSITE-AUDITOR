# Double-Counting and Correlation Risks

This document identifies risks of double-counting and correlation among scoring features.

## Risks Identified
- Technical severity and false-positive rate may be correlated (e.g., noisy checks).
- Business value and fixability may overlap (high-value issues often easier to fix).
- Identity confidence and peer gap may correlate (businesses with clear identity may have fewer peers).
- Market context and vertical demand context may overlap.

## Mitigation Strategies
- Perform correlation analysis on pilot data.
- Adjust scoring weights to account for correlated features.
- Combine highly correlated features into a single metric.
- Use principal component analysis or similar techniques to reduce dimensionality.

## Next Steps
- Collect pilot data to measure correlations.
- Review each feature pair for potential double counting.
- Define clear, orthogonal features where possible.