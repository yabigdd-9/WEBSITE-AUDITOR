"""Synthetic runtime artifacts; no live DB, browser, transport or provider."""
import importlib.util
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('artifact_test_' + name,
                                                REPO / 'ops/hermes_zero_token' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    cwd = Path.cwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
    return module


@pytest.mark.parametrize('name,field,relative', [
    ('screenshot_worker', 'SCREENSHOT_DIR', 'screenshots'),
    ('demo_blueprint', 'BLUEPRINTS_DIR', 'demo_blueprints'),
    ('outreach_draft', 'DRAFTS_DIR', 'outreach_drafts'),
    ('outreach_draft', 'APPROVAL_QUEUE_PATH', 'APPROVAL_QUEUE.yaml'),
    ('daily_report', 'REPORTS_DIR', 'reports'),
    ('runner', 'REPORTS_DIR', 'reports'),
])
def test_all_runtime_output_roots_use_state(name, field, relative):
    module = load(name)
    assert getattr(module, field) == REPO / 'state/hermes_zero_token' / relative


@pytest.mark.parametrize('mode', ['new_capture', 'existing_capture', 'empty'])
def test_screenshots_do_not_rewrite_historical_reports(tmp_path, monkeypatch, capsys, mode):
    module = load('screenshot_worker')
    runtime = tmp_path / 'state/hermes_zero_token/screenshots'
    legacy = tmp_path / 'reports/hermes_zero_token/screenshots'
    legacy.mkdir(parents=True)
    for name in ('manifest_sha256.json', 'screenshot_report.json'):
        (legacy / name).write_text('{"historical_fixture":true}')
    before = {p.name: p.read_bytes() for p in legacy.iterdir()}
    monkeypatch.setattr(module, 'SCREENSHOT_DIR', runtime)
    monkeypatch.setattr(module, 'MANIFEST_PATH', runtime / 'manifest_sha256.json')
    businesses = [] if mode == 'empty' else [{'id': 1, 'name': 'Synthetic',
                                             'public_website': 'https://example.invalid/'}]
    monkeypatch.setattr(module, 'get_pending_businesses', lambda limit: businesses)
    calls = []

    def capture(url, folder):
        calls.append(url)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'synthetic.png').write_bytes(b'synthetic fixture, not a real capture')
        return 0, '{}', ''

    monkeypatch.setattr(module, 'capture_with_browser_toolkit', capture)
    if mode == 'existing_capture':
        folder = runtime / 'business-1'
        folder.mkdir(parents=True)
        (folder / 'synthetic.png').write_bytes(b'existing synthetic fixture')
    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['production_written'] is False
    assert Path(report['screenshot_dir']) == runtime
    assert (runtime / 'screenshot_report.json').is_file()
    assert {p.name: p.read_bytes() for p in legacy.iterdir()} == before
    assert len(calls) == (1 if mode == 'new_capture' else 0)


def test_blueprints_are_generated_under_runtime_state(tmp_path, monkeypatch, capsys):
    module = load('demo_blueprint')
    runtime = tmp_path / 'state/hermes_zero_token/demo_blueprints'
    legacy = tmp_path / 'reports/hermes_zero_token/demo_blueprints'
    legacy.mkdir(parents=True)
    old = legacy / 'demo_blueprint_report.json'
    old.write_text('{"historical":true}')
    monkeypatch.setattr(module, 'BLUEPRINTS_DIR', runtime)
    monkeypatch.setattr(module, 'get_businesses_with_audit', lambda limit: [
        {'business_id': 1, 'audit_id': 1, 'name': 'Synthetic', 'public_website': 'https://example.invalid/'}])
    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['blueprints_created'] == 1 and report['outbound_messages_sent'] == 0
    assert Path(report['details'][0]['blueprint_path']).is_relative_to(runtime)
    assert old.read_text() == '{"historical":true}'


@pytest.fixture
def outreach(tmp_path, monkeypatch):
    module = load('outreach_draft')
    runtime = tmp_path / 'state/hermes_zero_token'
    legacy = tmp_path / 'approval/APPROVAL_QUEUE.yaml'
    legacy.parent.mkdir(parents=True)
    queue = {'owner_note': 'preserve metadata', 'requires_dion_approval': [
        {'id': 'historical', 'status': 'REJECTED', 'human_note': 'do not replace'}]}
    legacy.write_text(yaml.safe_dump(queue))
    monkeypatch.setattr(module, 'DRAFTS_DIR', runtime / 'outreach_drafts')
    monkeypatch.setattr(module, 'APPROVAL_QUEUE_PATH', runtime / 'APPROVAL_QUEUE.yaml')
    monkeypatch.setattr(module, 'LEGACY_APPROVAL_QUEUE_PATH', legacy)
    monkeypatch.setattr(module, 'get_businesses_with_evidence', lambda limit: [
        {'business_id': 1, 'name': 'Synthetic', 'public_website': 'https://example.invalid/',
         'evidence_id': 1, 'observation': 'synthetic fixture'}])
    return module, legacy, queue


def test_legacy_queue_and_metadata_survive_append_into_runtime_state(outreach, capsys):
    module, legacy, original = outreach
    before = legacy.read_bytes()
    assert module.main() == 0
    report = json.loads(capsys.readouterr().out)
    saved = yaml.safe_load(module.APPROVAL_QUEUE_PATH.read_text())
    assert saved['owner_note'] == original['owner_note']
    assert saved['requires_dion_approval'][0] == original['requires_dion_approval'][0]
    assert saved['requires_dion_approval'][1]['status'] == 'NOT_SENT_AWAITING_APPROVAL'
    assert report['outbound_messages_sent'] == 0
    assert legacy.read_bytes() == before
    assert stat.S_IMODE(module.APPROVAL_QUEUE_PATH.stat().st_mode) == 0o600
    assert not list(module.APPROVAL_QUEUE_PATH.parent.glob('.approval-*'))


def test_runtime_queue_is_authoritative_and_does_not_reimport_legacy(outreach, capsys):
    module, legacy, original = outreach
    module.APPROVAL_QUEUE_PATH.parent.mkdir(parents=True)
    runtime_queue = {'runtime_metadata': 'keep', 'requires_dion_approval': [
        {'id': 'newer-human-decision', 'status': 'REVOKED'}]}
    module.APPROVAL_QUEUE_PATH.write_text(yaml.safe_dump(runtime_queue))
    module.main()
    capsys.readouterr()
    saved = yaml.safe_load(module.APPROVAL_QUEUE_PATH.read_text())
    assert saved['runtime_metadata'] == 'keep'
    assert saved['requires_dion_approval'][0] == runtime_queue['requires_dion_approval'][0]
    assert all(item['id'] != 'historical' for item in saved['requires_dion_approval'])
    assert yaml.safe_load(legacy.read_text()) == original


def test_invalid_runtime_queue_is_never_overwritten_or_silently_reset(outreach):
    module, legacy, original = outreach
    module.APPROVAL_QUEUE_PATH.parent.mkdir(parents=True)
    module.APPROVAL_QUEUE_PATH.write_text('requires_dion_approval: wrong-type\n')
    before = module.APPROVAL_QUEUE_PATH.read_bytes()
    with pytest.raises(ValueError, match='approval item list'):
        module.main()
    assert module.APPROVAL_QUEUE_PATH.read_bytes() == before
    assert not list(module.DRAFTS_DIR.glob('*.md'))
    assert yaml.safe_load(legacy.read_text()) == original


def test_concurrent_draft_workers_do_not_drop_review_items(outreach, monkeypatch, capsys):
    module, _, original = outreach
    businesses = iter([{'business_id': i, 'name': 'Synthetic',
                        'public_website': 'https://example.invalid/', 'evidence_id': i}
                       for i in (1, 2)])
    monkeypatch.setattr(module, 'get_businesses_with_evidence', lambda limit: [next(businesses)])
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: module.main(), range(2))) == [0, 0]
    capsys.readouterr()
    saved = yaml.safe_load(module.APPROVAL_QUEUE_PATH.read_text())
    assert saved['requires_dion_approval'][0] == original['requires_dion_approval'][0]
    assert {item['id'] for item in saved['requires_dion_approval'][1:]} == {'APR-ZT-1', 'APR-ZT-2'}


def test_daily_report_uses_runtime_state_without_live_database(tmp_path, monkeypatch):
    module = load('daily_report')
    monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(module, 'STATE_DIR', tmp_path / 'state')
    monkeypatch.setattr(module, 'REPORTS_DIR', tmp_path / 'state/hermes_zero_token/reports')
    monkeypatch.setattr(module, 'DB_PATH', tmp_path / 'absent.db')
    metrics = module.collect_metrics()
    report = module.write_daily_report(metrics)
    assert report.is_relative_to(tmp_path / 'state')
    assert not (tmp_path / 'reports').exists()


def test_dashboard_switches_to_runtime_queue_and_never_falls_back_on_parse_error(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('runtime_queue_dashboard', REPO / 'audit-dashboard/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    legacy = tmp_path / 'approval/APPROVAL_QUEUE.yaml'
    legacy.parent.mkdir()
    legacy.write_text(yaml.safe_dump({'requires_dion_approval': [{'id': 'legacy', 'status': 'PENDING'}]}))
    runtime = tmp_path / 'state/hermes_zero_token/APPROVAL_QUEUE.yaml'
    monkeypatch.setattr(module, 'REPO_ROOT', str(tmp_path))
    monkeypatch.setattr(module, 'APPROVAL_YAML', str(legacy))
    monkeypatch.setattr(module, 'RUNTIME_APPROVAL_YAML', str(runtime))
    monkeypatch.setattr(module, 'DB_JSON', str(tmp_path / 'missing.json'))
    monkeypatch.setattr(module, 'DB_CSV', str(tmp_path / 'missing.csv'))
    monkeypatch.setattr(module, 'STATE_YAML', str(tmp_path / 'missing.yaml'))
    monkeypatch.setattr(module, 'OUTPUTS_DIR', str(tmp_path / 'missing-outputs'))
    assert module.build_model()['approval']['items'][0]['id'] == 'legacy'
    runtime.parent.mkdir(parents=True)
    runtime.write_text(yaml.safe_dump({'requires_dion_approval': [{'id': 'runtime', 'status': 'REVOKED'}]}))
    model = module.build_model()
    assert model['approval']['items'][0]['id'] == 'runtime'
    assert 'state/hermes_zero_token/APPROVAL_QUEUE.yaml' in module.render_html(model)
    runtime.write_text('invalid: [unterminated')
    model = module.build_model()
    assert model['approval'] is None
    assert 'Selected approval queue not found or unreadable' in module.render_html(model)
