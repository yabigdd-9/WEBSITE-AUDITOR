import json
import requests
import sys
import os

# --- CONFIGURATION ---
# Set GITHUB_TOKEN in your environment (.env, master.env, shell rc)
# Generate a token at https://github.com/settings/tokens (needs 'repo' scope)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

REPO_OWNER = "Yabigdd-9"
REPO_NAME = "YOUR_REPOSITORY_NAME"

def create_github_issue(title, body, labels):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"title": title, "body": body, "labels": labels}
    
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        print(f"✅ Issue created: {response.json()['html_url']}")
    else:
        print(f"❌ Failed to create issue: {response.text}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 github_issue_exporter.py <audit_report.json>")
        sys.exit(1)
        
    filename = sys.argv[1]
    with open(filename, 'r') as f:
        data = json.load(f)

    url = data.get("url", "Unknown URL")
    defects = data.get("defects", [])
    
    # Group high-priority defects into a single comprehensive issue
    if len(defects) > 3:
        issue_title = f"[Audit] Critical Defects Found on {url}"
        
        body = f"## 🚨 Automated Website Audit Report\n\n"
        body += f"**Target:** {url}\n"
        body += f"**Tech Stack Detected:** {', '.join(data.get('tech_stack_detected', ['Unknown']))}\n\n"
        body += f"### 🐛 Defects Found ({len(defects)})\n"
        
        for d in defects[:10]: # Limit to top 10 to avoid spam
            body += f"- **{d['defect']}**: {d['impact']}\n"
            
        body += f"\n### 📊 Email Security\n"
        email_sec = data.get("email_security_dns", {})
        body += f"- SPF Valid: {'✅ Yes' if email_sec.get('spf_valid') else '❌ No'}\n"
        body += f"- DMARC Valid: {'✅ Yes' if email_sec.get('dmarc_valid') else '❌ No'}\n"
        
        create_github_issue(issue_title, body, ["bug", "audit", "automated"])
    else:
        print("🎉 Site is relatively healthy (less than 4 defects). No GitHub issue created!")

if __name__ == "__main__":
    main()
