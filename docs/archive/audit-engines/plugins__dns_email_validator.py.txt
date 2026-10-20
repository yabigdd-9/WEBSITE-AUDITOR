import subprocess
import json
import re
import os

def audit_email_security(url):
    domain = re.sub(r'^https?://', '', url).split('/')[0]
    
    # Mac user-specific path to checkdmarc
    checkdmarc_path = os.path.expanduser('~/Library/Python/3.9/bin/checkdmarc')
    
    try:
        result = subprocess.run([checkdmarc_path, domain, '--format', 'json'], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            spf = data.get("spf", {}).get("valid", False)
            dmarc = data.get("dmarc", {}).get("valid", False)
            return {"spf_valid": spf, "dmarc_valid": dmarc, "spoofing_risk": "Low" if dmarc else "Medium"}
    except Exception: pass
    return {"spf_valid": False, "dmarc_valid": False, "spoofing_risk": "Unknown/Error"}
