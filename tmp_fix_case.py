import sys, os, json
sys.path.insert(0, '/Users/dd/WEBSITE-AUDITOR/money-machine')
from pathlib import Path

# Fix the case.json paths to be correct for the audit workflow
# load_case uses base = path.parent.parent, so for case.json at prospects/trident-electric/case/case.json
# base = prospects/trident-electric/
# So paths should be "case/3-0.html" (relative to base)

case_path = Path('/Users/dd/WEBSITE-AUDITOR/prospects/trident-electric/case/case.json')
case_data = json.loads(case_path.read_text())

# Fix paths - should be relative to base (parent.parent of case.json)
for page in case_data['pages']:
    # Extract just the case/filename part
    page['path'] = f"case/{page['path'].split('/')[-1]}"

# Also fix page_evidence paths in result
for pe in case_data['result']['identity']['page_evidence']:
    pe['capture_path'] = f"case/{pe['capture_path'].split('/')[-1]}"

# Fix evidence paths in results
for r in case_data['result']['results']:
    for e in r.get('evidence', []):
        if 'capture_path' in e:
            e['capture_path'] = f"case/{e['capture_path'].split('/')[-1]}"

case_path.write_text(json.dumps(case_data, indent=2))
print("Fixed case.json paths")
print(json.dumps(case_data['pages'], indent=2))
