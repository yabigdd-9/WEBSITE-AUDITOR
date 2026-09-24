"""
Artifact envelope definition.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import hashlib
import json

@dataclass
class ArtifactMetadata:
    artifact_id: str
    kind: str
    schema_version: str
    run_id: str
    trace_id: str
    producer: str
    producer_version: str
    git_sha: str
    config_hash: str
    policy_version: str
    input_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    sha256: str = field(default="")

    def compute_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "git_sha": self.git_sha,
            "config_hash": self.config_hash,
            "policy_version": self.policy_version,
            "input_refs": self.input_refs,
            "evidence_refs": self.evidence_refs,
            "generated_at": self.generated_at,
            "sha256": self.sha256,
        }