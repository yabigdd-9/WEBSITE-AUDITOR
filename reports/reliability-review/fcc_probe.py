"""Latency probe for an FCC /health endpoint.

Read-only GETs, no auth token, no model payload. Reports p50/p95/p99 and the
timeout rate. Also usable as a concurrent load driver against the mock upstream.

Usage:
  python probe.py health [port] [count] [timeout]
  python probe.py load   [port] [count] [timeout] [concurrency]
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time


def one_request(port: int, path: str, timeout: float, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[str, float, int]:
    t0 = time.perf_counter()
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        hdrs = {"Host": f"127.0.0.1:{port}", "Connection": "close"}
        hdrs.update(headers or {})
        if body is not None:
            hdrs["Content-Type"] = "application/json"
            hdrs["Content-Length"] = str(len(body))
        request = f"GET {path} HTTP/1.1\r\n" if body is None else f"POST {path} HTTP/1.1\r\n"
        request += "".join(f"{k}: {v}\r\n" for k, v in hdrs.items()) + "\r\n"
        s.sendall(request.encode() + (body or b""))
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        dt = time.perf_counter() - t0
        status = 0
        if data.startswith(b"HTTP/"):
            try:
                status = int(data.split(b" ", 2)[1])
            except (IndexError, ValueError):
                status = 0
        return ("ok" if status else "empty"), dt, status
    except socket.timeout:
        return "timeout", time.perf_counter() - t0, 0
    except Exception as exc:  # noqa: BLE001
        return f"error:{type(exc).__name__}", time.perf_counter() - t0, 0


def summarize(name: str, results: list[tuple[str, float, int]]) -> dict:
    lat = sorted(dt for status, dt, _ in results if status == "ok")
    outcomes: dict[str, int] = {}
    for status, _, _ in results:
        outcomes[status] = outcomes.get(status, 0) + 1
    n = len(results)
    report = {
        "name": name,
        "requests": n,
        "outcomes": outcomes,
        "timeout_rate": round(outcomes.get("timeout", 0) / n * 100, 1),
        "success_rate": round(outcomes.get("ok", 0) / n * 100, 1),
    }
    if lat:
        report |= {
            "p50_ms": round(lat[len(lat) // 2] * 1000, 1),
            "p95_ms": round(lat[min(int(len(lat) * 0.95), len(lat) - 1)] * 1000, 1),
            "p99_ms": round(lat[min(int(len(lat) * 0.99), len(lat) - 1)] * 1000, 1),
            "max_ms": round(lat[-1] * 1000, 1),
        }
    return report


def run_parallel(fn, count: int, concurrency: int) -> list[tuple[str, float, int]]:
    results: list[tuple[str, float, int]] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        out = fn(idx)
        with lock:
            results.append(out)

    threads = []
    for i in range(count):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        if len(threads) >= concurrency:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()
    return results


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "health"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8182
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    timeout = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0

    if mode == "health":
        started = time.perf_counter()
        results = [one_request(port, "/health", timeout) for _ in range(count)]
        report = summarize(f"GET /health x{count} port {port}", results)
        report["wall_s"] = round(time.perf_counter() - started, 1)
    elif mode == "load":
        concurrency = int(sys.argv[5]) if len(sys.argv) > 5 else 4
        body = json.dumps(
            {
                "model": "mock-model",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "ping"}],
            }
        ).encode()
        started = time.perf_counter()
        results = run_parallel(
            lambda _i: one_request(port, "/v1/messages", timeout, body=body,
                                   headers={"x-api-key": "test", "anthropic-version": "2023-06-01"}),
            count,
            concurrency,
        )
        report = summarize(f"POST /v1/messages x{count} port {port} c={concurrency}", results)
        report["wall_s"] = round(time.perf_counter() - started, 1)
    else:
        raise SystemExit(f"unknown mode {mode!r}")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
