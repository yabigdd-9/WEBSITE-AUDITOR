from __future__ import annotations

from pathlib import Path


def load_cpu_llama(model_path: str | Path, **kwargs):
    from llama_cpp import Llama

    defaults = {"n_gpu_layers": 0, "n_ctx": 2048, "n_threads": 2, "n_batch": 32, "verbose": False}
    defaults.update(kwargs)
    return Llama(model_path=str(model_path), **defaults)

