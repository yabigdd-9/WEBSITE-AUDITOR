import pathlib
code = """
import json, sys, os
from pathlib import Path
from website_auditor.connectors.github_connector import GitHubConnector
from website_auditor.models import Action

def main():
    push_mode = "--push" in sys.argv
    actions_file = Path("outputs/actions/proposed_actions.jsonl")
    
    if not actions_file.exists():
        print("No proposed actions found. Run 'python3 run_all.py <url>' first.")
        return
        
    connector = GitHubConnector()
    
    if push_mode and not connector.token:
        print("--push mode requires GITHUB_TOKEN environment variable.")
        return
        
    print(f"Starting Deployment ({'LIVE PUSH' if push_mode else 'LOCAL SAFE MODE'})")
    print(f"Repo: {connector.repo_info or 'Local Only'}")
    print("-" * 50)
    
    os.system("git checkout main >/dev/null 2>&1 || git checkout master >/dev/null 2>&1")
    
    count = 0
    for line in actions_file.read_text().splitlines():
        if not line.strip(): continue
        try:
            action = Action.from_dict(json.loads(line))
            print(f"Processing: {action.name} for {action.domain}")
            result = connector.execute(action, push=push_mode)
            if result.get("status") == "pr_opened":
                print(f"   PR Opened: {result['url']}")
            elif result.get("status") == "local_branch_created":
                print(f"   Local Branch: {result['branch']} (Safe Mode)")
            else:
                print(f"   Issue: {result.get('error', 'Unknown')}")
            count += 1
        except Exception as e:
            print(f"   Error: {e}")
            
    print(f"Finished. Processed {count} actions.")

if __name__ == "__main__":
    main()
"""
pathlib.Path('deploy_fixes.py').write_text(code)
print('✅ Deployment script created safely')
