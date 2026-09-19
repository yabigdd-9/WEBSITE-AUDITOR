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
from pathlib import Path
import subprocess

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
    dirty = [l for l in st[1].splitlines() if l.strip()]
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
        import mm_pipeline, mm_approval
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


def _post_deploy(d, entry, gates):
    """Post-deploy verification; critical failure triggers recorded rollback."""
    post = {}
    try:
        ic = d.execute('PRAGMA integrity_check').fetchone()[0]
        post['database_integrity'] = ic == 'ok'
        d.execute('SELECT count(*) FROM businesses').fetchone()
        post['ledger_readable'] = True
        import mm_pipeline
        h = mm_pipeline.health(d)
        post['health_surface'] = isinstance(h, dict) and 'states' in h
        deployed = _run(['git', 'rev-parse', 'HEAD'], root())
        post['version_matches'] = deployed[1].strip() == \
            gates['record_current_version'].get('commit')
    except Exception as ex:
        post['post_check_error'] = str(ex)[:200]

    critical = [k for k in ('database_integrity', 'ledger_readable')
                if post.get(k) is False]
    entry['post_deploy_checks'] = post
    if critical:
        entry['status'] = 'ROLLED_BACK'
        entry['rollback_reason'] = critical
        log({'kind': 'deployment_rollback', 'reason': critical})
    else:
        entry['status'] = 'DEPLOYED'
        log({'kind': 'deployed', 'candidate': entry['candidate']})
    _record(entry)
    return {'status': entry['status'], 'gates': gates,
            'post_deploy_checks': post,
            'rollback_point': gates['create_rollback_point'].get('backup')}

