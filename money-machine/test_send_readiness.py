"""Read-only send review with synthetic messages; no credentials or network."""
import sqlite3

import mm_core as core
import mm_send_readiness as readiness
import pytest


@pytest.fixture
def db(monkeypatch):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.executescript('''
        CREATE TABLE mm_messages(id INTEGER PRIMARY KEY,business_id INTEGER,recipient TEXT,
          body TEXT,approved_hash TEXT,sent_at TEXT,invalidated_reason TEXT);
        CREATE TABLE approval_records(id INTEGER PRIMARY KEY,business_id INTEGER,
          status TEXT,content_hash TEXT);
    ''')
    digest = core.digest('synthetic@example.invalid', 'Subject: Synthetic\n\nReview only.')
    connection.execute('INSERT INTO mm_messages VALUES(1,2,?,?,?,?,?)',
                       ('synthetic@example.invalid', 'Subject: Synthetic\n\nReview only.',
                        digest, None, None))
    connection.execute('INSERT INTO approval_records VALUES(1,2,?,?)', ('APPROVED', digest))
    connection.commit()
    monkeypatch.setattr(readiness.mm_email_store, 'require_email', lambda *args: None)
    monkeypatch.setattr(readiness.mm_approval, 'evaluate',
                        lambda *args: {'all_passed': True, 'gates': {}})
    yield connection
    connection.close()


def test_valid_draft_is_reviewable_but_cannot_send_or_write(db):
    before = list(db.iterdump())
    db.execute('PRAGMA query_only=ON')
    result = readiness.inspect_message(db, 1)
    assert result['message_ready_for_transport_review'] is True
    assert result['ready_to_send'] is False
    assert result['holds'] == ['live_transport_not_approved']
    assert result['external_messages_sent'] == result['network_calls'] == 0
    assert list(db.iterdump()) == before


@pytest.mark.parametrize('column,value,hold', [
    ('body', 'changed', 'exact_message_approval'),
    ('recipient', 'changed@example.invalid', 'exact_message_approval'),
    ('sent_at', '2026-01-01', 'not_already_sent'),
    ('invalidated_reason', 'revoked', 'draft_valid'),
])
def test_changed_or_sent_draft_is_held(db, column, value, hold):
    # Column names come only from this finite test parameter list.
    statements = {
        'body': 'UPDATE mm_messages SET body=? WHERE id=1',
        'recipient': 'UPDATE mm_messages SET recipient=? WHERE id=1',
        'sent_at': 'UPDATE mm_messages SET sent_at=? WHERE id=1',
        'invalidated_reason': 'UPDATE mm_messages SET invalidated_reason=? WHERE id=1',
    }
    db.execute(statements[column], (value,))
    result = readiness.inspect_message(db, 1)
    assert result['message_ready_for_transport_review'] is False
    assert hold in result['holds']


def test_newer_rejection_revokes_old_approval(db):
    db.execute("INSERT INTO approval_records VALUES(2,2,'REJECTED',NULL)")
    assert readiness.inspect_message(db, 1)['checks']['latest_approval_matches'] is False


def test_missing_message_is_an_explicit_hold(db):
    result = readiness.inspect_message(db, 999)
    assert result['holds'] == ['message_exists', 'live_transport_not_approved']


def test_verification_or_consent_failure_blocks_review(db, monkeypatch):
    monkeypatch.setattr(readiness.mm_approval, 'evaluate',
                        lambda *args: {'all_passed': False, 'gates': {'consent': {'passed': False}}})
    assert readiness.inspect_message(db, 1)['message_ready_for_transport_review'] is False


def test_missing_schema_is_an_explicit_hold(db):
    db.execute('DROP TABLE approval_records')
    result = readiness.inspect_message(db, 1)
    assert result['ready_to_send'] is False
    assert result['checks']['inspection_available'] is False
