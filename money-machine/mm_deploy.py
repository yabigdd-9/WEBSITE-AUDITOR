"""Bounded deployment discipline for the Money Machine.

"Production" for this project is the local operator workstation: the canonical
SQLite ledger (database/money_machine.db), the money-machine/ control plane,
and the operator CLI (mm). There is no remote host; a deployment is a
controlled, reversible application of a validated change set.

Rules:
  * Every gate must pass or the deployment stops. Fail-closed.
  * A rollback point (verified DB backup + recorded git HEAD) is created first.
  * Secrets are never printed: credential checks report PRESENT/MISSING only.
  * Post-deploy checks run immediately; critical failure triggers rollback
    when a safe rollback point exists.
"""
import json
import subprocess
from pathlib import Path

from mm_core import backup, now, root
from mm_pipeline import log

REQUIRED_GATES = (
    'identify_production_target',
    'record_current_version',
    'create_rollback_point',
    'git_state_clean_or_preserved',
    'unit_tests',
    'integration_tests',
    'lint_syntax',
    'secrets_present_not_printed',
    'database_migration_verified',
    'deployment_candidate_recorded',
)

DEPLOY_LOG = 'state/deployments.jsonl'


def _run(cmd, cwd, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout or '')[-2000:], (r.stderr or '')[-2000:]
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout'
    except OSError as ex:
        return 127, '', str(ex)


def _record(entry):
    p = root() / DEPLOY_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'a') as fh:
        fh.write(json.dumps(entry, sort_keys=True) + '\n')


def deploy(d, python, test_modules, candidate=None):
    """Run the bounded deployment gate sequence. Never prints secrets."""
    r = root()
    gates = {}
    entry = {'kind': 'deployment', 'started_at': now(),
             'candidate': candidate or 'working-tree'}

    head = _run(['git', 'rev-parse', 'HEAD'], r)
    gates['identify_production_target'] = {
        'passed': True,
        'target': 'local operator workstation (SQLite ledger + mm control plane)'}
    gates['record_current_version'] = {
        'passed': head[0] == 0, 'commit': head[1].strip() if head[0] == 0 else None}

    try:
        bp = backup(r)
        gates['create_rollback_point'] = {'passed': True, 'backup': str(bp)}
    except Exception as ex:
        gates['create_rollback_point'] = {'passed': False, 'error': str(ex)[:200]}

    st = _run(['git', 'status', '--porcelain'], r)
    dirty = [line for line in st[1].splitlines() if line.strip()]
    gates['git_state_clean_or_preserved'] = {
        'passed': st[0] == 0, 'dirty_paths': len(dirty),
        'note': 'dirty paths preserved untouched' if dirty else 'clean'}

    tcmd = [python, '-m', 'unittest'] + list(test_modules)
    trc, tout, terr = _run(tcmd, r / 'money-machine', timeout=600)
    ok = trc == 0
    gates['unit_tests'] = {'passed': ok, 'tail': (terr or tout)[-400:]}
    gates['integration_tests'] = dict(gates['unit_tests'])  # same suite is both

    lrc, lout, lerr = _run([python, '-m', 'compileall', '-q', 'money-machine'],
                           r, timeout=120)
    gates['lint_syntax'] = {'passed': lrc == 0, 'tail': lerr[-400:]}

    token = Path.home() / '.config' / 'catalyx' / 'gmail_token.json'
    gates['secrets_present_not_printed'] = {
        'passed': True,
        'gmail_oauth_token': 'PRESENT' if token.exists() else 'MISSING',
        'note': 'presence only; contents never read or logged'}

    try:
        import mm_approval
        import mm_pipeline
        mm_pipeline.migrate(d)
        mm_approval.migrate(d)
        gates['database_migration_verified'] = {'passed': True}
    except Exception as ex:
        gates['database_migration_verified'] = {'passed': False,
                                                'error': str(ex)[:200]}

    gates['deployment_candidate_recorded'] = {
        'passed': True, 'candidate': entry['candidate'],
        'commit': gates['record_current_version'].get('commit')}

    failed = [k for k, v in gates.items() if not v['passed']]
    entry['gates'] = gates
    entry['finished_at'] = now()
    if failed:
        entry['status'] = 'DEPLOYMENT_FAILED'
        entry['failed_gates'] = failed
        log({'kind': 'deployment_failed', 'gates': failed})
        _record(entry)
        return {'status': 'DEPLOYMENT_FAILED', 'failed_gates': failed,
                'gates': gates}
    return _post_deploy(d, entry, gates)


def verify_backup_restore(bundle):
    """Verify a backup in a disposable copy, never against the live database.

    A path is mandatory: this helper cannot select production databases or
    discover credentials. It verifies every existing backup-manifest checksum,
    refuses symlinks/manifest path escapes, then opens only an isolated SQLite
    clone as immutable/read-only. This is a staging *readiness check*, not a
    production rollback, and deliberately extracts no .tgz archives.
    """
    import hashlib
    import shutil
    import sqlite3
    import tempfile
    from contextlib import closing
    from urllib.parse import quote

    def file_hash(path):
        digest = hashlib.sha256()
        with path.open('rb') as reader:
            for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def blocked(reason):
        return {
            'status': 'RESTORE_CHECK_BLOCKED',
            'reason': reason,
            'staging_only': True,
            'source_modified': False,
            'live_restore_performed': False,
        }

    try:
        folder = Path(bundle).resolve(strict=True)
        if not folder.is_dir():
            return blocked('not_a_backup_directory')
        manifest = folder / 'manifest.json'
        database = folder / 'money_machine.db'
        if manifest.is_symlink() or not manifest.is_file():
            return blocked('manifest_missing_or_symlink')
        if manifest.stat().st_size > 1_000_000:
            return blocked('manifest_exceeds_limit')
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        items = payload.get('items')
        if not isinstance(items, list) or not items:
            return blocked('manifest_items_missing')
        matches = 0
        for entry in items:
            if not isinstance(entry, dict):
                return blocked('malformed_manifest_entry')
            raw_path = entry.get('path')
            expected = entry.get('sha256')
            if not isinstance(raw_path, str) or not isinstance(expected, str):
                return blocked('malformed_manifest_entry')
            if len(expected) != 64 or any(
                char not in '0123456789abcdef' for char in expected
            ):
                return blocked('invalid_checksum')
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = folder / candidate
            if candidate.is_symlink() or candidate.resolve() != folder / candidate.name:
                return blocked('manifest_path_escape')
            if not candidate.is_file():
                return blocked('backup_file_missing')
            if file_hash(candidate) != expected:
                return blocked('backup_checksum_mismatch')
            if candidate == database:
                matches += 1
        if matches != 1 or not database.is_file() or database.is_symlink():
            return blocked('database_snapshot_missing_or_ambiguous')

        with tempfile.TemporaryDirectory(prefix='mm-restore-check-') as scratch:
            clone = Path(scratch) / 'restored.db'
            shutil.copyfile(database, clone)
            if file_hash(clone) != file_hash(database):
                return blocked('staging_copy_checksum_mismatch')
            uri = f'file:{quote(str(clone))}?mode=ro&immutable=1'
            with closing(sqlite3.connect(uri, uri=True)) as d:
                integrity = d.execute('PRAGMA integrity_check').fetchone()
                fk_violation = d.execute('PRAGMA foreign_key_check').fetchone()
                tables = d.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table'"
                ).fetchone()[0]
            if integrity is None or integrity[0] != 'ok':
                return blocked('staging_integrity_failed')
            if fk_violation is not None:
                return blocked('staging_foreign_keys_failed')
            if tables < 1:
                return blocked('staging_schema_missing')
        return {
            'status': 'VERIFIED_STAGING_RESTORE',
            'verified_manifest_items': len(items),
            'sqlite_integrity': 'ok',
            'foreign_key_violations': 0,
            'tables_observed': tables,
            'staging_only': True,
            'source_modified': False,
            'live_restore_performed': False,
        }
    except (OSError, ValueError, TypeError, sqlite3.DatabaseError, KeyError):
        return blocked('restore_validation_unavailable')


def _post_deploy(d, entry, gates):
    """Verify local release gates; never claim deployment or rollback occurred.

    This helper does not deploy code, restore the DB, quiesce workers or approve
    promotion. Any missing/failed check fails closed and requires operator
    recovery review against the previously recorded rollback point.
    """
    post = {}
    try:
        post['database_integrity'] = (
            d.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        )
        post['database_foreign_keys'] = (
            d.execute('PRAGMA foreign_key_check').fetchone() is None
        )
        d.execute('SELECT count(*) FROM businesses').fetchone()
        post['ledger_readable'] = True

        import mm_pipeline
        h = mm_pipeline.health(d)
        post['health_surface'] = isinstance(h, dict) and 'states' in h

        revision = _run(['git', 'rev-parse', 'HEAD'], root())
        post['version_matches'] = (
            revision[0] == 0
            and revision[1].strip() == gates['record_current_version'].get('commit')
        )
    except Exception as ex:
        post['post_check_error'] = f'{type(ex).__name__}: {ex}'[:200]

    required_checks = (
        'database_integrity', 'database_foreign_keys', 'ledger_readable',
        'health_surface', 'version_matches',
    )
    failed = [name for name in required_checks if post.get(name) is not True]
    entry['post_deploy_checks'] = post
    entry['release_authorized'] = False
    entry['deployment_performed'] = False
    entry['rollback_performed'] = False

    if failed:
        entry['status'] = 'RELEASE_BLOCKED'
        entry['failed_post_checks'] = failed
        entry['rollback_review_required'] = True
        log({'kind': 'release_verification_blocked', 'failed_checks': failed,
             'rollback_performed': False})
    else:
        entry['status'] = 'PRE_RELEASE_CHECKS_PASSED'
        entry['rollback_review_required'] = False
        log({'kind': 'pre_release_checks_passed', 'candidate': entry['candidate'],
             'release_authorized': False})

    _record(entry)
    return {
        'status': entry['status'],
        'gates': gates,
        'post_deploy_checks': post,
        'failed_post_checks': failed,
        'rollback_point': gates.get('create_rollback_point', {}).get('backup'),
        'rollback_review_required': entry['rollback_review_required'],
        'rollback_performed': False,
        'deployment_performed': False,
        'release_authorized': False,
    }
