# Select Canterbury trades cohort
# Select a cohort of trades businesses in Canterbury for pilot.

def is_canterbury_trades(record):
    """Determine if a record is in the Canterbury trades cohort."""
    # Placeholder: check if address is in Canterbury and category is a trade
    address = record.get('address', '').lower()
    category = record.get('category', '').lower()
    trades = ['plumber', 'electrician', 'builder', 'carpenter']
    is_in_canterbury = 'canterbury' in address or 'christchurch' in address
    is_trade = any(trade in category for trade in trades)
    return is_in_canterbury and is_trade

def select_canterbury_trades(cohort_size=500):
    """Select up to cohort_size Canterbury trades businesses."""
    # Placeholder: in reality, we would query our data source
    return []