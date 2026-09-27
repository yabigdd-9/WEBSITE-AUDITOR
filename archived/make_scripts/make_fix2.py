import pathlib

# The confirmed key from your JSON: ['domain','score','total_defects','generated','actions','summary']
# Defects live under "actions". We'll check it explicitly, then fall back to god-mode.

SMART_EXTRACT = '''
DEFECT_KEYS = ["actions", "defects", "issues", "remediations", "fixes", "findings", "results"]

def extract_defects_smart(data):
    """Check known keys first, then fall back to recursive god-mode hunt."""
    if not isinstance(data, dict):
        return []
    # 1. Direct key lookup (fast path)
    for key in DEFECT_KEYS:
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    # 2. God-mode recursive fallback
    return _god_mode(data)

def _god_mode(data):
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                s = str(v[0]).lower()
                if any(x in s for x in ["fix", "issue", "defect", "priority", "missing", "broken", "error", "action"]):
                    found.extend(v)
            elif isinstance(v, dict):
                found.extend(_god_mode(v))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        found.extend(_god_mode(item))
    elif isinstance(data, list):
        for item in data:
            found.extend(_god_mode(item))
    return found
'''

# ============================================
# PATCH revenue_report.py
# ============================================
rev_path = pathlib.Path("revenue_report.py")
rcode = rev_path.read_text()

# Remove the old extract_defects function if present (from previous patch)
import re
rcode = re.sub(r'def extract_defects\(data\):.*?(?=\n\ndef |\n\nclass |\ndef main)', '', rcode, flags=re.DOTALL)

# Insert smart extractor before main()
if 'extract_defects_smart' not in rcode:
    rcode = rcode.replace('def main():', SMART_EXTRACT + '\n\ndef main():')

# Point extraction to the smart function
rcode = rcode.replace('defects = extract_defects(data)', 'defects = extract_defects_smart(data)')
rcode = rcode.replace('defects = data.get("defects", data.get("issues", []))', 'defects = extract_defects_smart(data)')

rev_path.write_text(rcode)
print("✅ revenue_report.py → smart extractor (checks 'actions' key first)")


# ============================================
# PATCH generator.py
# ============================================
gen_path = pathlib.Path("website_auditor/reporting/generator.py")
gcode = gen_path.read_text()

# Remove old _extract_defects if present
gcode = re.sub(r'def _extract_defects\(data\):.*?(?=\n\nclass |\ndef )', '', gcode, flags=re.DOTALL)

# Insert smart extractor before class
if 'extract_defects_smart' not in gcode:
    gcode = gcode.replace('class MonthlyReportGenerator:', SMART_EXTRACT + '\n\nclass MonthlyReportGenerator:')

# Point to smart function
gcode = gcode.replace('defects = _extract_defects(rem)', 'defects = extract_defects_smart(rem)')
gcode = gcode.replace('defects = rem.get("defects", rem.get("issues", []))', 'defects = extract_defects_smart(rem)')

gen_path.write_text(gcode)
print("✅ generator.py → smart extractor (checks 'actions' key first)")

print("\n🔧 Schema-locked fix applied. 'actions' key will now be read correctly.")
