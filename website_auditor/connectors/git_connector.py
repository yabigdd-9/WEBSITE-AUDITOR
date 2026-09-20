import json
import subprocess
from pathlib import Path


class GitConnector:
    """Local Git connector for creating patch branches and commits."""
    
    def execute_local_patch(self, action):
        """Creates a local git branch and commits a remediation proposal."""
        domain = action.domain
        patch_dir = Path(f"outputs/patches/{domain}")
        patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Generate the patch file (Markdown with defect data)
        patch_file = patch_dir / f"{action.action_id}.md"
        content = f"# Automated Remediation: {action.name}\n\n"
        content += f"**Domain:** {domain}\n"
        content += f"**Risk:** {action.risk.value}\n"
        content += f"**Category:** {action.category}\n"
        content += f"**Status:** {action.status.value}\n\n"
        content += f"## Defect Evidence\n\n"
        content += f"```json\n{json.dumps(action.payload, indent=2)}\n```\n\n"
        content += f"## Proposed Fix\n\n"
        content += f"- Action ID: `{action.action_id}`\n"
        content += f"- Requires approval: {action.requires_approval}\n"
        content += f"- Reversible: {action.reversible}\n"
        if action.rollback_action_id:
            content += f"- Rollback action: `{action.rollback_action_id}`\n"
        content += f"\n## Verification\n\n"
        for check in action.verification_checks:
            content += f"- [ ] {check}\n"
        patch_file.write_text(content)
        
        # 2. Interact with Git
        branch_name = f"auto-fix/{action.action_id[:20]}"
        result = {"status": "simulated", "file": str(patch_file), "branch": branch_name}
        
        try:
            # Check if we are in a git repo
            subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, capture_output=True)
            
            # Create branch, add file, commit
            subprocess.run(["git", "checkout", "-b", branch_name], capture_output=True)
            subprocess.run(["git", "add", str(patch_file)], capture_output=True)
            subprocess.run(["git", "commit", "-m", f"chore(auditor): propose {action.name} for {domain}"], capture_output=True)
            
            result["status"] = "committed_locally"
            result["message"] = f"Created branch {branch_name} and committed patch."
        except subprocess.CalledProcessError:
            result["message"] = "Not a git repository or git command failed. Patch file saved locally."
        except FileNotFoundError:
            result["message"] = "Git not found. Patch file saved locally."
            
        return result
