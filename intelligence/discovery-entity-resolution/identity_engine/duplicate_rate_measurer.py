# Measure duplicate rate
# Measure the rate of duplicate records in the resolved identities.

def measure_duplicate_rate(predicted_clusters):
    """Measure the proportion of clusters that have more than one member.
    Placeholder: return 0.0.
    """
    if not predicted_clusters:
        return 0.0
    multi_member = sum(1 for c in predicted_clusters if len(c['members']) > 1)
    return multi_member / len(predicted_clusters)