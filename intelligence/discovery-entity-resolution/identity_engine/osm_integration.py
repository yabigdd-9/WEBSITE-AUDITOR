# Integrate OSM
# Incorporate data from OpenStreetMap.

def integrate_osm_record(raw_record):
    """Convert a raw OSM record to a common candidate format."""
    # Placeholder mapping
    return {
        'osm_id': raw_record.get('id'),
        'name': raw_record.get('name'),
        'address': raw_record.get('address'),
        'website': raw_record.get('website'),
        'phone': raw_record.get('phone'),
        'amenity': raw_record.get('amenity'),
        'source': 'osm',
        'raw': raw_record
    }

def should_integrate(record):
    """Determine if an OSM record should be integrated."""
    # For example, only those with a name and either website or phone
    return bool(record.get('name')) and (bool(record.get('website')) or bool(record.get('phone')))