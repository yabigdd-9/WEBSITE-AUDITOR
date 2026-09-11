"""Append-only email provenance, migrations, current-selection gate and status."""
import json
import contextlib
import copy
from pathlib import Path
import sqlite3

import mm_core as core
import mm_email as engine


def installed(d):
    return bool(d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='email_policy'").fetchone())


def _migrate_v3(d, backup_path, sql_path=None):
    backup_path = Path(backup_path)
    manifest = json.loads((backup_path / 'manifest.json').read_text())
    if not manifest.get('items'): raise ValueError('Nonempty verified backup manifest required')
    has_database = False
    for item in manifest['items']:
        p = Path(item.get('path', item.get('backup', '')))
        if not p.is_file() or core.sha(p.read_bytes()) != item['sha256']: raise ValueError('Backup checksum mismatch')
        if p.name == 'money_machine.db':
            with contextlib.closing(sqlite3.connect('file:' + str(p) + '?mode=ro&immutable=1', uri=True)) as check:
                if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Backup DB integrity failed')
            has_database = True
    if not has_database: raise ValueError('MoneyMachine DB backup required')
    path = Path(sql_path or Path(__file__).resolve().parents[1] / 'migrations/003_email_finder_v2.sql')
    sql = path.read_text(); sql_hash = core.sha(sql)
    if installed(d):
        row = d.execute('SELECT * FROM email_schema_migrations WHERE version=3').fetchone()
        if not row or row['sql_hash'] != sql_hash: raise ValueError('Migration version/checksum conflict')
        return {'applied': False, 'version': 3}
    if d.in_transaction: raise ValueError('Migration requires its own transaction')
    try:
        d.executescript('BEGIN IMMEDIATE;\n' + sql)
        # Raw legacy records remain unchanged, including standalone suppressions.
        for row in d.execute('SELECT * FROM contacts').fetchall():
            raw = row['address_or_channel'] or ''
            if '@' not in raw: continue
            blocked = bool(row['do_not_contact']) or is_suppressed(d, row['business_id'], raw)
            d.execute('INSERT INTO email_candidates(prospect_id,email,normalized_email,source_type,source_url,source_excerpt,observed_at,candidate_method,status,legacy_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (row['business_id'], raw, engine.normalize_email(raw)[0], 'legacy_contact', None,
                       'Legacy source label: ' + (row['source'] or 'unknown'), row['last_verified'], 'legacy_import',
                       'SUPPRESSED' if blocked else 'UNVERIFIED', 'contacts:' + str(row['id']), core.now()))
        for row in d.execute('SELECT * FROM mm_contact_evidence').fetchall():
            raw = row['recipient']; blocked = is_suppressed(d, row['business_id'], raw)
            d.execute('INSERT INTO email_candidates(prospect_id,email,normalized_email,source_type,source_url,source_excerpt,observed_at,candidate_method,status,legacy_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (row['business_id'], raw, engine.normalize_email(raw)[0], 'legacy_capture', row['source_url'],
                       'Legacy fixed confidence is not email verification', row['checked_at'], 'legacy_import',
                       'SUPPRESSED' if blocked else 'UNVERIFIED', 'mm_contact_evidence:' + str(row['id']), core.now()))
        d.execute('INSERT INTO email_schema_migrations VALUES(3,?,?,?)', (core.now(), str(backup_path), sql_hash))
        if d.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Foreign key check failed')
        d.commit()
    except Exception:
        d.rollback(); raise
    return {'applied': True, 'version': 3, 'mode': 'shadow'}


def _migrate_v4(d, backup_path, sql_path=None):
    result = _migrate_v3(d, backup_path, sql_path)
    path = Path(__file__).resolve().parents[1] / 'migrations/004_email_hardening.sql'
    sql = path.read_text(); digest = core.sha(sql)
    row = d.execute('SELECT sql_hash FROM email_schema_migrations WHERE version=4').fetchone()
    if row:
        if row[0] != digest: raise ValueError('Migration version/checksum conflict')
        return {'applied': result['applied'], 'version': 4}
    if d.in_transaction: raise ValueError('Migration requires its own transaction')
    try:
        d.executescript('BEGIN IMMEDIATE;\n' + sql)
        d.execute('INSERT INTO email_schema_migrations VALUES(4,?,?,?)', (core.now(), str(backup_path), digest))
        if d.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Foreign key check failed')
        d.commit()
    except Exception:
        d.rollback(); raise
    return {'applied': True, 'version': 4, 'mode': 'POST_DEPLOYMENT_OBSERVATION'}


def migrate_email(d, backup_path, sql_path=None):
    result = _migrate_v4(d, backup_path, sql_path)
    path = Path(__file__).resolve().parents[1] / 'migrations/005_email_receipt_format.sql'
    sql = path.read_text(); digest = core.sha(sql)
    row = d.execute('SELECT sql_hash FROM email_schema_migrations WHERE version=5').fetchone()
    if row:
        if row[0] != digest: raise ValueError('Migration version/checksum conflict')
        return {'applied': result['applied'], 'version': 5}
    if d.in_transaction: raise ValueError('Migration requires its own transaction')
    try:
        d.executescript('BEGIN IMMEDIATE;\n' + sql)
        d.execute('INSERT INTO email_schema_migrations VALUES(5,?,?,?)', (core.now(), str(backup_path), digest))
        d.commit()
    except Exception:
        d.rollback(); raise
    return {'applied': True, 'version': 5, 'mode': 'POST_DEPLOYMENT_OBSERVATION'}


def require_production_persistence(d):
    table = d.execute("SELECT 1 FROM sqlite_master WHERE name='email_release_policy'").fetchone()
    row = d.execute('SELECT mode,verifier_version FROM email_release_policy WHERE id=1').fetchone() if table else None
    if not row or row[0] != 'PRODUCTION' or row[1] != engine.VERSION:
        raise ValueError('POST_DEPLOYMENT_OBSERVATION: use isolated observation; production email persistence is held')


def is_suppressed(d, bid, address=''):
    if bid is not None:
        if d.execute('SELECT 1 FROM mm_holds WHERE business_id=?', (bid,)).fetchone(): return True
        if d.execute("SELECT 1 FROM mm_deals WHERE business_id=? AND stage='SUPPRESSED'", (bid,)).fetchone(): return True
        if d.execute("SELECT 1 FROM mm_contact_evidence WHERE business_id=? AND lower(trim(recipient))=? AND unsubscribe_state='unsubscribed'", (bid, address.strip().lower())).fetchone(): return True
    return bool(d.execute('SELECT 1 FROM mm_suppression WHERE lower(trim(address))=?', (address.strip().lower(),)).fetchone()
                or d.execute('SELECT 1 FROM contacts WHERE lower(trim(address_or_channel))=? AND do_not_contact=1', (address.strip().lower(),)).fetchone())


def persist(d, result, root=None):
    """Store new checks. This never writes contacts, CRM, messages or approvals."""
    require_production_persistence(d)
    root = Path(root or core.root()); bid = result['business_id']
    core.business(d, bid)
    identity = copy.deepcopy(result['identity'])
    for page in identity['page_evidence']:
        path=Path(page['capture_path'])
        if not path.is_absolute():path=root/path
        if not core.artifact_valid(path,page['capture_hash']):raise ValueError('Identity capture missing/modified before storage')
        page['capture_path']=str(path.resolve())
    identity_json = json.dumps(identity, sort_keys=True)
    iid = d.execute('INSERT INTO email_identity_checks(prospect_id,checked_at,entity_key,result_json,evidence_hash) VALUES(?,?,?,?,?)',
                    (bid, core.now(), identity['entity_key'], identity_json, core.sha(identity_json))).lastrowid
    selected_cid = selected_vid = None; selected_score = None
    for v in result['results']:
        v=copy.deepcopy(v)
        email = v['email']
        # Recheck suppression at persistence time, not just before network IO.
        if is_suppressed(d, bid, email):
            v = {**v, 'confidence_label': 'SUPPRESSED', 'confidence_score': 0,
                 'rejection_reasons': v['rejection_reasons'] + ['Suppression rechecked at persistence']}
        candidate = d.execute('SELECT id FROM email_candidates WHERE prospect_id=? AND normalized_email=? ORDER BY id LIMIT 1', (bid, email)).fetchone()
        if candidate: cid = candidate[0]
        else:
            observation = v['evidence'][0] if v['evidence'] else {}
            cid = d.execute('INSERT INTO email_candidates(prospect_id,email,normalized_email,source_type,source_url,source_excerpt,observed_at,candidate_method,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (bid, observation.get('observed_email', email), email, 'page' if observation else 'legacy_report', observation.get('source_url'),
                             observation.get('context'), observation.get('observed_at'), 'observed' if observation else 'legacy_import',
                             'OBSERVED' if observation else 'UNVERIFIED', core.now())).lastrowid
        prior=d.execute("SELECT 1 FROM email_verifications WHERE candidate_id=? AND smtp_status='rejected' LIMIT 1",(cid,)).fetchone()
        if prior and v['confidence_label']!='SUPPRESSED' and not (v['smtp_result']=='accepted' and v['catch_all_status']=='no'):
            v.update(confidence_label='REJECTED',confidence_score=0,smtp_result='rejected')
            v['rejection_reasons'].append('Unresolved historical SMTP hard rejection; publication alone cannot clear it')
        for observation in v['evidence']:
            path = Path(observation['capture_path'])
            if not path.is_absolute(): path = root / path
            if not core.artifact_valid(path, observation['capture_hash']): raise ValueError('Evidence file missing/modified before storage')
            observation['capture_path']=str(path.resolve())
            d.execute('INSERT OR IGNORE INTO email_evidence(candidate_id,evidence_type,url,title,excerpt,observed_email,captured_at,evidence_hash,capture_path,role) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (cid, observation['method'], observation['source_url'], observation['title'], observation['context'], observation['observed_email'],
                       observation['observed_at'], observation['capture_hash'], str(path.resolve()), observation['role']))
        vid = d.execute('INSERT INTO email_verifications(candidate_id,identity_id,checked_at,syntax_valid,mx_valid,smtp_status,catch_all_status,disposable,business_match,person_match,first_party_observed,confidence_score,confidence_label,rejection_reason,verifier_version,result_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (cid, iid, v['checked_at'], int(v['syntax_valid']), int(v['mx_present']), v['smtp_result'], v['catch_all_status'],
                         int(v['disposable_status'] == 'known_disposable'), int(v['business_match']), str(v['person_match']), int(v['first_party_observed']),
                         v['confidence_score'], v['confidence_label'], json.dumps(v['rejection_reasons']), v['verifier_version'], json.dumps(v, sort_keys=True))).lastrowid
        if result['selected'] and email == result['selected']['email'] and v['confidence_label'] == 'VERIFIED_HIGH':
            selected_cid, selected_vid, selected_score = cid, vid, v['confidence_score']
    d.execute('INSERT INTO prospect_email_state VALUES(?,?,?,?,1,?,?,?,?) ON CONFLICT(prospect_id) DO UPDATE SET best_email_id=excluded.best_email_id,best_verification_id=excluded.best_verification_id,best_email_confidence=excluded.best_email_confidence,email_review_required=1,contact_form_urls=excluded.contact_form_urls,selection_status=excluded.selection_status,last_checked=excluded.last_checked,identity_id=excluded.identity_id',
              (bid, selected_cid, selected_vid, selected_score, json.dumps(result['contact_form_urls']),
               'VERIFIED_HIGH' if selected_cid else 'NO_VERIFIED_EMAIL', core.now(), iid))
    return status(d, bid)


def require_email(d, bid, address):
    if not installed(d): raise ValueError('Email V2 migration and verification required')
    require_production_persistence(d)
    policy = d.execute('SELECT mode FROM email_policy WHERE id=1').fetchone()[0]
    if policy != 'v2': raise ValueError('Email finder is ' + policy + '; verification rollout not enabled')
    core.eligible(d, bid, address)
    found = d.execute('SELECT * FROM email_current_high WHERE prospect_id=? AND lower(normalized_email)=?', (bid, address.strip().lower())).fetchone()
    if not found: raise ValueError('Current selected VERIFIED_HIGH email with provenance required')
    if engine.normalize_email(address)[0]!=found['normalized_email']:raise ValueError('Use the exact published local-part casing of the selected email')
    return found


def status(d, bid):
    b = core.business(d, bid)
    if not installed(d): return {'business': b['name'], 'email': 'NO_VERIFIED_EMAIL', 'mode': 'not_migrated', 'human_review_required': True}
    state = d.execute('SELECT * FROM prospect_email_state WHERE prospect_id=?', (bid,)).fetchone()
    candidates = []
    for c in d.execute('SELECT * FROM email_candidates WHERE prospect_id=? ORDER BY id', (bid,)):
        v = d.execute('SELECT result_json FROM email_verifications WHERE candidate_id=? ORDER BY id DESC LIMIT 1', (c['id'],)).fetchone()
        candidates.append(json.loads(v[0]) if v else {'email': c['normalized_email'], 'confidence_label': c['status'], 'reasons': ['Legacy/unreviewed candidate; no email verification']})
    current = d.execute('SELECT * FROM email_current_high WHERE prospect_id=?', (bid,)).fetchone()
    release = d.execute('SELECT mode,verifier_version FROM email_release_policy WHERE id=1').fetchone() if d.execute("SELECT 1 FROM sqlite_master WHERE name='email_release_policy'").fetchone() else None
    if d.execute('SELECT mode FROM email_policy WHERE id=1').fetchone()[0]=='v1_hold':current=None
    selected = next((v for v in candidates if current and v['email'] == current['normalized_email']), None)
    identity = d.execute('SELECT result_json FROM email_identity_checks WHERE prospect_id=? ORDER BY id DESC LIMIT 1', (bid,)).fetchone()
    outreach_ready = False
    if selected:
        packet = d.execute('SELECT evidence_id FROM mm_messages WHERE business_id=? AND lower(recipient)=lower(?) AND invalidated_reason IS NULL AND sent_at IS NULL ORDER BY id DESC LIMIT 1', (bid, selected['email'])).fetchone()
        outreach_ready = bool(packet and not core.readiness(d, bid, packet[0], selected['email']))
    legacy_mode = d.execute('SELECT mode FROM email_policy WHERE id=1').fetchone()[0]
    return {'business_id': bid, 'business': b['name'], 'website': b['public_website'], 'mode': 'v1_hold' if legacy_mode=='v1_hold' else release['mode'] if release else legacy_mode,
            'verifier_version': release['verifier_version'] if release else engine.VERSION,
            'identity': json.loads(identity[0]) if identity else None, 'email': selected['email'] if selected else 'NO_VERIFIED_EMAIL',
            'confidence': selected['confidence_score'] if selected else None, 'selected': selected, 'candidates': candidates,
            'contact_form_urls': json.loads(state['contact_form_urls']) if state else [], 'last_checked': state['last_checked'] if state else None,
            'human_review_required': True, 'outreach_eligible': outreach_ready, 'next_action': 'Complete independent holdout review; production email finding and outreach remain held' if release and release['mode']=='POST_DEPLOYMENT_OBSERVATION' else 'Human relevance/permission and exact-item approval required' if selected else 'No current verified email; review evidence or use public contact form manually'}


def duplicate_entities(d):
    # Report only: never merge people, branch records, CRM stages or suppression.
    rows = d.execute('SELECT i.prospect_id,i.entity_key,i.result_json FROM email_identity_checks i WHERE i.id=(SELECT max(j.id) FROM email_identity_checks j WHERE j.prospect_id=i.prospect_id)').fetchall()
    groups = {}
    for row in rows:
        data = json.loads(row['result_json'])
        if data['status'] != 'HIGH': continue
        key = (data['canonical_root_domain'], engine.normalize_name(data['physical_location']))
        groups.setdefault(key, []).append(row['prospect_id'])
    return [{'domain': k[0], 'location': k[1], 'business_ids': ids, 'action': 'Manual entity/branch review; nothing merged'} for k, ids in groups.items() if len(ids) > 1]
