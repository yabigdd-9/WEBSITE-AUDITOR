# FCC reliability — root cause, patch, and measurements

**Date:** 2026-10-15
**Target:** `ai.website-auditor.fcc` — `fcc-server` (free-claude-code **6.2.57**) on `127.0.0.1:8082`
**Status:** root cause **proven** with captured stacks; patch applied to a copy and **verified** with A/B measurements and a RED/GREEN regression test.
**Production:** NOT modified, NOT restarted. No model request was issued. No paid provider was contacted.

---

## 1. Symptom

`GET /health` on production, 100 sequential probes, 2 s client timeout:

| metric | value |
|---|---|
| outcomes | **79 `timeout`, 21 `ok`** |
| timeout rate | **79.0 %** |
| p50 / p95 / p99 (successes) | 5 ms / 303 ms / **1585 ms** |

The handler is `async def health(): return {"status": "healthy"}` — no I/O, no
computation. Its latency is therefore a direct measurement of **event-loop
scheduling lag**, not handler cost.

## 2. Root cause

`api/routes.py:163-177` (6.2.57):

```python
@router.post("/v1/messages/count_tokens")
async def count_tokens(...):
    lease = await services.requests.acquire()
    try:
        await lease.wait_for_token_estimation()
        handler = TokenCountHandler(lease.settings, token_counter=get_token_count)
        return handler.count(request_data, request_id=get_request_id(request))  # <-- SYNC, inline
    finally:
        await lease.release()
```

`TokenCountHandler.count` is a **synchronous** method called **directly from the
`async def` route** — no `to_thread`, no `run_in_threadpool`. Inside it,
`get_token_count` → `estimate_text_tokens` → tiktoken's `cl100k_base`
`encode()` is invoked **once per content block across the entire conversation**
(every text block, thinking block, tool_use input, tool_result, and tool
schema). That is CPU-bound C work holding the GIL, executed **on the event-loop
thread**. While it runs, the loop cannot schedule anything — including the
trivial `/health` coroutine.

Volume confirms this is a hot path: the server log contains **7,012
`POST /v1/messages/count_tokens`** requests against 8,544 `POST /v1/messages`.
Claude Code calls `count_tokens` before essentially every message.

Measured encoder cost: 60 KB of text → 12.4 ms of pure `encode()` time. A
multi-megabyte conversation therefore costs hundreds of ms to seconds per call.

**This is not fixed upstream.** Upstream `main` (6.16.6) still has the same
inline call, only with an extra `resolved=` argument.

### 2a. Proof — captured blocking stacks

A watchdog thread sampled `sys._current_frames()` for the loop thread whenever
its heartbeat stopped (py-spy's job; `py-spy` itself needs root on macOS).
**267 captures** on the unpatched instance, **260 of them showing the same
stack**:

```
routing.py:352  run_endpoint_function
routes.py:175   count_tokens          <- the async route
token_count.py:49 count               <- SYNC handler, called inline
tokens.py:48    get_token_count
token_estimation.py:75 estimate_text_tokens
core.py:127     encode                <- tiktoken C encode, ON THE EVENT LOOP
```

After the patch: **3 captures, 0 of them showing `encode` on the loop.**

### 2b. Ruled out

* **Garbage collection** — `gc.get_stats()` gen2 collections stayed at **0**
  for the whole measurement window on both runs. GC is not involved.
* **Config-lock contention** — `ManagedConfigStore._storage_lock()` uses
  `InterprocessFileLock` with a blocking `time.sleep()` poll, but its 10 s wait
  is already bounded and it is not on the per-request path
  (`current_settings()` just returns a cached attribute).
* **Provider catalogue publish** — `CodexModelCatalogPublisher.publish` is
  already offloaded via `run_sync_owned(...)`.
* **`/v1/messages`** — `MessagesHandler.create` is `async def` and awaited
  properly; `_token_counter` is never called in `messages.py`.
* **Sibling call sites** — `routes.py:175` is the **only** place in
  `api/routes.py`, `api/admin_routes.py`, or `api/code_sessions_routes.py`
  where a handler is invoked synchronously and returned from an async route.
  The fix is complete for this class.

## 3. Patch

`fcc-count-tokens-offload.patch` (34 lines, 3 hunks, one file). It offloads the
call through the boundary FCC already uses for its admin config path
(`core/async_tasks.run_sync_owned` → `anyio.to_thread.run_sync`), and preserves
cancellation semantics because `run_sync_owned` drains the worker rather than
abandoning it:

```python
return await run_sync_owned(
    partial(handler.count, request_data, request_id=get_request_id(request))
)
```

No API contract changes: same route, same request/response models, same status
codes, same headers.

## 4. Measurements

### 4a. Isolated A/B (identical invocation)

Isolated instance on a spare port, `HOME` redirected to a throwaway config dir
whose `.env` sets `MODEL=lmstudio/mock-model` with `LM_STUDIO_BASE_URL` pointed
at a local mock upstream — **no real keys visible, no provider contacted**.
Production version (6.2.57) code, patch applied by shadowing a writable copy via
`PYTHONPATH` (the installed package was never modified).

Payload: 5.83 MiB, 300 messages, 15 tools. Invocation: 30 × `GET /health`,
4 × `count_tokens`, concurrency 2.

| `/health` under load | before | after |
|---|---|---|
| outcomes | 28 ok / **2 timeout** | **30 ok / 0 timeout** |
| timeout rate | 6.7 % | **0.0 %** |
| p50 | 13.6 ms | 11.7 ms |
| p95 | **941.9 ms** | **86.5 ms** |
| p99 | **1854.7 ms** | **115.3 ms** |
| max | 1854.7 ms | 115.3 ms |

Idle baseline for reference: 100 % ok, p50 4.9 ms, p99 18.2 ms.

A larger run (60 probes, 8 requests, concurrency 4) reproduced the production
signature on unpatched code: 35.6 % timeouts, p95 371 ms, p99 1950 ms, and a
single `count_tokens` call taking **4015 ms**.

### 4b. Event-loop lag

| | before | after |
|---|---|---|
| worst lag observed | **6,450 ms** | **540 ms** |
| samples with lag > 200 ms | 7 | 3 |
| frame captures | 267 | 3 |
| captures showing `encode` on the loop | **260** | **0** |
| gen2 GC collections | 0 | 0 |

(Worst-case lag is the comparable figure; the two logs cover different wall-clock
windows, so their percentiles are not directly comparable.)

## 5. Regression test

`test_count_tokens_offload.py` pins the invariant directly: mount the real
router, substitute a recording handler, and assert the token counter is invoked
on a **worker** thread, never on the event-loop thread. Runs under pytest or
standalone.

```
RED   (unpatched 6.2.57): FAIL: token counting ran ON the event-loop thread
GREEN (patched):          PASS: token counting ran on 'AnyIO worker thread',
                                not the event-loop thread ('MainThread')
```

### 5a. Upstream suite results

The equivalent patch was applied to an upstream `main` checkout (6.16.6,
commit `261ecf7`) and upstream's own tests were run.

| scope | result |
|---|---|
| unpatched baseline (5 API modules) | 98 passed |
| patched (same 5 modules) | **98 passed** |
| patched, full `tests/api/` | **2,188 passed, 1 failed** |

The single failure,
`test_runtime_safe_logging.py::test_messaging_start_failure_default_logs_exclude_traceback`,
is an artifact of a deliberately partial dependency install in the test venv
(`python-telegram-bot` / `discord.py` absent, so the module raises
`ModuleNotFoundError` instead of the expected `RuntimeError`). Verified by
re-running it on **unpatched** code: it fails identically. **No regressions from
the patch.**

Two patch files are provided:

* `fcc-count-tokens-offload.patch` — against the installed 6.2.57 layout
  (what production runs).
* `fcc-count-tokens-offload-6.16.6.patch` — against upstream `main`; verified to
  apply cleanly with `git apply --check`.

## 6. Rollback

Nothing was changed in place, so there is nothing to roll back. To apply the
patch: `git apply fcc-count-tokens-offload.patch` in an FCC source checkout, or
copy the three hunks into the installed `api/routes.py`. To revert: restore
`api/routes.py` from the package (`uv tool install --force` from the pinned ref).

## 7. Safety attestation

* Production FCC not modified, not restarted, not reconfigured.
  PID `99117`, started `Thu Oct 15 00:53:33 2026`; installed
  `api/routes.py` mtime `Sep 24 00:20:03` (unchanged).
* No model request was issued against any provider. All generation traffic in
  the isolated instance went to the local mock upstream on `127.0.0.1:8181`;
  the isolated `.env` contains zero API keys.
* No paid provider contacted. Zero-token audit log: 446 entries, all
  `"cost_nzd": 0`.
* Hermes routing and the FCC fallback chain were not touched.
* Test processes stopped; ports 8181/8182 released.

## 8. Residual risk / next steps

1. **Production is still on the defective build.** It needs a restart to clear
   the current degraded state, and a patched build to stay healthy — both
   require owner approval.
2. **Upstream has not fixed this.** Worth reporting to
   `Alishahryar1/free-claude-code`; the one-line offload is directly applicable
   to 6.16.6 at `api/routes.py:257`.
3. The same pattern should be audited in any future route that calls a
   synchronous handler from an `async def`; `routes.py:175` is currently the only
   instance, but nothing prevents a regression. The regression test guards it.
4. Unrelated observation: `~/.fcc/fcc-server.pid` is stale (contains `55403`,
   dead) while the live process is `99117`; the pid file cannot be used for
   liveness checks. The isolated instance reproduced the same
   "8 leaked semaphore objects" shutdown warning, so that is a generic FCC
   shutdown artifact, not specific to the hang.
