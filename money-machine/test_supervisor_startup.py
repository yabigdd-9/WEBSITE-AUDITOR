"""Disposable supervisor startup: no host services or external network."""
import signal
import sqlite3
from types import SimpleNamespace

import mm_recurring_contact_review
import mm_recurring_discovery
from supervisor import cli


def test_startup_refreshes_network_before_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv('MM_ROOT', str(tmp_path))
    monkeypatch.setattr(cli, 'STATE', tmp_path / 'state')
    monkeypatch.setattr(cli, 'root', lambda: tmp_path)
    monkeypatch.setattr(cli, '_build_workers', lambda *args: [])
    monkeypatch.setattr(cli, '_heartbeat', lambda *args: None)
    monkeypatch.setattr(cli, '_log', lambda *args: None)
    handlers = {}
    monkeypatch.setattr(cli.signal, 'signal', lambda number, handler: handlers.update({number: handler}))
    order = []

    def network(**kwargs):
        assert kwargs == {'refresh': True}
        order.append('network')
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return {'ok': True}, 'network_recovered'

    monkeypatch.setattr(cli, 'network_guard_event', network)
    monkeypatch.setattr(mm_recurring_discovery, 'run_due',
                        lambda db: order.append('discovery') or {'reason': 'disabled_or_not_due'})
    monkeypatch.setattr(mm_recurring_contact_review, 'tick', lambda db: {'reason': 'disabled'})
    monkeypatch.setattr(mm_recurring_contact_review, 'shutdown', lambda: None)
    (tmp_path / 'database').mkdir()
    with sqlite3.connect(tmp_path / 'database/money_machine.db') as db:
        db.execute('CREATE TABLE businesses(id INTEGER PRIMARY KEY)')
    args = SimpleNamespace(sleep=5, lease=300, rotate_every=60, worker=None)
    assert cli.cmd_run_foreground(args) == 0
    assert order == ['network', 'discovery']
