"""
Canonical policy interface for WEBSITE-AUDITOR.
Provides decision engine for consequential actions.
"""

import os
import yaml
import hashlib
import json
from typing import Dict, Any, Optional
from enum import Enum

class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"

class PolicyEngine:
    def __init__(self, policies_dir: str = "config/policies"):
        self.policies_dir = policies_dir
        self.policies = self._load_policies()
        self.decision_log = []

    def _load_policies(self) -> Dict[str, Any]:
        policies = {}
        if os.path.isdir(self.policies_dir):
            for filename in os.listdir(self.policies_dir):
                if filename.endswith(('.yaml', '.yml')):
                    with open(os.path.join(self.policies_dir, filename), 'r') as f:
                        policies[filename] = yaml.safe_load(f)
        return policies

    def evaluate(self, request: Dict[str, Any]) -> Decision:
        """
        Evaluate a request and return a decision.
        Request must contain: actor, action, target, environment, data_class,
        side_effect_class, cost_class, payload_hash, approval_id (optional).
        """
        # Log the request for policy logging
        self.decision_log.append({
            "request": request.copy(),
            "timestamp": os.times().elapsed  # simplified
        })

        # Extract action
        action = request.get("action", "").upper()
        target = request.get("target", "")
        data_class = request.get("data_class", "")
        side_effect_class = request.get("side_effect_class", "")

        # Safe auto actions (from plan)
        safe_auto = {"PUBLIC_READ", "LOCAL_ANALYSIS", "AUDIT",
                     "GENERATE_INTERNAL_REPORT", "SANDBOX_TEST"}
        if action in safe_auto:
            return Decision.ALLOW

        # Human review examples
        human_review_triggers = ["identity conflict", "low-confidence contact",
                                "uncertain qualification"]
        if any(trigger in action.lower() for trigger in human_review_triggers):
            return Decision.HUMAN_REVIEW

        # Human approval examples
        human_approval_triggers = ["EXTERNAL_SEND", "PRODUCTION_WRITE",
                                 "BIND_PRICE", "DEPLOY_PRODUCTION", "PAYMENT",
                                 "REFUND", "CONTRACT", "PRIVATE_DATA_EXPORT"]
        if any(trigger in action.upper() for trigger in human_approval_triggers):
            return Decision.HUMAN_APPROVAL_REQUIRED

        # Check config/policies for specific rules
        # For now, default to DENY for unknown consequential actions
        return Decision.DENY

    def get_approval_object(self, decision: Decision, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if decision in [Decision.HUMAN_APPROVAL_REQUIRED, Decision.HUMAN_REVIEW]:
            approval_id = request.get("approval_id")
            if not approval_id:
                # Generate a simple approval ID
                approval_id = hashlib.sha256(
                    json.dumps(request, sort_keys=True).encode()
                ).hexdigest()[:16]
            return {
                "approval_id": approval_id,
                "action": request.get("action"),
                "target": request.get("target"),
                "payload_hash": request.get("payload_hash"),
                "approved_by": None,
                "approved_at": None,
                "expires_at": None,
                "policy_version": "1.0.0"
            }
        return None

    def invalidate_approval(self, approval_id: str):
        # In a real implementation, we would mark approval as invalid
        # For now, just log
        self.decision_log.append({
            "event": "approval_invalidated",
            "approval_id": approval_id
        })

# Singleton instance
policy_engine = PolicyEngine()

def evaluate_action(request: Dict[str, Any]) -> Decision:
    return policy_engine.evaluate(request)

def get_approval_object(decision: Decision, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return policy_engine.get_approval_object(decision, request)

def invalidate_approval(approval_id: str):
    policy_engine.invalidate_approval(approval_id)