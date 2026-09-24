"""
Provenance ID generation: run_id, trace_id.
"""

import hashlib
import os
import uuid
from datetime import datetime
from typing import Optional

def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp and random component."""
    timestamp = datetime.utcnow().isoformat()
    random_part = uuid.uuid4().hex[:8]
    return f"run_{timestamp}_{random_part}".replace(":", "-").replace(".", "-")

def generate_trace_id() -> str:
    """Generate a unique trace ID for an event within a run."""
    return uuid.uuid4().hex

def compute_git_sha(repo_path: str = ".") -> Optional[str]:
    """Compute current git SHA of the repository."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None

def compute_config_hash(config_dir: str = "config") -> Optional[str]:
    """Compute hash of all config files (simplified)."""
    try:
        import yaml
        hash_obj = hashlib.sha256()
        for root, _, files in os.walk(config_dir):
            for f in files:
                if f.endswith(('.yaml', '.yml', '.json')):
                    path = os.path.join(root, f)
                    with open(path, 'rb') as fp:
                        hash_obj.update(fp.read())
        return hash_obj.hexdigest()
    except Exception:
        return None

def compute_policy_version(policies_dir: str = "config/policies") -> str:
    """Compute policy version based on policy files."""
    try:
        import yaml
        hash_obj = hashlib.sha256()
        for root, _, files in os.walk(policies_dir):
            for f in files:
                if f.endswith(('.yaml', '.yml')):
                    path = os.path.join(root, f)
                    with open(path, 'rb') as fp:
                        policy_data = yaml.safe_load(fp)
                        # Dump sorted keys for consistent hash
                        hash_obj.update(
                            yaml.dump(policy_data, sort_keys=True).encode()
                        )
        return hash_obj.hexdigest()[:16]
    except Exception:
        return "unknown"