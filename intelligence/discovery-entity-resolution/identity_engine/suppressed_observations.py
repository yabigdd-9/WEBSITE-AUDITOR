# Preserve suppressed source observations
# Keep track of observations that were intentionally suppressed.

def suppress_observation(observation, reason):
    """Mark an observation as suppressed with a reason."""
    observation['_suppressed'] = True
    observation['_suppress_reason'] = reason
    return observation

def is_suppressed(observation):
    """Check if an observation is suppressed."""
    return observation.get('_suppressed', False)