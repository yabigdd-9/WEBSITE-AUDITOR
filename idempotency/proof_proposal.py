"""
Example application of idempotency to proof and proposal.
"""

from .function import compute_idempotency_key, check_idempotency, store_idempotency_result

# In-memory storage for demonstration
_pp_store = {}

def process_proof_proposal(entity_type: str, entity_id: str, operation: str, input_data: dict) -> dict:
    """
    Process proof/proposal with idempotency check.
    Returns previous result if already processed, otherwise processes and stores result.
    """
    policy_version = "1.0.0"
    key = compute_idempotency_key(entity_type, entity_id, operation, input_data, policy_version)

    previous_result = check_idempotency(key, _pp_store)
    if previous_result is not None:
        return {"status": "duplicate", "result": previous_result, "idempotency_key": key}

    # Process the proof/proposal (placeholder)
    result = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "operation": operation,
        "completed_at": "2026-09-24T00:00:00Z",
        "output": {}  # placeholder
    }

    store_idempotency_result(key, result, _pp_store)
    return {"status": "processed", "result": result, "idempotency_key": key}