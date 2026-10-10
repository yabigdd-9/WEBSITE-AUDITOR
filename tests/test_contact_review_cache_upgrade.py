"""Isolated evidence reuse, scheduling and request-saving contracts."""
import copy
import json
import socket
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'money-machine'))

import mm_contact_review_cache as cache  # noqa: E402
import mm_contact_review_tasks as tasks  # noqa: E402
import mm_recurring_contact_review as recurring  # noqa: E402

CONFIG = {
    'enabled': True, 'scan_interval_seconds': 60, 'refresh_hours': 24,
    'max_businesses_per_job': 2, 'job_timeout_seconds': 180,
    'case_timeout_seconds': 80, 'collection_timeout_seconds': 55,
    'dns_timeout_seconds': 15, 'max_pages': 3, 'max_requests': 5,
    'max_dns_domains': 5, 'model_execution_enabled': False,
    'evidence_reuse_enabled': True,
}
HASHES = {path: 'acquisition-v1' for path in cache.ACQUISITION_FILES}
HASHES['money-machine/mm_contact_review_pathway.py'] = 'decision-v1'
BUSINESS = {
    'id': 'business-1', 'live_business_id': 1, 'name': 'Synthetic Services',
    'region': 'Auckland', 'public_website': 'https://business.nz/',
    'source': 'synthetic', 'branch': 'Auckland', 'unit_scope': 'Recorded branch',
    'pipeline_updated_at': 'old', 'pipeline_state_at_freeze': 'NEEDS_REVIEW',
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError('Real network, database, models and processes are forbidden')
    monkeypatch.setenv('MM_ROOT', str(tmp_path))
    monkeypatch.setenv('MM_EXTERNAL_SEND_DISABLED', '1')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    monkeypatch.setattr(recurring, 'root', lambda: tmp_path)
    monkeypatch.setattr(recurring, 'connect', forbidden)
    monkeypatch.setattr(recurring, 'get_public', forbidden)
    monkeypatch.setattr(recurring.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(recurring.os, 'kill', forbidden)
    monkeypatch.setattr(recurring.signal, 'alarm', Mock())
    monkeypatch.setattr(recurring.signal, 'signal', Mock())
    monkeypatch.setitem(sys.modules, 'mm_model_router', SimpleNamespace(local_complete=forbidden))


def saved_collection(runtime, *, page_age_hours=0, dns_age_hours=0, errors=None):
    job = runtime / 'state/contact-review/runs/synthetic-original'
    folder = job / BUSINESS['id']
    raw_path = folder / 'evidence/cache/page.capture'
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b'<h1>Synthetic Services</h1><p>Auckland contact page</p>')
    at = datetime.now(timezone.utc)
    raw_hash = cache.sha(raw_path)
    document = {
        'business': dict(BUSINESS),
        'pages': [{'url': BUSINESS['public_website'] + 'contact',
                   'path': 'cache/page.capture', 'sha256': raw_hash,
                   'captured_at': (at - timedelta(hours=page_age_hours)).isoformat()}],
        'dns': {'business.nz': {'checked_at': (at - timedelta(hours=dns_age_hours)).isoformat(),
                               'status': 'mx', 'domain_accepts_mail': True}},
        'errors': errors or [],
        'stage_timings': {'collection_seconds': 12.0, 'dns_seconds': 3.0, 'total_seconds': 15.0},
        'request_metrics': {'actual_requests': 4, 'reserved_requests': 0,
                            'accounting': 'attempt_callbacks'},
    }
    collection = folder / 'COLLECTION.json'
    write_json(collection, document)
    write_json(job / 'MANIFEST.json', {
        str(collection.relative_to(job)): cache.sha(collection),
        str(raw_path.relative_to(job)): raw_hash,
    })
    acquisition = cache.acquisition_key(BUSINESS, HASHES, CONFIG)
    entry = cache.cache_entry(job, folder, document, acquisition)
    return SimpleNamespace(job=job, folder=folder, raw=raw_path,
                           document=document, entry=entry, acquisition=acquisition)


@pytest.mark.parametrize('field', ['pipeline_updated_at', 'pipeline_state_at_freeze'])
def test_pipeline_bookkeeping_does_not_invalidate_capture(field):
    changed = {**BUSINESS, field: 'updated'}
    assert cache.acquisition_key(changed, HASHES, CONFIG) == cache.acquisition_key(BUSINESS, HASHES, CONFIG)


def test_rule_changes_do_not_invalidate_acquisition_key():
    newer = {**HASHES, 'money-machine/mm_contact_review_pathway.py': 'decision-v2'}
    assert cache.acquisition_key(BUSINESS, newer, CONFIG) == cache.acquisition_key(BUSINESS, HASHES, CONFIG)


@pytest.mark.parametrize('field,value', [
    ('branch', 'Dunedin'), ('region', 'Dunedin'), ('name', 'Other Services'),
    ('public_website', 'https://other.nz/'), ('live_business_id', 2),
])
def test_changed_business_unit_invalidates_acquisition(field, value):
    assert cache.acquisition_key({**BUSINESS, field: value}, HASHES, CONFIG) != cache.acquisition_key(BUSINESS, HASHES, CONFIG)


@pytest.mark.parametrize('path', cache.ACQUISITION_FILES)
def test_changed_network_source_invalidates_acquisition(path):
    newer = {**HASHES, path: 'network-v2'}
    assert cache.acquisition_key(BUSINESS, newer, CONFIG) != cache.acquisition_key(BUSINESS, HASHES, CONFIG)


@pytest.mark.parametrize('field', cache.ACQUISITION_FIELDS)
def test_changed_collection_limits_invalidate_acquisition(field):
    changed = {**CONFIG, field: CONFIG[field] + 1}
    assert cache.acquisition_key(BUSINESS, HASHES, changed) != cache.acquisition_key(BUSINESS, HASHES, CONFIG)


def test_rule_only_replay_rejudges_current_rules_with_zero_fetches(monkeypatch, tmp_path):
    saved = saved_collection(tmp_path)
    before = cache.sha(saved.folder / 'COLLECTION.json')
    write_json(tmp_path / 'state/contact-review/cache/1.json', saved.entry)
    new_hashes = {**HASHES, 'money-machine/mm_contact_review_pathway.py': 'decision-v2'}
    new_job = tmp_path / 'state/contact-review/runs/synthetic-new-rules'
    request = {'cases': [{'business': dict(BUSINESS),
                         'fingerprint': recurring.fingerprint(BUSINESS, new_hashes)}],
               'source_hashes': new_hashes, 'config': CONFIG, 'seed_packets': []}
    write_json(new_job / 'JOB.json', request)
    monkeypatch.setattr(recurring, 'source_hashes', lambda: new_hashes)
    monkeypatch.setattr(recurring, 'load_config', lambda: CONFIG)
    monkeypatch.setattr(recurring, 'current_business', lambda bid: dict(BUSINESS))
    def no_fetch(*args):
        raise AssertionError('Fresh matching capture must avoid acquisition')
    monkeypatch.setattr(recurring, 'collect_case', no_fetch)
    monkeypatch.setattr(recurring, 'seed_case', no_fetch)
    calls = []
    def new_review(business, doc, folder, at):
        calls.append({'decision_source': recurring.source_hashes()['money-machine/mm_contact_review_pathway.py'],
                      'capture': str(folder)})
        return {'case_id': business['id'], 'live_business_id': 1,
                'company': business['name'], 'website': business['public_website'],
                'identity': {'status': 'HIGH', 'reasons': [], 'name_suggestions': []},
                'verifier': {'selected': None}, 'proofer': {'passed': False, 'checks': {}, 'sources': []},
                'judge': {'route': 'CONTACT_EXCEPTION', 'next_worker': 'CONTACT_VERIFIER',
                              'reason': 'Current synthetic decision', 'outreach_eligible': False,
                              'pipeline_state_at_capture': 'NEEDS_REVIEW'}}
    monkeypatch.setattr(recurring, 'review_case', new_review)
    recurring.process_job(new_job)
    result = json.loads((new_job / '1.json').read_text())
    assert result['status'] == 'COMPLETE'
    assert result['row']['collection_method'] == 'HASH_VERIFIED_CAPTURE_REUSED'
    assert calls == [{'decision_source': 'decision-v2', 'capture': str(saved.folder)}]
    assert cache.sha(saved.folder / 'COLLECTION.json') == before
    assert result['external_sends'] == result['model_calls'] == result['pipeline_writes'] == 0


def test_reuse_reports_current_zero_requests_not_historical_work(tmp_path):
    saved = saved_collection(tmp_path)
    _, doc, _ = cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path)
    assert doc['request_metrics']['actual_requests'] == 0
    assert doc['request_metrics']['reserved_requests'] == 0
    assert doc['stage_timings']['collection_seconds'] == 0


def test_stale_dns_refreshes_only_dns_and_preserves_immutable_html(tmp_path):
    saved = saved_collection(tmp_path, dns_age_hours=2)
    before = {path: cache.sha(path) for path in (saved.raw, saved.folder / 'COLLECTION.json', saved.job / 'MANIFEST.json')}
    checks = []
    class Checker:
        def check(self, domain, *, deadline):
            checks.append((domain, deadline))
            return {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'mx'}
    _, doc, method = cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path,
                                dns_factory=Checker)
    assert method == 'HASH_VERIFIED_CAPTURE_REUSED'
    assert len(checks) == 1
    assert checks[0][0] == 'business.nz'
    assert all(cache.sha(path) == digest for path, digest in before.items())
    assert doc['dns']['business.nz']['checked_at'] != saved.document['dns']['business.nz']['checked_at']
    assert doc['request_metrics']['actual_requests'] == 0


def test_stale_dns_without_bounded_checker_is_a_cache_miss(tmp_path):
    saved = saved_collection(tmp_path, dns_age_hours=2)
    assert cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path) is None


@pytest.mark.parametrize('hours', [25, -1])
def test_expired_or_future_html_is_not_reused(tmp_path, hours):
    saved = saved_collection(tmp_path, page_age_hours=hours)
    assert cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path) is None


@pytest.mark.parametrize('target', ['capture', 'collection', 'manifest'])
def test_tampered_cached_evidence_fails_closed(tmp_path, target):
    saved = saved_collection(tmp_path)
    path = {'capture': saved.raw, 'collection': saved.folder / 'COLLECTION.json',
            'manifest': saved.job / 'MANIFEST.json'}[target]
    path.write_bytes(path.read_bytes() + b'\nchanged')
    with pytest.raises(ValueError, match='changed|integrity'):
        cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path)


def test_same_fingerprint_cannot_attach_capture_to_other_unit(tmp_path):
    saved = saved_collection(tmp_path)
    with pytest.raises(ValueError, match='another business/unit'):
        cache.reuse(saved.entry, {**BUSINESS, 'branch': 'Dunedin'}, saved.acquisition, tmp_path)


def test_acquisition_mismatch_does_not_read_invalid_cache(tmp_path):
    saved = saved_collection(tmp_path)
    saved.raw.unlink()
    assert cache.reuse(saved.entry, BUSINESS, 'different-acquisition-key', tmp_path) is None


def test_partial_collection_errors_are_not_cached(tmp_path):
    saved = saved_collection(tmp_path, errors=[{'reason': 'HTTP_404'}])
    assert saved.entry is None


def test_duplicate_reuse_is_deterministic_and_documents_are_independent(tmp_path):
    saved = saved_collection(tmp_path)
    before = cache.sha(saved.folder / 'COLLECTION.json')
    first = cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path)
    second = cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path)
    assert first[0] == second[0]
    assert first[1]['pages'] == second[1]['pages']
    first[1]['pages'][0]['url'] = 'https://changed.nz/'
    assert second[1]['pages'][0]['url'] == saved.document['pages'][0]['url']
    assert cache.sha(saved.folder / 'COLLECTION.json') == before


def test_cache_outside_owned_runtime_is_rejected(tmp_path):
    saved = saved_collection(tmp_path)
    changed = {**saved.entry, 'job': str(tmp_path / 'other-job')}
    with pytest.raises(ValueError, match='escaped'):
        cache.reuse(changed, BUSINESS, saved.acquisition, tmp_path)


@pytest.mark.parametrize('dns_age_hours', [0, 2])
def test_expired_case_deadline_rejects_both_fresh_and_stale_dns(monkeypatch, tmp_path, dns_age_hours):
    saved = saved_collection(tmp_path, dns_age_hours=dns_age_hours)
    monkeypatch.setattr(cache.time, 'monotonic', lambda: 100.0)
    with pytest.raises(TimeoutError, match='DEADLINE'):
        cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path,
                    dns_factory=lambda: None, deadline=99.0)


def test_dns_cache_refresh_is_capped_to_fifteen_seconds(monkeypatch, tmp_path):
    saved = saved_collection(tmp_path, dns_age_hours=2)
    monkeypatch.setattr(cache.time, 'monotonic', lambda: 100.0)
    deadlines = []
    class Checker:
        def check(self, domain, *, deadline):
            deadlines.append(deadline)
            return {'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'unknown'}
    cache.reuse(saved.entry, BUSINESS, saved.acquisition, tmp_path,
                dns_factory=Checker, deadline=200.0)
    assert deadlines == [115.0]


@pytest.mark.parametrize('status', ['REVIEW_ERROR', 'INCOMPLETE', 'TIMEOUT', 'SCHEDULED'])
def test_transient_execution_failures_use_bounded_retry(status):
    at = datetime(2026, 10, 6, tzinfo=timezone.utc)
    for attempts, seconds in enumerate((60, 300, 1800)):
        latest = {'fingerprint': 'same', 'reviewed_at': at.isoformat(),
                  'status': status, 'retry_attempts': attempts}
        decision = tasks.schedule(latest, 'same', at=at)
        assert decision['reason'] == 'TRANSIENT_RETRY'
        assert decision['due'] is False
        assert tasks.timestamp(decision['due_at']) == at + timedelta(seconds=seconds)
    exhausted = tasks.schedule({**latest, 'retry_attempts': 3}, 'same', at=at)
    assert exhausted['reason'] == 'RETRY_EXHAUSTED'
    assert tasks.timestamp(exhausted['due_at']) == at + timedelta(hours=24)


def test_partial_acquisition_failure_retries_but_access_restrictions_hold():
    at = datetime(2026, 10, 6, tzinfo=timezone.utc)
    latest = {'fingerprint': 'same', 'reviewed_at': at.isoformat(), 'status': 'COMPLETE',
              'retryable_acquisition_error': True, 'retry_attempts': 0}
    assert tasks.schedule(latest, 'same', at=at)['reason'] == 'TRANSIENT_RETRY'
    latest['row'] = {'scout': {'acquisition_errors': ['ACCESS_RESTRICTED_OR_ROBOTS_UNAVAILABLE']}}
    decision = tasks.schedule(latest, 'same', at=at)
    assert decision['reason'] == 'ACCESS_HOLD'
    assert tasks.timestamp(decision['due_at']) == at + timedelta(hours=24)


def test_changed_business_bypasses_failure_backoff_without_retry_storm():
    at = datetime(2026, 10, 6, tzinfo=timezone.utc)
    latest = {'fingerprint': 'old', 'reviewed_at': at.isoformat(), 'status': 'TIMEOUT',
              'retry_attempts': 3}
    decision = tasks.schedule(latest, 'new', at=at)
    assert decision['due'] is True
    assert decision['attempts'] == 0
    assert decision['reason'] == 'EVIDENCE_CHANGED'


@pytest.mark.parametrize('status', ['STALE_LIVE_STATE', 'TIMEOUT', 'REVIEW_ERROR'])
def test_noncurrent_supported_row_never_routes_to_draft_worker(status):
    result = {'live_business_id': 1, 'fingerprint': 'frozen', 'status': status,
              'row': {'judge': {'route': 'MACHINE_SUPPORTED_RECOMMENDATION'},
                      'proofer': {'checks': {'published': True}}}}
    task = tasks.task_for(result)
    assert task['required_worker'] != 'DRAFT_PREPARATION'
    assert task['permitted_action'] != 'BUILD_LOCAL_DRAFT'
    assert task['external_sends'] == task['model_calls'] == 0


def test_duplicate_task_build_is_deterministic_and_never_mutates_input():
    result = {'live_business_id': 1, 'fingerprint': 'frozen', 'status': 'COMPLETE',
              'row': {'judge': {'route': 'MACHINE_SUPPORTED_RECOMMENDATION'},
                      'proofer': {'checks': {'published': True}}}}
    original = copy.deepcopy(result)
    first, second = tasks.task_for(result), tasks.task_for(result)
    assert first == second
    assert result == original
    assert first['required_worker'] == 'DRAFT_PREPARATION'
    assert first['authority'] == 'DRAFT_ONLY'
