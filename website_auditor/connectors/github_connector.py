"""Local request preview only. This release never pushes or opens remote PRs."""
from pathlib import Path
import hashlib
from auditor_toolkit.common import atomic_write_json


class GitHubConnector:
    def __init__(self, output_dir='outputs/github-previews'):
        self.output_dir = Path(output_dir)

    def push_branch(self, branch_name):
        return {'ok': False, 'status': 'disabled', 'output': 'External writes disabled in local release'}

    def _request(self, method, endpoint, payload=None):
        return {'ok': False, 'status': 'preview', 'method': method, 'endpoint': endpoint, 'payload': payload}

    def create_pull_request(self, title, body, head_branch, base_branch='main'):
        return self._request('POST', '/repos/{owner}/{repo}/pulls',
                             {'title': title, 'body': body, 'head': head_branch, 'base': base_branch})

    def execute_action(self, action):
        result = self.create_pull_request(action.name, str(action.payload), 'review-required')
        identity = hashlib.sha256(str(action.action_id).encode()).hexdigest()[:24]
        path = self.output_dir / (identity + '.json')
        atomic_write_json(path, result)
        return {'status': 'preview', 'file': str(path), 'external_dispatch': False}
