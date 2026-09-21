"""Release gate: regression suite, real shadow precision, integrity and rollback.

All test writes are to disposable snapshots. --promote changes only email_policy
after the exact code/fixtures pass. It never creates approvals or advances CRM.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings

import mm_core as c
import mm_email as e
import mm_email_store as store
from email_benchmark import compare, write_report
from mm_email_network import atomic_json

MM_DIR=Path(__file__).resolve().parent
ROOT=MM_DIR.parent
BACKUP=ROOT/'backups/pre_email_finder_v2_20260908T022750Z'
OUT=ROOT/'reports/email-finder-evidence'


def source_fingerprints():
    paths=[]
    for base in ('scripts','config'):
        paths.extend(
            p for p in (MM_DIR/base).rglob('*')
            if p.is_file() and p.name!='.DS_Store'
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc',)
        )
    paths.extend(MM_DIR.glob('test_*.py'))
    paths.extend(MM_DIR.glob('*.sql'))
    paths.extend(MM_DIR/p for p in ('mm','Daily Operator.command','requirements-email.txt'))
    return {str(p.relative_to(ROOT)):c.sha(p.read_bytes()) for p in sorted(set(paths))}


def historical_fingerprints(d):
    baseline=json.loads((OUT/'baseline-db.json').read_text());now={}
    for table in baseline['tables']:
        rows=d.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
        now[table]={'count':len(rows),'hash':c.sha(json.dumps([tuple(r) for r in rows],ensure_ascii=True))}
    return now


def check_history(d):
    baseline=json.loads((OUT/'baseline-db.json').read_text())
    changed=[k for k,v in historical_fingerprints(d).items() if v!=baseline['tables'][k]]
    triggers=dict(d.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
    missing_or_changed=[k for k,v in baseline['triggers'].items() if triggers.get(k)!=v]
    return {'all_33_historical_tables_unchanged':not changed,'changed_tables':changed,
            'all_39_original_triggers_preserved':not missing_or_changed,'changed_triggers':missing_or_changed,
            'integrity':d.execute('PRAGMA integrity_check').fetchone()[0],
            'foreign_key_errors':[list(x) for x in d.execute('PRAGMA foreign_key_check')],
            'verified_sends':d.execute('SELECT count(*) FROM mm_messages WHERE sent_at IS NOT NULL').fetchone()[0],
            'approvals':d.execute('SELECT count(*) FROM mm_messages WHERE approved_hash IS NOT NULL').fetchone()[0]}


def rollback_proof():
    manifest=json.loads((BACKUP/'manifest.json').read_text())
    for item in manifest['items']:
        if c.sha(Path(item['path']).read_bytes())!=item['sha256']:raise ValueError('Backup hash mismatch')
    with tempfile.TemporaryDirectory(prefix='email-rollback-') as temp:
        restored=Path(temp)
        with tarfile.open(BACKUP/'workspace.tgz') as archive:archive.extractall(restored,filter='data')
        hashes=json.loads((BACKUP/'source-hashes.json').read_text())
        mismatches=[p for p,h in hashes.items() if not (restored/p).is_file() or c.sha((restored/p).read_bytes())!=h]
        if mismatches:raise ValueError('Restored source/config mismatch')
        databases={}
        for relative in ('database/money_machine.db','data/n8n/database.sqlite'):
            dest=restored/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            with contextlib.closing(sqlite3.connect('file:'+str(BACKUP/relative)+'?mode=ro&immutable=1',uri=True)) as src,contextlib.closing(sqlite3.connect(dest)) as dst:
                src.backup(dst);databases[relative]=dst.execute('PRAGMA integrity_check').fetchone()[0]
        with contextlib.closing(c.connect(restored/'database/money_machine.db',readonly=True)) as db:
            restored_history=check_history(db)
        # Execute only the restored read-only operator status, never retired seed,
        # approval/send or model commands. No network is needed by the old code.
        env={**os.environ,'MM_ROOT':str(restored),'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,str(restored/'scripts/mm_operator.py'),'status'],env=env,capture_output=True,text=True,timeout=30)
        status=json.loads(result.stdout) if result.returncode==0 else {}
        if result.returncode or status.get('external_sends')!=0:raise ValueError('Restored V1 status failed')
        return {'passed':not mismatches and all(x=='ok' for x in databases.values()) and restored_history['all_33_historical_tables_unchanged'] and restored_history['all_39_original_triggers_preserved'],
                'source_config_report_test_files_restored':len(hashes),'database_integrity':databases,
                'restored_v1_status_exit':result.returncode,'restored_v1_external_sends':status['external_sends'],
                'historical_tables_and_triggers_exact':restored_history,'safe_switch_test':'test_safe_rollback_switch_retains_history_and_holds_approval',
                'restoration_scope':'Disposable directory only; live code/config/DB not rolled back','backup':str(BACKUP)}


def secret_scan():
    # Compare actual local .env values without printing them. Also scan new task
    # reports for common credential formats. Report only paths/counts on failure.
    values=[]
    env=ROOT/'.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                value=line.split('=',1)[1].strip().strip('"\'')
                if len(value)>=8 and not value.startswith(('${','http://','https://')):values.append(value)
    paths=list(OUT.glob('*.json'))+list(OUT.glob('*.txt'))
    paths.extend(p for p in (ROOT/'reports').glob('*') if p.is_file() and p.name.startswith(('EMAIL_FINDER_','CODEX_EMAIL_FINDER_','MONEYMACHINE_POLISH_')))
    bad=[]
    for p in paths:
        text=p.read_text(errors='replace')
        if any(value in text for value in values) or re.search(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})',text):bad.append(str(p.relative_to(ROOT)))
    return {'passed':not bad,'files_scanned':len(paths),'flagged_paths':bad,'secret_values_printed':0}


def run(promote=False):
    OUT.mkdir(parents=True,exist_ok=True)
    before=source_fingerprints()
    sys.path.insert(0,str(MM_DIR))
    warnings.filterwarnings('ignore',category=ResourceWarning)
    suite=unittest.defaultTestLoader.discover(str(MM_DIR), pattern='test_*.py')
    log=io.StringIO();test_result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (OUT/'tests-final.txt').write_text(log.getvalue())
    tests={'run':test_result.testsRun,'passed':test_result.testsRun-len(test_result.failures)-len(test_result.errors)-len(test_result.skipped),
           'failures':len(test_result.failures),'errors':len(test_result.errors),'skipped':[{'test':str(t),'reason':reason} for t,reason in test_result.skipped]}
    comparison=compare(dt.datetime.now(e.UTC));write_report(comparison);m=comparison['metrics']
    rollback=rollback_proof();atomic_json(OUT/'rollback-tested.json',rollback)
    with contextlib.closing(c.connect(readonly=True)) as d:history=check_history(d)
    scan=secret_scan()
    unchanged=before==source_fingerprints()
    # Existing skips are unrelated historical/provider reconciliation, never new
    # email tests. Zero selected/high contacts does not vacuously pass precision.
    allowed_skips=all('test_11_' in x['test'] or 'test_44_' in x['test'] for x in tests['skipped'])
    gates={'regressions':test_result.wasSuccessful() and allowed_skips,
           'verified_high_precision_gte_95pct':m['true_positive']>0 and m['precision']>=.95 and m['false_positive']==0,
           'no_unsupported_guesses':m['unsupported_guesses_promoted']==0,
           'zero_new_outreach_and_approvals':history['verified_sends']==0 and history['approvals']==0 and history['all_33_historical_tables_unchanged'],
           'human_send_and_suppression_guards_preserved':history['all_39_original_triggers_preserved'],
           'db_integrity':history['integrity']=='ok' and not history['foreign_key_errors'],
           'no_secret_values_in_task_reports':scan['passed'],'rollback_tested':rollback['passed'],
           'tested_source_unchanged':unchanged,'zero_model_calls':m['model_calls']==0 and m['paid_inference_cost']==0}
    passed=all(gates.values())
    result={'generated_at':e.utcnow(),'passed':passed,'gates':gates,'tests':tests,'metrics':m,'history':history,'secrets':scan,
            'rollback':rollback,'source_fingerprints':before,'benchmark_hash':c.sha(json.dumps(comparison,sort_keys=True)),
            'promoted':False,'limitations':comparison['limitations']}
    atomic_json(OUT/'acceptance.json',result)
    if promote:
        if not passed:raise ValueError('Acceptance failed; promotion blocked')
        with contextlib.closing(c.connect()) as d,d:
            if not store.installed(d):raise ValueError('Migrate/persist shadow before promotion')
            if d.execute('SELECT count(*) FROM email_shadow_runs').fetchone()[0]<1:raise ValueError('Persisted shadow run required')
            # All runtime selections must come from the tested shadow checks.
            selected=d.execute('SELECT count(*) FROM email_current_high').fetchone()[0]
            if selected!=m['selected_email_count']:raise ValueError('Live selected count differs from tested shadow')
            digest=c.sha((OUT/'acceptance.json').read_bytes())
            # Preserve the exact approved artifact even when a later acceptance
            # run replaces the convenient latest-result filename.
            (OUT/('acceptance-'+digest+'.json')).write_bytes((OUT/'acceptance.json').read_bytes())
            d.execute("UPDATE email_policy SET mode='v2',changed_at=?,acceptance_hash=? WHERE id=1",(c.now(),digest))
        result['promoted']=True
        # Keep the approved gate artifact immutable; promotion receipt is separate.
        atomic_json(OUT/'promotion.json',{'promoted_at':e.utcnow(),'acceptance_sha256':digest,'mode':'v2','external_sends':0,'approvals_created':0})
    precision_text=f"{m['precision']:.1%}" if m['precision'] is not None else 'undefined (no current high contacts)'
    interval=m.get('precision_95pct_wilson_interval')
    interval_text=f'{interval[0]:.1%}–{interval[1]:.1%}' if interval else 'undefined (no current high contacts)'
    lines=['# Email finder acceptance results','','Status: **'+('PASS' if passed else 'FAIL')+'**'+(' — V2 promoted' if result['promoted'] else ' — rollout not promoted by this run'),'',
           f"Tests: {tests['run']} run; {tests['passed']} passed; {tests['failures']} failures; {tests['errors']} errors; {len(tests['skipped'])} pre-existing skips.",'',
           f"VERIFIED_HIGH public-attribution precision: {m['true_positive']}/{m['verified_high']} = {precision_text}. Selected businesses: {m['selected_email_count']}. Eligible-public-email recall: {m['recall_eligible_public_emails']:.1%}.",
           '',f"95% Wilson precision interval: {interval_text}. This small benchmark does not prove 95% population precision or mailbox delivery.",'',
           '| Acceptance gate | Result |','|---|---|',*[f"| {k} | {'PASS' if v else 'FAIL'} |" for k,v in gates.items()],
           '', 'All 33 historical tables and 39 pre-existing triggers compared to pre-change snapshot. New email tables are additive. No CRM stage, suppression, historical send or approval record changed.', '',
           'Synthetic SMTP/catch-all, invalid mailbox, hard rejection, vendor, directory, form-only, duplicate, redirect, free-mail and named-person regressions are in the test log; they are not counted as real businesses.', '',
           '## Existing skips', '', *['- '+x['reason'] for x in tests['skipped']], '', '## Evidence', '',
           '- `email-finder-evidence/acceptance.json`: machine-readable gate results and tested source hashes.',
           '- `email-finder-evidence/tests-final.txt`: full pass/fail output.',
           '- `email-finder-evidence/rollback-tested.json`: actual source/config/DB restoration proof.',
           '- `EMAIL_FINDER_METRICS.json`: raw comparison, measured metrics and provenance.', '',
           'No scaling performed. SMTP probing is disabled; unknown catch-all status is never reported as NO. No independent mailbox delivery tests or provider billing reconciliation were performed.']
    (ROOT/'reports/EMAIL_FINDER_ACCEPTANCE_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'passed':passed,'gates':gates,'tests':tests,'precision':m['precision'],'promoted':result['promoted']},indent=2))
    return 0 if passed else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--promote',action='store_true');a=p.parse_args()
    try:sys.exit(run(a.promote))
    except (ValueError,OSError,sqlite3.Error) as ex:print('BLOCKED: '+str(ex),file=sys.stderr);sys.exit(2)
