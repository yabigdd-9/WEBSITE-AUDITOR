"""
Example application of idempotency to ingestion.
"""

from .function import compute_idempotency_key, check_idempotency, store_idempotency_result

# In-memory storage for demonstration (would be SQLite operational record in practice)
_idempotency_store = {}

def ingest_data(entity_type: str, entity_id: str, operation: str, input_data: dict) -> dict:
    """
    Ingest data with idempotency check.
    Returns previous result if already processed, otherwise processes and stores result.
    """
    policy_version = "1.0.0"  # Could be retrieved from policy engine
    key = compute_idempotency_key(entity_type, entity_id, operation, input_data, policy_version)

    # Check if already processed
    previous_result = check_idempotency(key, _idempotency_store)
    if previous_result is not None:
        # Return prior result (duplicate execution harmless)
        return {"status": "duplicate", "result": previous_result, "idempotency_key": key}

    # Process the data (placeholder)
    result = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "operation": operation,
        "processed_at": "2026-09-24T00:00:00Z",
        "input_data": input_data
    }

    # Store result
    store_idempotency_result(key, result, _idempotency_store)
    return {"status": "processed", "result": result, "idempotency_key": key}