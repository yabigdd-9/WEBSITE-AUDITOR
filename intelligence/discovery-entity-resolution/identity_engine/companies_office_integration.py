# Integrate Companies Office candidates
# Incorporate data from the New Zealand Companies Office.

def integrate_companies_office_record(raw_record):
    """Convert a raw Companies Office record to a common candidate format."""
    # Placeholder mapping
    return {
        'nzbn': raw_record.get('NZBN'),
        'company_number': raw_record.get('CompanyNumber'),
        'name': raw_record.get('Name'),
        'registered_address': raw_record.get('Address'),
        'status': raw_record.get('Status'),
        'source': 'companies_office',
        'raw': raw_record
    }

def should_integrate(record):
    """Determine if a Companies Office record should be integrated."""
    # For example, only active companies
    return record.get('Status') == 'Active'