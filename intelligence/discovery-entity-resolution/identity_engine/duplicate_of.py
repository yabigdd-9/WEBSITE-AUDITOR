# Add duplicate_of relationships
# Link records that are duplicates of each other.

def add_duplicate_of(record, duplicate_of_key):
    """Add a duplicate_of link to a record.
    Args:
        record: dict representing the record.
        duplicate_of_key: the key (e.g., NZBN) of the record it is a duplicate of.
    """
    record['duplicate_of'] = duplicate_of_key
    return record

def get_duplicate_of(record):
    """Get the duplicate_of key from a record."""
    return record.get('duplicate_of')