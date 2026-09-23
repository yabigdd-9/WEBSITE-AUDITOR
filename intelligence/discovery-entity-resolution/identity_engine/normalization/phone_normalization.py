# NZ phone normalization
# Normalize New Zealand phone numbers to a standard format.

import re

def normalize_nz_phone(phone: str) -> str:
    """Normalize a NZ phone number to a canonical format.
    Removes all non-digit characters, then formats based on length.
    Assumes NZ numbers:
      - Landline: 2-digit area code + 7-digit number (total 9 digits, e.g., 09 123 4567 -> 091234567)
      - Mobile: 02 + 8-9 digits (total 10-11 digits, e.g., 021 123 456 -> 021123456)
    Returns normalized string of digits, or empty if invalid.
    """
    if not phone:
        return ""
    # Keep only digits
    digits = re.sub(r'\D', '', phone)
    # Check if starts with 0 (NZ trunk prefix)
    if not digits.startswith('0'):
        return ""
    # Remove leading zero for processing? We'll keep it as part of the normalized form.
    # For simplicity, we return the digits as is, but we could format.
    # We'll just return the digits.
    # Additional validation: length
    if len(digits) < 9 or len(digits) > 11:
        return ""
    return digits