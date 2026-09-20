"""Pipeline upgrade: checkpoint system."""
import json
from pathlib import Path

CHECKPOINT_FILE = "outputs/pipeline_checkpoint.json"

def save_checkpoint(step, data):
    Path(CHECKPOINT_FILE).write_text(json.dumps({
        "last_completed_step": step,
        "data": data,
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }))

def load_checkpoint():
    if Path(CHECKPOINT_FILE).exists():
        return json.loads(Path(CHECKPOINT_FILE).read_text())
    return None

# Add to full-pipeline.py:
# After each step, call save_checkpoint(step_number, results)
# On startup, check load_checkpoint() and skip completed steps
print("✅ Checkpoint system ready. Add save_checkpoint() after each pipeline step.")
