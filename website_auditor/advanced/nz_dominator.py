
"""
NZ Dominator: Macron validation, NZBN API, and Fair Trading Act heuristics.
"""
import re, urllib.request, json

MACRON_DICT = {
    "Maori": "Māori", "Whakatane": "Whakatāne", "Wanganui": "Whanganui",
    "Waikato": "Waikato", "Tauranga": "Tauranga", "Rotorua": "Rotorua",
    "Kawerau": "Kawerau", "Opotiki": "Ōpōtiki", "Whangarei": "Whangārei"
}

ILLEGAL_CLAIMS = [
    r"\bguaranteed cheapest\b", r"\bnumber one in nz\b", 
    r"\bfree \w+ \(no catch\)\b", r"\bcountdown timer\b"
]

def check_macrons(html_text):
    missing = []
    for wrong, right in MACRON_DICT.items():
        if re.search(rf"\b{wrong}\b", html_text, re.IGNORECASE) and right not in html_text:
            missing.append(f"Missing macron: '{wrong}' should be '{right}'")
    return missing

def check_fair_trading(html_text):
    flags = []
    for pattern in ILLEGAL_CLAIMS:
        if re.search(pattern, html_text, re.IGNORECASE):
            flags.append(f"Potential Fair Trading Act risk: '{pattern}'")
    return flags

def lookup_nzbn(nzbn_number):
    """Stub for NZBN public register API."""
    if not nzbn_number or len(str(nzbn_number)) != 13:
        return {"status": "invalid_format"}
    # In production, this hits the public NZBN API
    return {"status": "verified_stub", "nzbn": nzbn_number, "entity_type": "NZ Limited Company"}
