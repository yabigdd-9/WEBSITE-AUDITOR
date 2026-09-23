# Company number linking
# Link records by exact company number match (from Companies Office).

def link_by_company_number(record1_company_number: str, record2_company_number: str) -> bool:
    """Return True if two records have the same company number and both are non-empty."""
    if not record1_company_number or not record2_company_number:
        return False
    return record1_company_number.strip() == record2_company_number.strip()