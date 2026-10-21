"""Synthetic policy and fake SMTP only; no credentials, sockets or live DB."""
import sqlite3
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser

import mm_core as core
import mm_smtp_candidate as candidate
import pytest
from test_send_readiness import db as db


@pytest.fixture
def approved(db, monkeypatch):
    recipient, body = 'synthetic@example.com', 'Subject: Synthetic review\n\nReview only.'
    digest = core.digest(recipient, body)
    db.execute('UPDATE mm_messages SET recipient=?,body=?,approved_hash=? WHERE id=1',
               (recipient, body, digest))
    db.execute('UPDATE approval_records SET content_hash=?', (digest,))
    db.commit()
    # Hypothetical reviewed policy, never written to real config.
    config = {'provider': 'gmail', 'enabled': True, 'external_send_allowed': True,
              'daily_cap': 1, 'requires_exact_approval': True,
              'requires_verified_recipient': True, 'requires_suppression_check': True}
    monkeypatch.setattr(candidate.mm_transport, 'load_config', lambda path=None: config.copy())
    inspection = candidate.readiness.inspect_message(db, 1)
    assert inspection['message_ready_for_transport_review'], inspection
    return db


class FakeSMTP:
    def __init__(self, *, login_hook=None, send_error=None, quit_error=None):
        self.events = []
        self.login_hook, self.send_error, self.quit_error = login_hook, send_error, quit_error

    def __call__(self, host, port, timeout):
        assert (host, port, timeout) == ('smtp.gmail.com', 587, 20)
        self.events.append('connect')
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.events.append('quit')
        if self.quit_error:
            raise self.quit_error

    def ehlo(self):
        self.events.append('ehlo')

    def starttls(self, *, context):
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        self.events.append('tls')

    def login(self, account, password):
        assert (account, password) == (candidate.SENDER, 'synthetic-only')
        self.events.append('login')
        if self.login_hook:
            self.login_hook()

    def sendmail(self, sender, recipients, wire):
        assert self.events == ['connect', 'ehlo', 'tls', 'ehlo', 'login']
        assert sender == candidate.SENDER and recipients == ['synthetic@example.com']
        message = BytesParser(policy=policy.default).parsebytes(wire)
        assert message['To'] == recipients[0] and not message['Bcc'] and not message['Cc']
        self.events.append('submit')
        if self.send_error:
            raise self.send_error
        return {}


def password(account):
    assert account == candidate.SENDER
    return 'synthetic-only'


def test_real_disabled_policy_stops_before_reads_writes_credentials_or_network(db):
    before = list(db.iterdump())
    db.execute('PRAGMA query_only=ON')

    def forbidden(*args, **kwargs):
        raise AssertionError('disabled policy reached a side effect')

    with pytest.raises(candidate.SubmissionHeldError, match='live_transport_not_approved'):
        candidate.submit(db, 1, password_loader=forbidden, smtp_factory=forbidden)
    assert list(db.iterdump()) == before


def test_single_claimed_attempt_uses_verified_tls_and_never_claims_delivery(approved):
    client = FakeSMTP()
    result = candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert result['status'] == 'ACCEPTED'
    assert result['delivery_confirmed'] is result['automatic_retry'] is False
    assert client.events.count('submit') == 1
    with pytest.raises(candidate.SubmissionHeldError, match='prior_submission'):
        candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert client.events.count('submit') == 1


def test_disconnect_after_submission_is_ambiguous_and_cannot_retry(approved):
    client = FakeSMTP(send_error=TimeoutError('synthetic provider timeout'))
    result = candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert result['status'] == 'UNKNOWN' and result['provider_submission_attempted']
    with pytest.raises(candidate.SubmissionHeldError, match='prior_submission'):
        candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert client.events.count('submit') == 1


def test_quit_failure_does_not_erase_provider_acceptance(approved):
    client = FakeSMTP(quit_error=TimeoutError('synthetic quit timeout'))
    assert candidate.submit(approved, 1, password_loader=password,
                            smtp_factory=client)['status'] == 'ACCEPTED'


@pytest.mark.parametrize('change', ['reject', 'edit', 'suppress'])
def test_last_moment_decision_change_stops_submission(approved, monkeypatch, change):
    def changed():
        if change == 'reject':
            approved.execute("INSERT INTO approval_records VALUES(2,2,'REJECTED',NULL)")
        elif change == 'edit':
            approved.execute("UPDATE mm_messages SET body='edited' WHERE id=1")
        else:
            monkeypatch.setattr(candidate.readiness.mm_approval, 'evaluate',
                                lambda *args: {'all_passed': False, 'gates': {}})
        approved.commit()

    client = FakeSMTP(login_hook=changed)
    result = candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert result['status'] == 'HELD' and not result['provider_submission_attempted']
    assert 'submit' not in client.events


def test_reservations_enforce_daily_cap_before_connecting(approved):
    client = FakeSMTP()
    candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    approved.execute('INSERT INTO mm_messages SELECT 2,business_id,recipient,body,approved_hash,'
                     'sent_at,invalidated_reason FROM mm_messages WHERE id=1')
    approved.commit()
    with pytest.raises(candidate.SubmissionHeldError, match='daily_cap'):
        candidate.submit(approved, 2, password_loader=password, smtp_factory=client)
    assert client.events.count('connect') == 1


def test_crash_reservation_blocks_replay(approved):
    envelope = candidate._approved_envelope(approved, 1)
    candidate._reserve(approved, 1, envelope, 1)
    with pytest.raises(candidate.SubmissionHeldError, match='prior_submission'):
        candidate.submit(approved, 1, password_loader=password, smtp_factory=FakeSMTP())


def test_acceptance_with_failed_persistence_retains_claim_and_blocks_replay(approved):
    class BrokenReceipt:
        def __getattr__(self, name):
            return getattr(approved, name)

        def execute(self, sql, args=()):
            if sql.startswith('UPDATE smtp_candidate_submissions'):
                raise sqlite3.OperationalError('synthetic receipt failure')
            return approved.execute(sql, args)

    client = FakeSMTP()
    with pytest.raises(sqlite3.OperationalError, match='synthetic receipt failure'):
        candidate.submit(BrokenReceipt(), 1, password_loader=password, smtp_factory=client)
    assert approved.execute('SELECT status FROM smtp_candidate_submissions').fetchone()[0] == 'RESERVED'
    with pytest.raises(candidate.SubmissionHeldError, match='prior_submission'):
        candidate.submit(approved, 1, password_loader=password, smtp_factory=client)
    assert client.events.count('submit') == 1


def test_two_connections_cannot_reserve_beyond_shared_cap(tmp_path):
    path = tmp_path / 'synthetic.db'
    with sqlite3.connect(path) as connection:
        connection.execute(candidate.DDL)
    barrier = threading.Barrier(2)

    def reserve(message_id):
        envelope = candidate.prepare(message_id, 'synthetic@example.com', 'Subject: Review\n\nHello')
        with sqlite3.connect(path, timeout=5) as connection:
            barrier.wait(timeout=5)
            try:
                candidate._reserve(connection, message_id, envelope, 1)
                return 'reserved'
            except candidate.SubmissionHeldError as exc:
                return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, (1, 2)))
    assert sorted(outcomes) == ['daily_cap_reserved', 'reserved']
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM smtp_candidate_submissions').fetchone()[0] == 1


@pytest.mark.parametrize('recipient,body', [
    ('synthetic@example.com\r\nBcc: other@example.com', 'Subject: Review\n\nHello'),
    ('synthetic@example.com', 'Subject: Review\nBcc: other@example.com\n\nHello'),
    ('synthetic@example.com', 'Subject: Review\r\n\r\nHello'),
    ('synthetic@example.com', 'Subject: Review\n\n'),
])
def test_header_injection_or_invalid_draft_is_rejected(recipient, body):
    with pytest.raises(candidate.SubmissionHeldError):
        candidate.prepare(1, recipient, body)
