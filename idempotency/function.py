"""
Canonical idempotency function.
"""

import hashlib
import json
from typing import Any, Dict, Optional

def compute_idempotency_key(
    entity_type: str,
    entity_id: str,
    operation: str,
    input_data: Any,
    policy_version: str = "1.0.0"
) -> str:
    """
    Compute canonical idempotency key:
    entity_type + entity_id + operation + input_hash + policy_version
    """
    # Compute hash of input data (JSON string with sorted keys for consistency)
    if isinstance(input_data, (dict, list)):
        input_str = json.dumps(input_data, sort_keys=True)
    else:
        input_str = str(input_data)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()

    # Combine components
    key_string = f"{entity_type}:{entity_id}:{operation}:{input_hash}:{policy_version}"
    return hashlib.sha256(key_string.encode()).hexdigest()

def check_idempotency(
    key: str,
    storage: Dict[str, Any]  # In practice, this would be a database or cache
) -> Optional[Any]:
    """
    Check if key exists in storage and return previous result if present.
    Returns None if key not found.
    """
    return storage.get(key)

def store_idempotency_result(
    key: str,
    result: Any,
    storage: Dict[str, Any]
) -> None:
    """Store result for idempotency key."""
    storage[key] = result