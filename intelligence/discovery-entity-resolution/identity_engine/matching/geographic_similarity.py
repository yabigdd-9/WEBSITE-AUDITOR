# Geographic similarity
# Compute similarity based on geographic distance.

from math import radians, cos, sin, asin, sqrt

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    # Radius of earth in kilometers. Use 3956 for miles
    r = 6371
    return c * r

def geographic_similarity(lat1: float, lon1: float, lat2: float, lon2: float, max_distance_km: float = 50.0) -> float:
    """Return similarity between 0 and 1 based on distance.
    Similarity = 1 - (distance / max_distance) clipped to [0,1].
    """
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    distance = haversine(lat1, lon1, lat2, lon2)
    similarity = max(0.0, 1.0 - distance / max_distance_km)
    return similarity