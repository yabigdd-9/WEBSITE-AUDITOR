import pathlib

# ============================================
# FIX 1: generator.py — handle None data + god-mode defect extraction
# ============================================
gen_path = pathlib.Path("website_auditor/reporting/generator.py")
code = gen_path.read_text()

# Fix None handling
code = code.replace('rem = data.get("remediation", {})', 'rem = data.get("remediation") or {}')
code = code.replace('rev = data.get("revenue", {})', 'rev = data.get("revenue") or {}')

# Replace fragile defects line with robust extractor
code = code.replace(
    'defects = rem.get("defects", rem.get("issues", []))',
    'defects = _extract_defects(rem)'
)

# Insert the god-mode helper right before the class definition
helper = '''
def _extract_defects(data):
    """God-mode: recursively hunt for defect lists in any JSON structure."""
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                s = str(v[0]).lower()
                if any(x in s for x in ["fix", "issue", "defect", "priority", "missing", "broken", "error"]):
                    found.extend(v)
            elif isinstance(v, dict):
                found.extend(_extract_defects(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        found.extend(_extract_defects(item))
    elif isinstance(data, list):
        for item in data:
            found.extend(_extract_defects(item))
    return found


'''
code = code.replace('class MonthlyReportGenerator:', helper + 'class MonthlyReportGenerator:')

# Also fix score extraction to be resilient
code = code.replace('score = rem.get("score", 0)', 'score = rem.get("score", 0) or 0')

gen_path.write_text(code)
print("✅ generator.py patched (None-safe + god-mode extraction)")


# ============================================
# FIX 2: revenue_report.py — god-mode defect extraction
# ============================================
rev_path = pathlib.Path("revenue_report.py")
rcode = rev_path.read_text()

# Replace the fragile extraction
rcode = rcode.replace(
    'defects = data.get("defects", data.get("issues", []))',
    'defects = extract_defects(data)'
)

# Insert helper before main()
helper2 = '''
def extract_defects(data):
    """God-mode: recursively hunt for defect lists in any JSON structure."""
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                s = str(v[0]).lower()
                if any(x in s for x in ["fix", "issue", "defect", "priority", "missing", "broken", "error"]):
                    found.extend(v)
            elif isinstance(v, dict):
                found.extend(extract_defects(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        found.extend(extract_defects(item))
    elif isinstance(data, list):
        for item in data:
            found.extend(extract_defects(item))
    return found


'''
rcode = rcode.replace('def main():', helper2 + 'def main():')

rev_path.write_text(rcode)
print("✅ revenue_report.py patched (god-mode extraction)")

print("\\n🔧 Both bugs fixed!")
