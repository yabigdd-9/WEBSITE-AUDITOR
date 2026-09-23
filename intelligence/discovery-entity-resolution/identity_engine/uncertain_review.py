# Review uncertain/conflicting sample
# Review a sample of uncertain or conflicting identities.

def select_uncertain_sample(clusters, sample_size=50):
    """Select a sample of uncertain clusters for review.
    Placeholder: return first sample_size clusters with low confidence.
    """
    uncertain = [c for c in clusters if c.get('confidence', 1.0) < 0.8]
    return uncertain[:sample_size]

def review_sample(sample, reviewer):
    """Have a reviewer review the sample.
    Placeholder: do nothing.
    """
    pass