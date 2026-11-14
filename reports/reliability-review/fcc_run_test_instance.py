"""Run one isolated FCC instance on a spare port with a loop-lag monitor.

No real provider keys are visible: HOME is redirected to a throwaway config dir
whose .env points MODEL at a local mock upstream.

Usage: python run_test_instance.py [port]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8182

sys.path.insert(0, str(HARNESS))
from loop_lag import install  # noqa: E402

import uvicorn  # noqa: E402

from free_claude_code.config.loader import get_settings  # noqa: E402
from free_claude_code.runtime.bootstrap import build_asgi_app  # noqa: E402

LAG_LOG = os.environ.get("FCC_LOOP_LAG_LOG", str(HARNESS / "loop_lag.jsonl"))


async def main() -> None:
    monitor_task = install(LAG_LOG, threshold=float(os.environ.get("FCC_LAG_THRESHOLD", "0.05")))

    settings = get_settings()
    app = build_asgi_app(settings)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level=os.environ.get("FCC_TEST_LOG_LEVEL", "warning"),
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    print(f"isolated FCC instance starting on http://127.0.0.1:{PORT}", flush=True)
    try:
        await server.serve()
    finally:
        monitor_task.cancel()
        monitor = getattr(monitor_task, "monitor", None)
        if monitor is not None:
            print(
                f"loop-lag summary: samples={monitor.samples} "
                f"stalls={monitor.stalls} max_lag_ms={monitor.max_lag * 1000:.1f}",
                flush=True,
            )
            monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
