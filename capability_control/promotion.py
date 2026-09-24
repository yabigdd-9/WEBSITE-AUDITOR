"""
Promotion records: track feature promotions.
"""

import json
import os
from datetime import datetime

PROMOTION_LOG = "data/promotions.log"

def record_promotion(capability_id: str, from_state: str, to_state: str, reason: str = "") -> None:
    """
    Record a promotion/demotion of a capability feature state.
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "capability_id": capability_id,
        "from_state": from_state,
        "to_state": to_state,
        "reason": reason
    }
    # Ensure directory exists
    os.makedirs(os.path.dirname(PROMOTION_LOG), exist_ok=True)
    with open(PROMOTION_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def get_promotion_history(capability_id: Optional[str] = None) -> list:
    """
    Retrieve promotion history, optionally filtered by capability_id.
    """
    if not os.path.exists(PROMOTION_LOG):
        return []
    history = []
    with open(PROMOTION_LOG, 'r') as f:
        for line in f:
            entry = json.loads(line.strip())
            if capability_id is None or entry['capability_id'] == capability_id:
                history.append(entry)
    return history