"""Compatibility connector: local proposal files only; no implicit Git mutations."""
import hashlib
import json
from pathlib import Path

from auditor_toolkit.common import atomic_write_text


class GitConnector:
    def __init__(self, output_dir='outputs/patches'):
        self.output_dir = Path(output_dir)

    def execute_local_patch(self, action):
        identity = hashlib.sha256(str(action.action_id).encode()).hexdigest()[:24]
        patch_file = self.output_dir / (identity + '.md')
        payload = action.to_dict() if hasattr(action, 'to_dict') else vars(action)
        atomic_write_text(patch_file, '# Remediation preview — review required\n\n```json\n' +
                          json.dumps(payload, indent=2, default=str) + '\n```\n')
        return {'status': 'preview', 'file': str(patch_file), 'committed': False,
                'message': 'Proposal saved locally; no branch, commit or remote action was performed.'}
