# Integrate NZBN
# Incorporate data from the NZBN register.

def integrate_nzbn_record(raw_record):
    """Convert a raw NZBN record to a common candidate format."""
    # Placeholder mapping
    return {
        'nzbn': raw_record.get('NZBN'),
        'business_name': raw_record.get('BusinessName'),
        'trading_name': raw_record.get('TradingName'),
        'address': raw_record.get('Address'),
        'status': raw_record.get('Status'),
        'source': 'nzbn',
        'raw': raw_record
    }

def should_integrate(record):
    """Determine if an NZBN record should be integrated."""
    # For example, only registered businesses
    return record.get('Status') == 'Registered'