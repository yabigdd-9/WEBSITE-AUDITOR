# SearXNG Service — Upgrade & Host-Setup Plan (for FABLE to execute)

Date: 2026-09-22 · Owner: Dion · Executor: FABLE
Constraint line: **$0, local-first, macOS + optional Docker, no new system software unless unavoidable, no new paid services, no new install for the default path.**
Companion docs: `docs/research/DEEP_UPGRADE_PLAN.md`, `docs/research/UPGRADE_RESEARCH_2026.md`, `docs/LOCAL_TOOLKIT.md`, `README.md`.

**Status being fixed.** Today the SearXNG lane is *validated but dead-ended*: the 12 discovery tests pass, but no loopback service exists, so `./mm discover-search` can only fail with a raw connection error. This plan makes the lane **useful with zero installs**, and then makes the optional service a **one-command, reversible, host-level** addition.

---

## 0. Verified ground truth (evidence, captured 2026-09-22)

Every claim below was checked on this host before writing the plan. Re-run the commands to confirm before starting.

| # | Claim | Command | Observed | Consequence for the plan |
|---|---|---|---|---|
| G1 | Existing discovery suite is green | `cd ~/WEBSITE-AUDITOR/money-machine && python3 -m pytest test_discovery.py -q` | `12 passed in 1.06s` | These 12 tests are a **frozen contract**. Refactors must not edit them. |
| G2 | No service is listening on 8888 | `lsof -nP -iTCP:8888 -sTCP:LISTEN` | no output | Fresh install path; no conflict handling needed for the default port. |
| G3 | The lane currently fails opaquely | `curl -s -o /dev/null -w '%{http_code}\n' -m 3 'http://127.0.0.1:8888/search?q=test&format=json'` | `http=000`, exit `7` (connection refused) | P0 must convert this into a typed, actionable `BLOCKED_*` state instead of a stack trace. |
| G4 | Docker is not usable for free | `docker ps -a` | `failed to connect to the docker API … no such file or directory` | Docker is **Tier 2 only** (opt-in). `reports/polish-status.json` already records `docker_health: MISSING_OPTIONAL`. |
| G5 | A SearXNG-supported interpreter already exists | `ls -l ~/.local/bin/python3.11` · `cat ~/WEBSITE-AUDITOR/.venv-email/pyvenv.cfg` | symlink → `~/.local/share/uv/python/cpython-3.11.16-macos-x86_64-none/bin/python3.11` | A SearXNG venv needs **no new system software**. `uv --version` → `0.12.17` is already installed. |
| G6 | Do **not** build SearXNG on the default `python3` | `python3 -V` · upstream `setup.py` | host `3.14.7`; upstream `python_requires=">=3.10"`, classifiers only 3.10–3.13 | Pin the service venv to **3.11** (G5). 3.14 is unsupported by upstream today. |
| G7 | JSON API is off by default upstream | upstream `searx/settings.yml` lines 84–85 | `# formats: [html, csv, json, rss]` then `formats:` `- html` | The service install **must** add `json` to `search.formats`, or the lane can never work. |
| G8 | Redis/uwsgi are not required for a private instance | same file, lines 90/91/97/100/105 | `port: 8888`, `bind_address: "127.0.0.1"`, `limiter: false`, `public_instance: false`, `secret_key: "ultrasecretkey"` (overridden by `${SEARXNG_SECRET}`) | No Redis, no uwsgi, no nginx. One env var + one settings file is the whole config. |
| G9 | `pip install searxng` is a trap | `curl -s https://pypi.org/pypi/searxng/json \| jq .info.summary` | `"MCP server providing SearXNG-based web search functionality"` (author D. Danchev, v0.1.2) | That package is a third-party MCP wrapper, **not** the engine. Install from `github.com/searxng/searxng`. |
| G10 | Compose is doc-only | `cat docs/research/docker-stack.yaml` · `ls compose*` | declares `searxng/searxng:latest`; no compose file in the repo | No drift risk; nothing to undo if Tier 2 is skipped. |
| G11 | Discovery wiring is exactly one call site | `rg -n discover-search money-machine/mm_operator.py` | `mm_operator.py:277–288` → `mm_discovery.searxng_candidates(...)` → `mm_discovery.ingest(..., dry_run=...)` | One integration point; low blast radius. |
| G12 | Health/metrics surfaces already exist | `rg -n mm_metrics money-machine/mm_pipeline.py` | `mm_metrics(name,value,updated_at)` created in `mm_pipeline.DDL`; read by `mm_observability.metrics()` | Provider metrics can be recorded without any new table or dependency. |

**Safety invariants that must survive every phase** (enforced by code, not convention):
loopback-only endpoints (`mm_discovery._loopback_endpoint`), no credentials in URLs, no email/contact data in discovery output, `DISCOVERED`-only state changes, `external_sends: 0`, `models_enabled: false` / `model_calls: 0`, `contact_eligibility: "UNASSESSED"`.

---

## 1. Design: two layers, decoupled

The single most important change is **decoupling "search" from "SearXNG"**. SearXNG becomes one interchangeable provider behind a stdlib-only in-repo layer, so every workpath improves even when the service is absent (G3), and the service becomes an accelerator rather than a prerequisite.

```
Layer B (optional, host-level, reversible)
  launchd user agent  ai.website-auditor.searxng
        └─ ~/.local/share/searxng/.venv (Python 3.11, from G5)   ← no new system software
             └─ python -m searx.webapp   →  http://127.0.0.1:8888   (bind loopback, G8)
                  settings: search.formats += json (G7), SEARXNG_SECRET env (G8)

Layer A (always on, in-repo, zero install, stdlib only)
  money-machine/mm_search_backend.py
        ├─ probe(endpoint)      → typed status, no exceptions for expected states
        ├─ search(...)          → bounded, size-capped, cached, circuit-broken
        ├─ cache (state/search-cache/, TTL + --replay)     ← offline determinism
        └─ breaker (state/search-breaker.json)             ← per-source isolation
              ▲                                    ▲
              │                                    │
   mm_discovery.searxng_candidates()      discover-import / CSV / JSON / NZBN / OSM
   (legacy path preserved, G1)            (already exists — the no-install fallback)
```

**Non-negotiable design rules**
1. Stdlib only in Layer A (`urllib`, `json`, `hashlib`, `time`, `pathlib`, `sqlite3`). No `requests`, no `httpx`, no new deps → satisfies "no extra software".
2. `mm_discovery.searxng_candidates()` keeps its signature, its `urlopen` usage, and therefore all 12 existing tests (G1). New capability lands in **new** functions.
3. Nothing in Layer A can reach a non-loopback host. Provider endpoints stay validated by `_loopback_endpoint`.
4. Layer B lives **outside the git repo** (`~/.local/share/searxng`) so the MIT repo never contains AGPL code or a 200 MB venv. Only the wrapper script + plist generator live in-repo.
5. Every failure is a named state (`BLOCKED_SEARCH_*`), never a traceback, and never a silent pass.

---

## 2. Workpath-by-workpath improvement matrix

"Workpath" = a lane the operator actually runs. Nothing here may regress an existing lane.

| Workpath | Today | After this plan | Proof artifact |
|---|---|---|---|
| **Discovery (search)** | One query, one endpoint, opaque crash when absent (G3) | Multi-query fan-out, typed states, cache, ranking, provenance | `mm discover-search --queries q.txt` JSON + `test_search_backend.py` |
| **Discovery (import)** | Works (CSV/JSON/NZBN/OSM) | Unchanged behaviour, now the documented **first-class fallback** when search is absent | `test_discovery.py` still 12/12 |
| **Identity resolution** | Host from `root_url()` | Adds `engines`, `rank`, `hit_count`, `fetched_at` provenance → resolves which host is canonical when two queries disagree | `discovery_provenance` in `pipeline_items.payload` |
| **Qualification** | Region string only | Region + repeated-query frequency + sector keyword match become deterministic inputs | `mm_lead_qualifier` input row |
| **Contact / verification** | Correctly contact-free | Still contact-free; adds *hints only* via optional `site:`-scoped intel queries, no addresses stored | `all("email" not in row)` assertion |
| **Audit** | Queue fed by any DISCOVERED item | Higher-quality hosts reach audit (deduped, canonical) → fewer wasted audits | `mm pipeline-health` counts |
| **Observability** | `state/*.jsonl`, `mm_metrics` (G12) | Adds `search_queries`, `search_results`, `search_cache_hits`, `search_failures`, `searxng_up` | `./mm metrics` |
| **Reliability / supervisor** | Supervisor + DLQ + retries | Search outages become DLQ-able retryable failures with per-source breaker; no lane-wide stall | `./mm dead-letter`, `test_supervisor.py` |
| **Doctor / setup** | `docker: PRESENT_NOT_EXECUTED`, service state invisible | `./mm doctor` reports a `search` block with provider truth, non-fatal | `./mm doctor \| jq .search` |
| **Service ops** | "would require host-level configuration" | `scripts/searxng.sh install\|status\|verify\|logs\|stop\|uninstall` + launchd (reuses `supervisor/launchd.py` patterns) | `./mm searxng verify` |
| **CI / validation** | 12 discovery tests + CI list (`.github/workflows/ci.yml:70`) | Adds offline replay tests → discovery covered with **no network** in CI | CI green, no new deps |
| **Docs / runbook** | README shows a command that cannot work yet (G3) | README gets a 3-line preflight + exact service setup + rollback | `README.md` §Discovery |

**Explicit non-goals** (do not do these): no remote/public SearXNG instance, no API keys, no Docker in the default path, no vendoring SearXNG, no new Python package in `requirements*.txt`, no changes to transport/approval gates, no email discovery or storage, no model calls.

---

## 3. Phase P0 — Zero-install core (do this first, ship on its own)

Goal: the discovery lane becomes **useful, typed, and testable with no service installed**. If everything after P0 is skipped, this phase alone is a real upgrade.

### T0.1 `.gitignore` — keep runtime state out of git
`state/` is partly tracked (`state/HERMES_EXECUTION_STATE.yaml`, `state/deployments.jsonl`), and `state/search-cache` is **not** currently ignored. Append:

```gitignore
# Discovery search runtime state (regenerated, never committed)
state/search-cache/
state/search-breaker.json
```

### T0.2 New module `money-machine/mm_search_backend.py`

Stdlib only. Every provider outcome is a **named state**; expected failures never raise.

```python
#!/usr/bin/env python3
"""Stdlib-only search provider layer for discovery.

SearXNG's loopback JSON API is one provider behind this layer. A missing
service is an expected, named state -- never a traceback. Results are cached
so discovery can be replayed offline and CI needs no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import mm_core as core

MAX_RESPONSE = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 20
USER_AGENT = "WEBSITE-AUDITOR-Discovery/1.0"

OK = "OK"
BLOCKED_ENDPOINT_INVALID = "BLOCKED_ENDPOINT_INVALID"
BLOCKED_NOT_LOOPBACK = "BLOCKED_NOT_LOOPBACK"
BLOCKED_NOT_LISTENING = "BLOCKED_NOT_LISTENING"
BLOCKED_TIMEOUT = "BLOCKED_TIMEOUT"
BLOCKED_HTTP_STATUS = "BLOCKED_HTTP_STATUS"
BLOCKED_NOT_JSON = "BLOCKED_NOT_JSON"          # HTML => json format not enabled upstream
BLOCKED_TOO_LARGE = "BLOCKED_TOO_LARGE"
BLOCKED_INVALID_JSON = "BLOCKED_INVALID_JSON"
BLOCKED_CIRCUIT_OPEN = "BLOCKED_CIRCUIT_OPEN"

REMEDY = {
    BLOCKED_NOT_LISTENING: "Start the local service: ./mm searxng status (see docs/SEARXNG_SERVICE_PLAN.md section 6).",
    BLOCKED_NOT_JSON: "Enable the JSON API: search.formats must include 'json' in the service settings.yml.",
    BLOCKED_NOT_LOOPBACK: "Discovery only accepts http loopback endpoints (127.0.0.1/localhost/::1).",
    BLOCKED_CIRCUIT_OPEN: "Provider breaker is open after repeated failures; retry after the cooldown.",
}


def _endpoint(endpoint):
    """Hard-validate an endpoint. Config errors raise; runtime states do not."""
    parsed = urlsplit(str(endpoint or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("SearXNG endpoint must be loopback HTTP")
    if parsed.username or parsed.password:
        raise ValueError("SearXNG endpoint credentials are not allowed in URL")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid SearXNG port")
    return parsed.geturl().rstrip("/"), (parsed.port or 80)


def _request(endpoint, params, timeout):
    """One GET. Returns (state, payload_or_reason). Never raises for runtime faults."""
    url = endpoint + "/search?" + urlencode(params)
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE + 1)
    except HTTPError as exc:
        return BLOCKED_HTTP_STATUS, "HTTP " + str(exc.code)
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ConnectionRefusedError):
            return BLOCKED_NOT_LISTENING, "connection refused"
        if isinstance(reason, TimeoutError):
            return BLOCKED_TIMEOUT, "timeout"
        return BLOCKED_NOT_LISTENING, type(reason).__name__ + ": " + str(reason)
    except TimeoutError:
        return BLOCKED_TIMEOUT, "timeout"
    if len(body) > MAX_RESPONSE:
        return BLOCKED_TOO_LARGE, "response size limit"
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return BLOCKED_NOT_JSON, "response was not JSON"
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        return BLOCKED_INVALID_JSON, "missing results[]"
    return OK, document
```

### T0.2b Provider API: `probe()`, cache, breaker, `search()`

Append to the same module. `probe()` is read-only and safe to call from `doctor`/metrics.

```python
def probe(endpoint="http://127.0.0.1:8888", timeout=5):
    """Read-only liveness + capability check. Never raises for runtime faults."""
    endpoint, port = _endpoint(endpoint)
    state, payload = _request(
        endpoint,
        {"q": "localhost", "format": "json", "categories": "general", "safesearch": "1"},
        timeout,
    )
    result = {
        "provider": "searxng",
        "endpoint": endpoint,
        "port": port,
        "state": state,
        "ok": state == OK,
        "json_api_enabled": state != BLOCKED_NOT_JSON,
        "checked_at": core.now(),
        "scope": "Reachability and JSON capability only; not a result-quality claim.",
    }
    if state == OK:
        result["result_count"] = len(payload["results"])
    else:
        result["reason"] = payload
        result["remedy"] = REMEDY.get(state, "Inspect the service log: ./mm searxng logs")
    return result


def _cache_dir():
    directory = Path(core.root()) / "state" / "search-cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cache_key(endpoint, query, region, params):
    raw = json.dumps([endpoint, query, region, params], sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def cache_read(key, ttl_hours):
    path = _cache_dir() / (key + ".json")
    if not path.is_file() or ttl_hours <= 0:
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(document.get("cached_at", 0)) > ttl_hours * 3600:
        return None
    return document.get("payload")


def cache_write(key, payload):
    path = _cache_dir() / (key + ".json")
    path.write_text(json.dumps({"cached_at": time.time(), "payload": payload}),
                    encoding="utf-8")
    return path
```

`search(query, region, endpoint, limit, timeout, cache_hours, use_network=True)` composes breaker → cache → `_request` and returns:

```python
{"state": OK, "results": [...], "query_ref": "<sha256[:12]>", "endpoint": ..., "cache": "hit|miss|bypass"}
```

TTL defaults to `int(os.environ.get("MM_SEARCH_CACHE_HOURS", "24"))` and `0` disables caching — matching the project's existing env-var style (`MM_MIN_FREE_MB`, `MM_NETWORK_PROBE_HOST`). Breaker state lives in `state/search-breaker.json`: open after `MM_SEARCH_BREAKER_FAILS` (default 3) consecutive failures, half-open after `MM_SEARCH_BREAKER_COOLDOWN` seconds (default 300) — the same shape as the documented per-source breakers in `DEEP_UPGRADE_PLAN.md` §9.

### T0.3 CLI surface (backward compatible)

Register next to the existing `discover-*` parsers (`mm_operator.py:182`), dispatch near line 277:

```python
q=s.add_parser('searxng');q.add_argument('action',choices=['status','probe','verify','install-plan'])
```

- `./mm searxng status` → `probe()` + whether the lane is usable + remedy.
- `./mm searxng verify` → exit **0** when `OK`; exit **2** with `BLOCKED_*` + remedy otherwise (usable as a gate; matches the project's `BLOCKED: …; exit 2` convention in `mm_operator.main`).
- `./mm searxng install-plan` → prints the exact host commands from §6 (prints only, never executes).

Extend `discover-search` while keeping every existing flag working:

```python
q=s.add_parser('discover-search')
q.add_argument('--query')                       # was required=True; now optional
q.add_argument('--queries')                     # file: one query per line, '#' comments
q.add_argument('--region',required=True)
q.add_argument('--endpoint',default='http://127.0.0.1:8888')
q.add_argument('--limit',type=int,default=20)
q.add_argument('--cache-hours',type=int,default=int(os.environ.get('MM_SEARCH_CACHE_HOURS','24')))
q.add_argument('--no-cache',action='store_true')
q.add_argument('--dry-run',action='store_true')
```

Handler rule: exactly one of `--query`/`--queries` required, else `BLOCKED: provide --query or --queries`, exit 2. Endpoint resolution is a single source: `--endpoint` > `MM_SEARXNG_ENDPOINT` > `http://127.0.0.1:8888` (adopted from the sibling plan's W9). On a non-`OK` provider state: print state + remedy + fallback hint and exit 2 — **never** ingest an empty list as success.

### T0.4 Graceful-degradation contract (the important part)

| Provider state | Operator sees | Pipeline effect | Exit |
|---|---|---|---|
| `OK` | counts + states | `DISCOVERED` items ingested | 0 |
| `BLOCKED_NOT_LISTENING` / `TIMEOUT` | state, endpoint, remedy, fallback hint | nothing ingested, **no** false success | 2 |
| `BLOCKED_NOT_JSON` | "JSON API disabled" + exact settings key (G7) | nothing ingested | 2 |
| `BLOCKED_TOO_LARGE` / `INVALID_JSON` | state + reason | nothing ingested | 2 |
| `BLOCKED_CIRCUIT_OPEN` | retry-after | deferred; import lanes unaffected | 2 |

`./mm discover-import` remains the documented fallback and never touches the network.

### T0.5 Tests — `money-machine/test_search_backend.py` (new; stdlib + pytest)

Mirror the style of `test_discovery.py` (pure functions, monkeypatched `urlopen`, no network, no on-disk fixtures):

- `test_loopback_invariant_is_enforced` — `https://127.0.0.1:8888` and `http://example.com:8888` raise `ValueError`.
- `test_credentials_in_endpoint_are_rejected`.
- `test_probe_reports_not_listening_as_typed_state` — `urlopen` raises `URLError(ConnectionRefusedError())` → `BLOCKED_NOT_LISTENING`, no exception escapes.
- `test_probe_reports_html_response_as_json_disabled` — body `b"<html>"` → `BLOCKED_NOT_JSON`, `json_api_enabled is False`.
- `test_probe_rejects_oversized_response` — body > 2 MiB → `BLOCKED_TOO_LARGE`.
- `test_probe_rejects_invalid_json_document` — `{"nope": 1}` → `BLOCKED_INVALID_JSON`.
- `test_ok_probe_counts_results`.
- `test_cache_hit_avoids_second_request` — two calls at TTL 24 h → `urlopen` called once.
- `test_cache_expiry_forces_refetch` — pre-write cache with `cached_at` 25 h old → refetch.
- `test_replay_uses_cache_without_network` — `urlopen` raises → cached results still returned.
- `test_breaker_opens_after_repeated_failures_and_recovers_after_cooldown`.
- `test_no_contact_fields_in_provider_output` — no `email`/`recipient` keys anywhere in output.

**Frozen constraint:** `test_discovery.py` stays at 12/12 (G1) and is **not edited** in this phase.

### T0.6 Doctor integration (`mm_operator.doctor`, line 137)

Add a `search` block with probe timeout ≤ 5 s, wrapped in `try/except Exception`, using the existing status vocabulary:

```python
"search": {
    "providers": {"searxng": mm_search_backend.probe()},
    "lane_usable": <bool>,
    "limitation": "Presence or reachability does not prove result quality.",
}
```

`doctor` must stay green when the service is absent — `reports/polish-status.json` already models this with `docker_health: MISSING_OPTIONAL`; use the same "optional, non-fatal" framing.

### T0.7 Metrics

Record `search_queries`, `search_results`, `search_cache_hits`, `search_failures`, `searxng_up` in the existing `mm_metrics` table (G12), inside an `if "mm_metrics" in tables` guard so read-only/absent DBs still work. Visible via `./mm metrics` and `./mm observability-snapshot`.

### P0 acceptance criteria — exact commands

```bash
cd ~/WEBSITE-AUDITOR/money-machine
python3 -m pytest test_discovery.py test_search_backend.py -q    # 12 + new, no network
cd ~/WEBSITE-AUDITOR
./mm searxng status | jq -r '.state, .remedy'                     # BLOCKED_NOT_LISTENING + remedy
./mm searxng verify; echo "exit=$?"                               # exit=2, actionable, no traceback
./mm doctor | jq '.search.providers.searxng.state'                # typed state, non-fatal
./mm discover-search --query "plumber christchurch" --region Canterbury; echo "exit=$?"   # exit=2, nothing ingested
./mm discover-import --file sample_prospects.csv --region Canterbury --source nzbn        # unchanged, still works
python3 -m pytest money-machine/test_supervisor.py -q             # other lanes unaffected
```

---

## 4. Phase P1 — Discovery intelligence (still zero install)

Goal: make results *better*, not just safer. All changes are additive to `searxng_candidates`/`ingest`; the frozen tests still pass.

| Task | Change | Why it's better |
|---|---|---|
| T1.1 Multi-query fan-out | `discover-search --queries q.txt`: sequential (polite; no concurrency by default), per-query limit, global cap `MAX_SEARCH_RESULTS` (50) respected | One command covers a trade × suburb grid instead of N invocations |
| T1.2 Cross-query dedupe + ranking | Count how many queries returned each host; rank by `hit_count` desc, then SearXNG's per-result `score`, then host | Repeated hits = stronger lead signal; deterministic tie-break keeps runs reproducible |
| T1.3 Provenance enrichment | Extend the payload written by `mm_discovery.ingest()` with `engines`, `rank`, `hit_count`, `fetched_at`, `query_ref` (hash only — no raw query text) | Identity + qualification get real inputs; still no PII |
| T1.4 Region/sector shaping | Query template `"{trade} {suburb} {region}"` from a small JSON list in `money-machine/config/` | NZ-relevant queries instead of hand-typed strings |
| T1.5 Polite client behaviour | `MM_SEARCH_DELAY_MS` (default 1000) between queries, UA already identifies the tool, `--limit` capped, no unbounded paging | Avoids engine throttling/bans — the top real risk of any metasearch lane |
| T1.6 Replay mode | `--replay` reads only from `state/search-cache/`; with T0.5 this gives deterministic offline CI | CI and the 24 h soak stop depending on the network |
| T1.7 Optional `site:` intel lane | Opt-in `--intel-domain example.co.nz` producing *candidate hints* only; **no** address extraction or storage at this stage | Prepares the contact workpath without violating contact-free discovery |
| T1.8 Sector scoring handoff | Emit `sector_match: 0..1` from region/sector token overlap with title+content | Feeds `mm_lead_qualifier` deterministically |

**Ranking rule (deterministic; document it in the module docstring):** `key = (-hit_count, -score, host)`. No randomness, no model, stable across runs.

**Tests to add (P1):** multi-query dedupe yields one row per host with correct `hit_count`; ranking stable under shuffled input order; `--replay` performs zero network calls; delay honoured (`time.sleep` monkeypatched); global cap never exceeded; `ingest()` payload contains the new provenance keys while `contact_eligibility` stays `"UNASSESSED"`.

**P1 acceptance**

```bash
printf 'plumber christchurch\nplumber riccarton\nroofer canterbury\n' > /tmp/q.txt
./mm discover-search --queries /tmp/q.txt --region Canterbury --dry-run | jq '.counts'
./mm discover-search --queries /tmp/q.txt --region Canterbury --replay --dry-run | jq '.counts'
cd money-machine && python3 -m pytest test_discovery.py test_search_backend.py -q
```

---

## 5. Phase P2 — Host-level service (optional accelerator, reversible)

Only after P0 + P1 are green. This is the part previously described as "would require host-level configuration" — it does, but it is **one script and one plist**, with no sudo, no Redis, no uwsgi, no Docker, and no new system software (G5, G8).

### 5.1 Files (in-repo, small)

| File | Purpose |
|---|---|
| `money-machine/scripts/searxng.sh` | Idempotent host ops: `install`, `status`, `verify`, `logs`, `stop`, `uninstall` (mirrors `scripts/system_doctor.sh`: `set -eu`, small, no hidden state) |
| `money-machine/supervisor/searxng_launchd.py` | Plist generator + `install/status/uninstall`, structurally mirroring `supervisor/launchd.py` (same `plistlib`, same `launchctl bootout`/`bootstrap gui/<uid>` pattern, same `status()` shape) |
| `docs/SEARXNG_SERVICE_PLAN.md` (this file) | Runbook + rollback |

Everything else lives **outside the repo**: `~/searxng-src` (checkout), `~/.local/share/searxng/.venv` (Python 3.11 venv), `~/.searxng/settings.yml` (chmod 600). Keeping the checkout out of the repo preserves the MIT/AGPL boundary and keeps `git status` clean.

### 5.2 The setup, step by step (what `./mm searxng install-plan` prints)

```sh
# 0. Preconditions (both already verified true on this host)
python3.11 -V                      # 3.11.16 via ~/.local/bin/python3.11      (G5)
lsof -nP -iTCP:8888 -sTCP:LISTEN   # expected: empty                          (G2)

# 1. Source checkout (free; do NOT pip install "searxng" from PyPI -- G9)
git clone --depth 1 https://github.com/searxng/searxng.git ~/searxng-src

# 2. Dedicated venv on the SUPPORTED interpreter (never .venv-email, never python3.14 -- G6)
uv venv --python 3.11 ~/.local/share/searxng/.venv
~/.local/share/searxng/.venv/bin/python -m pip install -r ~/searxng-src/requirements.txt

# 3. Config: loopback + JSON API + private-instance defaults   (G7, G8)
mkdir -p ~/.searxng && chmod 700 ~/.searxng
umask 077
{ printf 'use_default_settings: true\nserver:\n  secret_key: "%s"\n  limiter: false\n  public_instance: false\n  bind_address: "127.0.0.1"\n  port: 8888\nsearch:\n  formats:\n    - html\n    - json\n  safe_search: 1\ngeneral:\n  debug: false\n  enable_metrics: false\n' \
    "$(openssl rand -hex 16)"; } > ~/.searxng/settings.yml
chmod 600 ~/.searxng/settings.yml

# 4. Smoke test in the FOREGROUND before installing anything persistent
SEARXNG_SETTINGS_PATH=~/.searxng/settings.yml \
  ~/.local/share/searxng/.venv/bin/python -m searx.webapp &
sleep 6
curl -fsS 'http://127.0.0.1:8888/search?q=nz&format=json' | jq '.results | length'
# Ctrl-C the foreground server once that returns a number.
```

Failure decoding: HTML instead of JSON → `search.formats` is wrong (G7). Bind error → port 8888 occupied, change it in `settings.yml` **and** pass `--endpoint http://127.0.0.1:<port>`. `ImportError` on `3.14` → you used the wrong interpreter (G6).

`use_default_settings: true` is deliberate: it inherits upstream's engine list so the instance aggregates many engines for free, while our block overrides only the keys that matter for safety and the JSON API.

### 5.3 Make it durable with launchd (already on macOS — no new software)

```sh
cd ~/WEBSITE-AUDITOR/money-machine
python3 supervisor/searxng_launchd.py install     # writes ~/Library/LaunchAgents/ai.website-auditor.searxng.plist + bootstraps gui/$UID
python3 supervisor/searxng_launchd.py status
```

Plist requirements (copy the shape of `supervisor/launchd.py`: `RunAtLoad`, `KeepAlive`, `ThrottleInterval: 10`, `ProcessType: Background`, `StandardOutPath`/`StandardErrorPath` under `state/`):

```python
LABEL = "ai.website-auditor.searxng"
PROGRAM = ["<home>/.local/share/searxng/.venv/bin/python", "-m", "searx.webapp"]
ENVIRONMENT = {
    "SEARXNG_SETTINGS_PATH": "<home>/.searxng/settings.yml",
    "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
}
```

Deliberate asymmetry vs the supervisor plist: the supervisor sets `MM_EXTERNAL_SEND_DISABLED=1`; the SearXNG plist gets **no** application environment and no `MM_ROOT`. The service is a read-only search proxy on loopback and must have no path into the money-machine database.

### 5.4 Verification (all must hold before declaring success)

```sh
./mm searxng verify                                     # exit 0, state OK
lsof -nP -iTCP:8888 -sTCP:LISTEN                        # 127.0.0.1:8888 ONLY (never *:8888)
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8888/search?q=x&format=json'   # 200
./mm discover-search --query "plumber christchurch" --region Canterbury --dry-run --limit 5 | jq '.counts'
python3 supervisor/searxng_launchd.py status             # loaded: true
kill -9 "$(lsof -t -iTCP:8888 -sTCP:LISTEN)"; sleep 12; ./mm searxng verify   # auto-restart proof
```

`verify` must also assert the **loopback-only** property: parse the `lsof` output and fail if any entry binds `*:8888`, `0.0.0.0:8888`, or `[::]:8888`. That is the single most important host-level safety check in this plan.

### 5.5 Tiers — pick the cheapest that works

| Tier | What it needs | When to choose it | Cost |
|---|---|---|---|
| **0 — none (default)** | nothing; P0 + P1 only; `discover-import` + cache/replay | You want value today and zero footprint | $0, no install |
| **1 — native venv + launchd (recommended)** | `uv` + Python 3.11, both already present (G5); git clone; pip deps into an isolated venv | You want live search on this Mac | $0, ~150 MB disk, outside the repo |
| **2 — Docker** | a running Docker daemon (currently down, G4) | Only if you already run Docker daily | $0 licence, ~120 MB image + daemon overhead |

Tier 2, if ever used, must reuse `docs/research/docker-stack.yaml`'s intent but publish the port bound to loopback (`127.0.0.1:8888:8080`) and mount a settings file with `json` enabled. Tier 2 is **not** part of the default path — do not make the plan depend on Docker (G4).

### 5.6 Rollback (everything is reversible)

```sh
python3 supervisor/searxng_launchd.py uninstall          # bootout + remove plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.website-auditor.searxng.plist 2>/dev/null || true
rm -rf ~/.local/share/searxng ~/searxng-src
rm -f  ~/.searxng/settings.yml && rmdir ~/.searxng 2>/dev/null || true
rm -rf ~/WEBSITE-AUDITOR/state/search-cache ~/WEBSITE-AUDITOR/state/search-breaker.json
```

After rollback: `./mm searxng status` → `BLOCKED_NOT_LISTENING` (typed, non-fatal) and every other lane behaves exactly as before. No repo file needs reverting because the service never lived in the repo.

---

## 6. Phase P3 — Reliability, observability, governance wiring

| Task | Change | Evidence |
|---|---|---|
| T3.1 Search failures are retryable, not fatal | Wrap `search()` in the pipeline's `RetryableError` path (`mm_pipeline`); provider outage → item stays queued and retries with backoff instead of failing the business | `mm_pipeline.RetryableError`, `mm_pipeline.finish` retry counters |
| T3.2 DLQ integration | After `max_attempts`, the failure lands in the observable DLQ with the provider state attached | `./mm dead-letter`, `state/dead-letter/` |
| T3.3 Per-source breaker | `BLOCKED_CIRCUIT_OPEN` short-circuits before any socket is opened; state file is human-readable JSON | `state/search-breaker.json` |
| T3.4 Supervisor heartbeat | Discovery/search work registers heartbeats like other workers, so a *stuck* search is visible as a stale lease, not silence | `state/worker-heartbeats/`, `test_supervisor.py` |
| T3.5 Disk/network guards honoured | Respect existing `disk_guard`/`network_guard` (`mm_runtime_guards.py`): pause new search work when disk is low; defer network work when TCP probe fails, while local/import work continues | `./mm health` → `guards` |
| T3.6 Launchd restart + soak proof | Kill-loop the service and prove recovery (`kill -9` twice); run a replay-based soak so the 24 h unattended soak requirement no longer needs live engines | `supervisor/searxng_launchd.py status`, `state/metrics.jsonl` |
| T3.7 Optional keyless Overpass lane (opt-in only) | Behind `MM_ALLOW_PUBLIC_SOURCE=1`, add a *second* provider (OSM Overpass API, keyless, free, JSON) using the same typed-state layer — **off by default**, never loopback-assumed, separate provenance `osm-overpass:<hash>` | New provider tests + `discover-search --provider overpass` |
| T3.8 Governance unchanged | No new approval path, no transport change, no sending, no model calls. Verify `./mm approval-check` and `external_sends: 0` remain as-is | acceptance run |

T3.7 is the only network-egress expansion in this plan and is therefore opt-in, documented, and reversible. It exists because it delivers real discovery volume for $0 with no install — the strongest "no extra software" win available after Tier 0.

---

## 7. Phase P4 — CI, docs, and evidence

| Task | Change |
|---|---|
| T4.1 CI | Add `money-machine/test_search_backend.py` to the test list in `.github/workflows/ci.yml` (currently lines ~66–76) and keep the `compileall` step green. No new pip dependency — the suite is stdlib + pytest, matching the existing pinned `money-machine/requirements-email.txt`. |
| T4.2 README | Replace the bare SearXNG example (`README.md` §Discovery, ~line 82) with: (a) a 3-line preflight `./mm searxng status`, (b) the import fallback as the zero-install default, (c) link to this plan's §5.2 for setup. Update the acceptance line (~183) so "local SearXNG when used" now points at an automated `./mm searxng verify`. |
| T4.3 Docs | Add the workpath matrix (§2) to `CURRENT_STATE.md` and mark the SearXNG item's new disposition in `docs/CHAT_ACTION_REGISTER.md` (the project's roadmap-disposition register). |
| T4.4 Evidence bundle | Append to `docs/TOOLKIT_VALIDATION.md` (or the next `CODEX_VERIFICATION_BUNDLE_*`) the raw outputs of §8's acceptance run, including the §5.4 loopback-only proof. |
| T4.5 Cost/no-cost statement | Record in the final summary: `paid_ai_cost: 0`, `pipeline_model_calls: 0`, `external_sends: 0`, new dependency count `0`, new system packages `0`. |

---

## 8. Blast radius — exact file inventory

| Path | Action | Phase |
|---|---|---|
| `money-machine/mm_search_backend.py` | **new** (~180 lines, stdlib only) | P0 |
| `money-machine/test_search_backend.py` | **new** (~12 tests) | P0 |
| `money-machine/mm_operator.py` | modify: `searxng` parser + dispatch; extend `discover-search` args + handler; add `search` block to `doctor()` | P0 |
| `money-machine/mm_discovery.py` | modify: additive `search_candidates()` + provenance enrichment in `ingest()`; **`searxng_candidates` untouched** | P1 |
| `money-machine/config/search-queries.json` | **new** small trade/suburb template list | P1 |
| `money-machine/scripts/searxng.sh` | **new** host ops wrapper | P2 |
| `money-machine/supervisor/searxng_launchd.py` | **new** plist generator | P2 |
| `.gitignore` | modify: 2 lines | P0 |
| `.github/workflows/ci.yml` | modify: 1 test path | P4 |
| `README.md`, `CURRENT_STATE.md`, `docs/CHAT_ACTION_REGISTER.md`, `docs/TOOLKIT_VALIDATION.md` | modify: documentation/evidence only | P4 |

**Do not touch:** `mm_pipeline.py` DDL/transitions, `mm_transport.py`, `mm_approval.py`, `mm_email*.py`, `mm_core.py` (except adding a metric helper if genuinely needed), `bookings`/`approval` gates, `test_discovery.py`, `requirements*.txt`, `pyproject.toml`.

## 9. Test matrix

**Must remain green (frozen, unchanged):**

```bash
cd ~/WEBSITE-AUDITOR/money-machine
python3 -m pytest test_discovery.py test_supervisor.py test_pipeline.py -q
```

**New (P0):** the 12 `test_search_backend.py` cases listed in T0.5.
**New (P1):** multi-query dedupe/`hit_count`, ranking stability under shuffle, replay = zero network, delay honoured, global cap, provenance keys present + still contact-free.
**New (P2/P3):** launchd `install/uninstall` idempotency (mirror `test_launchd.py`'s approach — plist generation asserted without requiring a live service), breaker open/close, DLQ landing, guards honoured.

Rule: any test that needs a live service must be marked `slow` (the project already has that marker registered in `pyproject.toml`) and must not be part of the default suite.

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Upstream engines throttle/ban a fresh instance | High | Lane quality drops | T1.5 delay + capped limits; breaker; cache/replay means reruns cost nothing |
| Someone builds SearXNG on Python 3.14 | Medium | Install failure/cryptic errors | G6 + explicit `uv venv --python 3.11` in the script and `install-plan` |
| Someone `pip install searxng` from PyPI (G9) | Medium | Wrong package (MCP wrapper) | Documented in §5.2 step 1 and in the script's help text |
| JSON API left disabled (G7) | High on first setup | Lane always `BLOCKED_NOT_JSON` | Typed state names the exact key; `verify` checks it |
| Service binds publicly | Low | Security exposure | `verify` fails on `*:8888`; `install-plan` bakes `bind_address: 127.0.0.1` |
| Secret handling | Low | Credential leak | `openssl rand -hex 16` into `~/.searxng/settings.yml`, `chmod 600`, repo `.gitignore` already ignores `*secret*` |
| AGPL contamination of an MIT repo | Low | Licensing confusion | Service stays outside the repo; no upstream code vendored or imported |
| Refactor breaks the 12 frozen tests | Medium if careless | Regression | `searxng_candidates` and its `urlopen` usage are explicitly out of scope; run them first on every commit |
| Vendored-venv/docker bloat | Low | Disk pressure | Tier 0 default; `disk_guard` respected; rollback removes all installed artifacts |
| Scope creep into contact/email discovery | Medium | Violates safety model | T1.7 is hints-only; T3.8 is a hard acceptance check |

---

## 11. Definition of done

**P0 done when** (all commands from §3 acceptance pass):
1. `test_discovery.py` = 12/12 unchanged, `test_search_backend.py` all pass, **no network**.
2. `./mm searxng verify` exits 2 with a named state + remedy (service absent) — never a traceback.
3. `./mm doctor` is green and reports a typed `search` block.
4. `./mm discover-import` behaviour is byte-for-byte unchanged.
5. `./mm metrics` shows the new search counters.

**P1 done when** multi-query + ranking + cache/replay are demonstrable, `--dry-run` produces a stable `hit_count`-ranked list, and the frozen tests still pass.
**P2 done when** §5.4 passes end to end *including* the loopback-only assertion and the `kill -9` auto-restart proof, and §5.6 rollback restores the previous state exactly.
**P3/P4 done when** search failures are visible in `./mm dead-letter`, the CI test list includes the new file, and the evidence bundle is appended.

Every phase must end with the same invariant check:

```bash
./mm health | jq '.pipeline, .guards'
./mm metrics | jq '.model_cost_usd'      # 0
./mm transport-status | jq '.external_sends'   # 0
```

---

## 12. FABLE execution protocol

1. **Order is binding:** P0 → (verify) → P1 → (verify) → P2 → (verify) → P3 → P4. Do not start P2 before P0/P1 acceptance is pasted as evidence — the whole point is that the lane is valuable *without* the service.
2. **Per step, attach raw evidence** (command + output) in the mission log; never claim a pass without the command output that shows it.
3. **Stop conditions — halt and report instead of improvising:**
   - any of the 12 frozen discovery tests fail;
   - `mm_pipeline` transition rules would need editing;
   - the service can only be made to work by installing Docker, Redis, uwsgi, or a system-wide Python;
   - any step would touch transport, approval, email, or sending code;
   - `verify` shows a non-loopback bind.
4. **Commit discipline:** one commit per task ID (`T0.2`, `T1.3`, …), message referencing the task, test output in the body. Never bundle the whole plan into one commit.
5. **Do not do:** edit `test_discovery.py`; add packages to `requirements*.txt`/`pyproject.toml`; vendor SearXNG into the repo; run the service as root/`sudo`; open the port beyond loopback; ingest results when the provider state is not `OK`; store raw query text or any contact data.
6. **Human gate:** steps 5.2/5.3 install host artifacts. `install-plan` prints them; a human (or FABLE with explicit approval) runs them. Everything up to and including P1 needs no host changes at all.

---

## 13. Coordination with the other plans already in this repo (read this before executing)

Two other plan documents exist and were produced in parallel with this one:

| Doc | Scope | Relationship to this plan |
|---|---|---|
| `docs/FABLE_SEARXNG_SERVICE_PLAN.md` ("SearXNG-Optional Discovery Fabric", W1–W18) | Same problem space, stricter rule: **never install or start a search service**, `no new software`, `no new egress` | Same goal, different service policy. Its workpath list and mine overlap ~80% — **do not execute both.** |
| `FABLE_EXECUTION_PLAN.md` | Broader free-only upgrade: DLQ triage, duplicate-row dedupe, acceptance evidence | Orthogonal; it *also* touches the SearXNG call site (`mm_operator.py:282`) in its ground-truth notes |

**Single source of truth (binding):**
1. For the **SearXNG/discovery lane**, FABLE executes **one** of the two SearXNG plans. Pick this doc if host enablement may ever be wanted; pick the sibling if the service must stay permanently uninstalled. Merge the loser's unique content in rather than running both.
2. **One writer per file.** `money-machine/mm_operator.py` and `money-machine/mm_discovery.py` are touched by both SearXNG plans *and* referenced by `FABLE_EXECUTION_PLAN.md`. Serialize: finish and commit the discovery lane before any other agent edits those two files, or the patches will collide.
3. **Adopt these ideas from the sibling plan** (they are improvements to this one):
   - endpoint resolution as a single source: `--endpoint` > `MM_SEARXNG_ENDPOINT` > `http://127.0.0.1:8888` (W9);
   - `state/search_service.json` as the read-only projection other workpaths consume (W4/W15);
   - an explicit zero-dependency guard test (`test_zero_new_dependencies.py`) asserting `git diff --stat requirements.txt pyproject.toml package.json money-machine/requirements-email.txt` stays empty (W6);
   - a degraded-path chaos test file (`test_discovery_degraded.py`) covering service-offline/misconfigured/timeout (W5);
   - no schema change: provenance stays additive inside `pipeline_items.payload` JSON (W12).

**Service policy — the one place the plans disagree, resolved:**
- **Automated execution (FABLE, unattended): P0 + P1 + P3 + P4 only. Install nothing, start nothing.** This satisfies the stricter plan and the user's "no extra software" preference.
- **P2 (host setup) is human-gated.** FABLE may *print* the plan (`./mm searxng install-plan`), may *prepare* the scripts and tests in-repo, and may run the verification checks — but must not clone, install, or load a launchd job without explicit human approval in the loop. Tier 0 (§5.5) is the default and needs no approval.
- If the sibling plan's "never, under any circumstance" rule is the operator's final answer, then **delete §5 and T3.6 from execution scope** and keep everything else — the plan remains fully coherent, because P0/P1 deliberately make the lane valuable with no service at all.

**Known in-progress condition:** `docs/FABLE_SEARXNG_SERVICE_PLAN.md` ends mid-file at a `<!-- PART-4 -->` marker, i.e. it was still being written. Verify it is complete and its task IDs do not collide with `T0.*`–`T4.*` here **before** starting work.

---

**One-line summary for the operator:** P0/P1 make discovery typed, ranked, cached, and useful with **zero installs**; P2 adds the real service in one reversible, human-gated step using software already on this Mac; P3/P4 make it observable, retry-safe, CI-covered, and documented — all at $0, with no new dependencies and no path to sending anything.



