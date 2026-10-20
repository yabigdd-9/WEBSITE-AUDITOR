"""Behavioral coverage for operator log time windows and global newest-first limits."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from supervisor import logquery  # noqa: E402


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(logquery, 'root', lambda: tmp_path)
    directory = tmp_path / 'state/worker-logs'
    directory.mkdir(parents=True)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 10, 20, 12, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(logquery, 'datetime', Clock)

    def write(name, records):
        (directory / name).write_text('\n'.join(json.dumps(r) for r in records) + '\n')

    return write


@pytest.mark.parametrize(('since', 'old'), [
    ('1h', '2026-10-20T10:59:59Z'),
    ('1d', '2026-10-19T11:59:59Z'),
    ('1w', '2026-10-13T11:59:59Z'),
    ('1m', '2026-09-20T11:59:59Z'),
])
def test_since_uses_requested_window(logs, since, old):
    logs('a.jsonl', [{'at': old, 'id': 'old'},
                     {'at': '2026-10-20T11:30:00Z', 'id': 'new'}])
    assert [r['id'] for r in logquery.query_logs(since=since)] == ['new']


def test_offsets_sort_by_instant_and_naive_legacy_dates_mean_utc(logs):
    logs('a.jsonl', [{'at': '2026-10-20T23:15:00+13:00', 'id': 'old'},
                     {'at': '2026-10-20T11:30:00', 'id': 'new'},
                     {'at': '2026-10-20T11:00:00Z', 'id': 'boundary'}])
    assert [r['id'] for r in logquery.query_logs(since='1h')] == ['new', 'boundary']


def test_limit_applies_after_searching_all_files(logs):
    logs('a.jsonl', [{'at': '2026-10-20T10:00:00Z', 'id': 'old'},
                     {'at': '2026-10-20T11:00:00Z', 'id': 'middle'}])
    logs('z.jsonl', [{'at': '2026-10-20T11:59:00Z', 'id': 'newest'}])
    assert [r['id'] for r in logquery.query_logs(limit=2)] == ['newest', 'middle']


def test_malformed_records_cannot_crash_or_establish_freshness(logs):
    logs('a.jsonl', [None, [], 4, {'at': 123}, {'at': 'bad-date'},
                     {'id': 'unknown-time'}, {'at': '2026-10-20T11:40:00Z', 'id': 'valid'}])
    assert [r['id'] for r in logquery.query_logs(since='1h')] == ['valid']
    assert len(logquery.query_logs()) == 4


def test_filters_are_combined_before_limiting(logs):
    logs('a.jsonl', [
        {'at': '2026-10-20T11:55:00Z', 'kind': 'done', 'worker_id': 'a', 'level': 'info'},
        {'at': '2026-10-20T11:50:00Z', 'kind': 'done', 'worker_id': 'b', 'level': 'error'},
        {'at': '2026-10-20T11:45:00Z', 'kind': 'done', 'worker_id': 'a', 'level': 'error'},
    ])
    result = logquery.query_logs(kind='done', worker='a', level='error', limit=1)
    assert result[0]['at'] == '2026-10-20T11:45:00Z'


@pytest.mark.parametrize('since', ['1hour', '1h trailing', '-1h', 'tomorrow', '1.5d'])
def test_invalid_windows_are_rejected(logs, since):
    with pytest.raises(ValueError, match='since'):
        logquery.query_logs(since=since)


def test_zero_limit_returns_no_rows_and_negative_limit_is_rejected(logs):
    logs('a.jsonl', [{'at': '2026-10-20T11:50:00Z'}])
    assert logquery.query_logs(limit=0) == []
    with pytest.raises(ValueError, match='limit'):
        logquery.query_logs(limit=-1)


def test_cli_invalid_window_is_an_argument_error(logs):
    with pytest.raises(SystemExit) as result:
        logquery.query_logs_cli(['--since', 'broken'])
    assert result.value.code == 2
