from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

MODEL_PATH = Path("/Users/dd/llama-2-7b-chat.Q4_K_M.gguf")
MODEL_SHA256 = "08a5566d61d7cb6b420c3e4387a39e0078e1f2fe5f055f3a03887385304d4bfa"
MODEL_SIZE = 4_081_004_224


def verify_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"ready": False, "reason": "model file is missing", "path": str(path)}
    size = path.stat().st_size
    if size != MODEL_SIZE:
        return {"ready": False, "reason": "model size mismatch", "size": size, "path": str(path)}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    return {"ready": actual == MODEL_SHA256, "sha256": actual, "size": size, "path": str(path)}


def fallback_drafts() -> dict[str, Any]:
    return {
        "metadata": {"text": "Title: Example services\nDescription: [review required]", "source": "template"},
        "platform_fix": {"text": "Prepare an evidence-backed fix draft for review.", "source": "template"},
        "outreach": {"text": "Prepare factual outreach from verified findings.", "source": "template"},
        "content_expansion": {"text": "Outline services, proof, FAQs, and contact details.", "source": "template"},
        "bilingual": {"text": "EN: [English draft]\nMI: [te reo Māori review required]", "source": "template"},
    }


def generate_drafts(context, enabled=False, timeout=120):
    import json
    import subprocess
    import sys
    fallback = {'status': 'fallback', 'review_required': True, 'drafts': fallback_drafts(),
                'reason': 'Local generation not requested'}
    for draft in fallback['drafts'].values():
        draft['review_required'] = True
    if not enabled:
        return fallback
    integrity = verify_model()
    fallback['integrity'] = integrity
    if not integrity['ready']:
        fallback['reason'] = integrity.get('reason', 'Model integrity mismatch')
        return fallback
    try:
        result = subprocess.run([sys.executable, '-m', 'auditor_toolkit.ai_worker'],
            input=json.dumps(context), capture_output=True, text=True, timeout=timeout, check=True)
        data = json.loads(result.stdout)
        if data.get('status') != 'ok' or set(data['drafts']) != set(fallback['drafts']):
            raise ValueError('Worker did not generate every requested draft type')
        if not all(isinstance(d.get('text'), str) and d['text'].strip() and
                   d.get('source') == 'llama.cpp' for d in data['drafts'].values()):
            raise ValueError('Malformed or empty generated draft')
        data['integrity'] = integrity
        return data
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        fallback['reason'] = f'Generation failed: {type(exc).__name__}: {str(exc)[:500]}'
        return fallback
