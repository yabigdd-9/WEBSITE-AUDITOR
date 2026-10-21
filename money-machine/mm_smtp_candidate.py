"""Unregistered SMTP candidate for review, blocked by canonical transport policy.

No CLI, scheduler registration, credential lookup or configuration activation.
The current canonical config loader rejects every live provider. Offline tests
exercise a hypothetical reviewed policy and fake SMTP sessions only.
"""
from __future__ import annotations

import hashlib
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP

import mm_core as core
import mm_send_readiness as readiness
import mm_transport
from email_validator import validate_email

SENDER = 'team.catalyxlabs@gmail.com'
MAX_BODY_BYTES = 1024 * 1024
DDL = '''CREATE TABLE IF NOT EXISTS smtp_candidate_submissions(
    message_id INTEGER PRIMARY KEY,
    submission_key TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    created_day TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RESERVED','ACCEPTED','REJECTED','UNKNOWN','HELD')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)'''


class SubmissionHeldError(ValueError):
    """A review gate failed; no provider submission is authorized."""


@dataclass(frozen=True)
class Envelope:
    recipient: str
    content_hash: str
    submission_key: str
    wire: bytes


def prepare(message_id, recipient, body):
    """Render a single-recipient plain-text message; does not approve or send."""
    if type(message_id) is not int or message_id < 1:
        raise SubmissionHeldError('invalid_message_id')
    if (not isinstance(recipient, str) or any(c in recipient for c in '\r\n\x00<>,;')
            or recipient != recipient.strip()):
        raise SubmissionHeldError('invalid_recipient')
    try:
        address = validate_email(recipient, check_deliverability=False)
    except ValueError:
        raise SubmissionHeldError('invalid_recipient') from None
    if not address.ascii_email:
        raise SubmissionHeldError('smtp_utf8_recipient_not_supported')
    if (not isinstance(body, str) or len(body.encode()) > MAX_BODY_BYTES
            or '\x00' in body or '\r' in body or not body.startswith('Subject: ')):
        raise SubmissionHeldError('invalid_draft_format')
    header, separator, text = body.partition('\n\n')
    subject = header.removeprefix('Subject: ')
    if not separator or not text.strip() or not subject.strip() or '\n' in header:
        raise SubmissionHeldError('invalid_draft_format')
    digest = core.digest(recipient, body)
    key = hashlib.sha256(f'{SENDER}|{message_id}|{digest}'.encode()).hexdigest()
    message = EmailMessage(policy=SMTP)
    message['From'] = SENDER
    message['To'] = address.ascii_email
    message['Subject'] = subject
    message['Message-ID'] = f'<wa-{key}@gmail.com>'
    message.set_content(text, subtype='plain', charset='utf-8')
    return Envelope(address.ascii_email, digest, key, message.as_bytes())


def _policy():
    # Do not add an override flag: the production loader itself must first be
    # separately reviewed to admit a live provider. It currently cannot do so.
    config = mm_transport.load_config()
    if (config.get('provider') != 'gmail' or config.get('enabled') is not True
            or config.get('external_send_allowed') is not True
            or type(config.get('daily_cap')) is not int
            or not 1 <= config['daily_cap'] <= 10
            or not all(config.get(k) is True for k in (
                'requires_exact_approval', 'requires_verified_recipient',
                'requires_suppression_check'))):
        raise SubmissionHeldError('live_transport_not_approved')
    return config


def _approved_envelope(db, message_id):
    result = readiness.inspect_message(db, message_id)
    if result['message_ready_for_transport_review'] is not True:
        raise SubmissionHeldError('current_message_gates_failed')
    row = db.execute('SELECT recipient,body FROM mm_messages WHERE id=?', (message_id,)).fetchone()
    envelope = prepare(message_id, row['recipient'], row['body'])
    if envelope.content_hash != result['content_hash']:
        raise SubmissionHeldError('draft_changed_during_review')
    return envelope


def _reserve(db, message_id, envelope, cap):
    db.execute(DDL)
    timestamp = core.now()
    db.execute('BEGIN IMMEDIATE')
    try:
        if db.execute('SELECT 1 FROM smtp_candidate_submissions WHERE message_id=?',
                      (message_id,)).fetchone():
            raise SubmissionHeldError('prior_submission_requires_reconciliation')
        used = db.execute('SELECT count(*) FROM smtp_candidate_submissions WHERE created_day=?',
                          (timestamp[:10],)).fetchone()[0]
        if used >= cap:
            raise SubmissionHeldError('daily_cap_reserved')
        db.execute('INSERT INTO smtp_candidate_submissions VALUES(?,?,?,?,?,?,?)',
                   (message_id, envelope.submission_key, envelope.content_hash,
                    timestamp[:10], 'RESERVED', timestamp, timestamp))
        db.commit()  # Persist the claim before any possible provider action.
    except Exception:
        db.rollback()
        raise


def submit(db, message_id, *, password_loader, smtp_factory=smtplib.SMTP):
    """Candidate only: one claimed attempt, with ambiguity held for reconciliation.

    No automatic retry. A stable Message-ID is a correlation key, not provider
    idempotency. ACCEPTED means SMTP acceptance, never proof of inbox delivery.
    A crash leaves RESERVED committed and blocks a second attempt.
    """
    config = _policy()  # Current real configuration stops here, without writes.
    if db.in_transaction:
        raise SubmissionHeldError('caller_transaction_must_be_closed')
    db.execute('BEGIN IMMEDIATE')
    try:
        envelope = _approved_envelope(db, message_id)
    finally:
        db.rollback()
    _reserve(db, message_id, envelope, config['daily_cap'])
    outcome, attempted = 'HELD', False
    try:
        password = password_loader(SENDER)
        with smtp_factory('smtp.gmail.com', 587, timeout=20) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(SENDER, password)
            # Freeze decisions while rechecking immediately before submission.
            # Concurrent rejection/suppression writers serialize at this point.
            db.execute('BEGIN IMMEDIATE')
            current = _approved_envelope(db, message_id)
            if current != envelope or _policy() != config:
                raise SubmissionHeldError('message_or_policy_changed_before_submission')
            attempted = True
            refused = client.sendmail(SENDER, [envelope.recipient], envelope.wire)
            outcome = 'REJECTED' if refused else 'ACCEPTED'
    except Exception:
        # Never log provider errors, which may contain credentials or content.
        if outcome != 'ACCEPTED':
            outcome = 'UNKNOWN' if attempted else 'HELD'
    finally:
        db.rollback()
    # If persistence fails after SMTP acceptance, RESERVED remains durable and
    # prevents replay. The operator must reconcile against the provider.
    db.execute('UPDATE smtp_candidate_submissions SET status=?,updated_at=? WHERE message_id=?',
               (outcome, core.now(), message_id))
    db.commit()
    return {'status': outcome, 'submission_key': envelope.submission_key,
            'provider_submission_attempted': attempted,
            'delivery_confirmed': False, 'automatic_retry': False}
