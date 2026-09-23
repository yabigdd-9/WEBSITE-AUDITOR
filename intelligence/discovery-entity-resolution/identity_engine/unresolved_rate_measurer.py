# Measure unresolved rate
# Measure the rate of records that could not be resolved to a confident identity.

def measure_unresolved_rate(predicted_clusters, total_records):
    """Measure the proportion of records that are in singleton clusters with low confidence.
    Placeholder: return 0.0.
    """
    if total_records == 0:
        return 0.0
    unresolved = sum(len(c['members']) for c in predicted_clusters if len(c['members']) == 1 and c.get('confidence', 1.0) < 0.5)
    return unresolved / total_records