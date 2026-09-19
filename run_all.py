import subprocess
import json
import sys
import os

if len(sys.argv) < 2:
    print("Usage: python3 run_all.py <url>")
    sys.exit(1)

url = sys.argv[1]
print(f"🚀 Running COMPLETE 50+ Check Audit on {url}...\n")

# 1. Run Base Auditor
print("⏳ [1/2] Running Base Auditor (Security, SEO, Broken Links)...")
base_result = subprocess.run(['python3', 'website_auditor.py', url], capture_output=True, text=True)
base_json = {}
try:
    # Extract JSON from stdout (ignoring the urllib3 warnings)
    start_idx = base_result.stdout.find('{')
    if start_idx != -1:
        base_json = json.loads(base_result.stdout[start_idx:])
except Exception as e:
    print(f"Warning: Could not parse base auditor output. {e}")

# 2. Run Advanced Plugins
print("⏳ [2/2] Running Advanced Plugins (Tech Stack, UX, Images, DNS)...")
adv_result = subprocess.run(['python3', 'advanced_audit.py', url], capture_output=True, text=True)
adv_json = {}
try:
    start_idx = adv_result.stdout.find('{')
    if start_idx != -1:
        adv_json = json.loads(adv_result.stdout[start_idx:])
except Exception as e:
    print(f"Warning: Could not parse advanced auditor output. {e}")

# 3. Merge Data
merged = {**base_json, **adv_json}

# 4. Save to file
domain_name = url.replace('https://', '').replace('http://', '').split('/')[0]
filename = f"{domain_name}_full_audit.json"
with open(filename, 'w') as f:
    json.dump(merged, f, indent=2)

print(f"\n🎉 SUCCESS! Combined report saved to: {filename}")
