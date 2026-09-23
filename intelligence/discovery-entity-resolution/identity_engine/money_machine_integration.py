# Integrate existing MoneyMachine records
# Incorporate data from the existing MoneyMachine system.

def integrate_money_machine_record(raw_record):
    """Convert a raw MoneyMachine record to a common candidate format."""
    # Placeholder mapping
    return {
        'mm_id': raw_record.get('id'),
        'name': raw_record.get('business_name'),
        'website': raw_record.get('website'),
        'phone': raw_record.get('phone'),
        'address': raw_record.get('address'),
        'source': 'money_machine',
        'raw': raw_record
    }

def should_integrate(record):
    """Determine if a MoneyMachine record should be integrated."""
    # For example, only those with a website or phone
    return bool(record.get('website')) or bool(record.get('phone'))