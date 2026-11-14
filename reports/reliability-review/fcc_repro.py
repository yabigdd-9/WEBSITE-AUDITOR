"""Reproduce the count_tokens event-loop stall and measure its impact on /health.

Builds a large Anthropic count_tokens payload (long history + tool results +
tool schemas), fires it at the target instance, and concurrently probes /health.
No model generation happens: count_tokens never contacts a provider.

Usage:
  python repro.py [port] [health_probes] [count_tokens_requests] [concurrency]
"""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time

sys.path.insert(0, "/Users/dd/.hermes/cache/scratch/fcc-harness")
from probe import one_request, summarize  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8182
HEALTH_PROBES = int(sys.argv[2]) if len(sys.argv) > 2 else 60
CT_REQUESTS = int(sys.argv[3]) if len(sys.argv) > 3 else 8
CONCURRENCY = int(sys.argv[4]) if len(sys.argv) > 4 else 4

MESSAGES = 300
TEXT_CHARS = 20_000
TOOLS = 15


def heavy_payload() -> bytes:
    msgs: list[dict] = []
    for i in range(MESSAGES):
        if i % 3 == 2:
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": f"toolu_{i:04d}",
                            "content": "tool output line. " * (TEXT_CHARS // 18),
                        }
                    ],
                }
            )
        elif i % 3 == 1:
            msgs.append(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": f"toolu_{i:04d}",
                            "name": f"tool_{i % TOOLS}",
                            "input": {"path": f"synthetic/file_{i}.py", "blob": "y" * TEXT_CHARS},
                        }
                    ],
                }
            )
        else:
            msgs.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "lorem ipsum dolor sit amet " * (TEXT_CHARS // 27)}
                    ],
                }
            )

    tools = [
        {
            "name": f"tool_{i}",
            "description": "d" * 800,
            "input_schema": {
                "type": "object",
                "properties": {
                    f"p{j}": {"type": "string", "description": "s" * 400} for j in range(10)
                },
            },
        }
        for i in range(TOOLS)
    ]
    return json.dumps(
        {"model": "lmstudio/mock-model", "messages": msgs, "tools": tools}
    ).encode()


def main() -> None:
    body = heavy_payload()
    print(f"payload: {len(body) / 1024 / 1024:.2f} MiB, {MESSAGES} messages, {TOOLS} tools")

    # Sanity: the request must succeed on its own.
    status, dt, code = one_request(
        PORT, "/v1/messages/count_tokens", 60.0, body=body,
        headers={"x-api-key": "test", "anthropic-version": "2023-06-01"},
    )
    print(f"single count_tokens: {status} http={code} {dt * 1000:.0f}ms")
    if status != "ok":
        print("count_tokens did not succeed; aborting")
        return

    print(f"\nbaseline: {HEALTH_PROBES} x GET /health with no load")
    idle = [one_request(PORT, "/health", 2.0) for _ in range(HEALTH_PROBES)]
    print(json.dumps(summarize("idle /health", idle), indent=2))

    print(f"\nloaded: {CT_REQUESTS} concurrent count_tokens (c={CONCURRENCY}) + {HEALTH_PROBES} x GET /health")
    health: list = []
    health_lock = threading.Lock()
    stop = threading.Event()

    def health_worker() -> None:
        while not stop.is_set():
            result = one_request(PORT, "/health", 2.0)
            with health_lock:
                health.append(result)
                if len(health) >= HEALTH_PROBES:
                    stop.set()
                    return

    def ct_worker() -> None:
        one_request(
            PORT, "/v1/messages/count_tokens", 120.0, body=body,
            headers={"x-api-key": "test", "anthropic-version": "2023-06-01"},
        )

    prober = threading.Thread(target=health_worker)
    prober.start()
    time.sleep(0.05)

    started = time.perf_counter()
    threads: list[threading.Thread] = []
    for _ in range(CT_REQUESTS):
        t = threading.Thread(target=ct_worker)
        threads.append(t)
        t.start()
        if len(threads) >= CONCURRENCY:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()
    load_wall = time.perf_counter() - started

    stop.set()
    prober.join(timeout=10)

    report = summarize("loaded /health", health)
    report["count_tokens_wall_s"] = round(load_wall, 2)
    print(json.dumps(report, indent=2))
    if health:
        lat = sorted(dt for s, dt, _ in health if s == "ok")
        if lat:
            print(f"health max={max(lat) * 1000:.0f}ms median={statistics.median(lat) * 1000:.0f}ms")


if __name__ == "__main__":
    main()
