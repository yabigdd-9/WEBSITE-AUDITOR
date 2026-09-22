"""P3 tests: multi-probe network guard, log dedupe, ensure-running continuity.

All fixtures are synthetic and disposable. No real network access: probes are
injected fakes or monkeypatched; no model calls; no sends.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mm_core as c
import mm_pipeline as p
import mm_runtime_guards as guards
from supervisor import cli as supervisor_cli


def fresh_db(tmp):
    path = Path(tmp) / "t.db"
    sqlite3.connect(path).close()  # mode=rw opens require an existing file
    d = c.connect(path)
    d.executescript("""
    CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY, name TEXT,
        public_website TEXT, region TEXT, source TEXT, discovered_at TEXT,
        current_status TEXT, is_dummy INTEGER DEFAULT 0);
    """)
    p.migrate(d)
    return d


class MultiProbeGuard(unittest.TestCase):
    def test_guard_multi_probe_fallback(self):
        """First probe fails, second succeeds -> guard reports ok via fallback."""
        def resolver(host, port, type=None):
            if host == "dead.example":
                raise OSError("name resolution failed")
            return [(2, 1, 6, "", ("203.0.113.10", port))]

        def connector(family, socktype, proto, sockaddr, timeout):
            return None  # connect succeeds

        result = guards.network_guard(
            hosts=["dead.example:443", "alive.example:443"],
            resolver=resolver, connector=connector)
        self.assertTrue(result["ok"])
        self.assertEqual(result["host"], "alive.example")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["ok"])
        self.assertTrue(result["attempts"][1]["ok"])
        self.assertEqual(result["action"], "network_workers_may_run")

    def test_guard_all_probes_fail_reports_degraded_action(self):
        def resolver(host, port, type=None):
            raise OSError("no network")

        result = guards.network_guard(
            hosts=["a.example:443", "b.example:443"], resolver=resolver)
        self.assertFalse(result["ok"])
        self.assertIn("defer_or_retry", result["action"])
        self.assertEqual(len(result["attempts"]), 2)

    def test_env_probe_hosts_order(self):
        with mock.patch.dict(os.environ,
                             {"MM_NETWORK_PROBE_HOSTS": "x.example:443, y.example:8443"}):
            parsed = guards._parse_probe_hosts()
        self.assertEqual(parsed, [("x.example", 443), ("y.example", 8443)])


class GuardCacheAndDedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "network_guard.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _always_fail(self, host, port, timeout, resolver=None, connector=None):
        return "OSError: simulated offline"

    def test_guard_error_dedup_within_ttl(self):
        """Repeated degraded observations produce at most one log event per TTL."""
        with mock.patch.object(guards, "_probe_once", self._always_fail):
            first_result, first_kind = guards.network_guard_event(cache_path=self.cache)
            second_result, second_kind = guards.network_guard_event(cache_path=self.cache)
        self.assertEqual(first_kind, "network_degraded")
        self.assertIsNone(second_kind)
        self.assertTrue(second_result["cached"])  # served from TTL cache

    def test_guard_dedup_while_continuously_degraded(self):
        """Even after cache expiry, a continuously-degraded network logs at most
        once per LOG_DEDUP_SECONDS window."""
        with mock.patch.object(guards, "_probe_once", self._always_fail):
            _, first_kind = guards.network_guard_event(cache_path=self.cache)
            # Expire the probe cache so the next call probes again.
            state = json.loads(self.cache.read_text())
            state["checked_at_epoch"] = 0
            self.cache.write_text(json.dumps(state))
            _, second_kind = guards.network_guard_event(cache_path=self.cache)
        self.assertEqual(first_kind, "network_degraded")
        self.assertIsNone(second_kind)  # deduped by LOG_DEDUP_SECONDS

    def test_guard_recovery_logged_once(self):
        with mock.patch.object(guards, "_probe_once", self._always_fail):
            guards.network_guard_event(cache_path=self.cache)
        with mock.patch.object(guards, "_probe_once",
                               lambda *a, **k: None):  # network back
            state = json.loads(self.cache.read_text())
            state["checked_at_epoch"] = 0  # expire cache
            self.cache.write_text(json.dumps(state))
            result, kind = guards.network_guard_event(cache_path=self.cache)
        self.assertTrue(result["ok"])
        self.assertEqual(kind, "network_recovered")

    def test_network_status_modes(self):
        self.assertEqual(guards.network_status(self.cache)["mode"], "unknown")
        with mock.patch.object(guards, "_probe_once", self._always_fail):
            guards.network_guard_event(cache_path=self.cache)
        status = guards.network_status(self.cache)
        self.assertEqual(status["mode"], "degraded")
        self.assertIsNotNone(status["since"])


class DeferredWorkerHeartbeat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = fresh_db(self.tmp.name)
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,public_website,discovered_at) "
            "VALUES(?,?,?)", ("Fixture Co", "https://fixture.example.co.nz",
                             c.now())).lastrowid
        p.enqueue(self.d, self.bid)

    def tearDown(self):
        self.d.close()
        self.tmp.cleanup()

    def test_deferred_worker_still_heartbeats(self):
        """A worker deferred by network failure (RetryableError) must still
        heartbeat so the supervisor never reaps it as stale."""
        def network_deferred_handler(d, it, worker):
            raise p.RetryableError("network degraded: deferring")

        worker = p.Worker("worker-net", ("DISCOVERED",), network_deferred_handler)
        worker.run_once(self.d)
        row = self.d.execute(
            "SELECT heartbeat_at FROM worker_registry WHERE worker_id=?",
            ("worker-net",)).fetchone()
        self.assertIsNotNone(row)
        age = c.dt.datetime.now(c.UTC) - c.timestamp(row["heartbeat_at"])
        self.assertLess(age.total_seconds(), 60)
        # The item is deferred (retry scheduled), not dead-lettered or reaped.
        item = p.item(self.d, self.bid)
        self.assertEqual(item["state"], "DISCOVERED")
        self.assertIsNotNone(item["next_retry_at"])
        metric = self.d.execute(
            "SELECT value FROM mm_metrics WHERE name='pipeline.items.retry_scheduled'"
        ).fetchone()
        self.assertIsNotNone(metric)


class EnsureRunning(unittest.TestCase):
    def test_ensure_running_noop_when_alive(self):
        with mock.patch.object(supervisor_cli, "_is_running", return_value=4242):
            result = supervisor_cli.cmd_ensure_running(object())
        self.assertFalse(result["started"])
        self.assertEqual(result["reason"], "already_running")
        self.assertEqual(result["pid"], 4242)

    def test_ensure_running_no_duplicate_workers(self):
        """Two concurrent ensure-running calls result in exactly one start."""
        calls = {"starts": 0}
        state = {"pid": None}

        def fake_is_running():
            return state["pid"]

        def fake_start(args):
            calls["starts"] += 1
            state["pid"] = 5000
            return {"started": True, "pid": 5000}

        with mock.patch.object(supervisor_cli, "_is_running", fake_is_running), \
             mock.patch.object(supervisor_cli, "cmd_start", fake_start):
            first = supervisor_cli.cmd_ensure_running(object())
            second = supervisor_cli.cmd_ensure_running(object())
        self.assertTrue(first["recovered"])
        self.assertEqual(calls["starts"], 1)
        self.assertFalse(second["started"])
        self.assertEqual(second["reason"], "already_running")

    def test_health_reports_network_mode(self):
        from types import SimpleNamespace
        with mock.patch.object(supervisor_cli, "network_status",
                               return_value={"mode": "degraded", "since": "t0",
                                             "checked_at": "t0"}):
            result = supervisor_cli.cmd_health(SimpleNamespace())
        self.assertEqual(result["network"]["mode"], "degraded")


if __name__ == "__main__":
    unittest.main()
