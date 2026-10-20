"""Run candidate tests with isolated state, credential-free env and receipts."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    name, *args = sys.argv[1:]
    evidence = ROOT / 'reports/reliability-review/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    state = ROOT / 'reports/reliability-review/staging' / name
    state.mkdir(parents=True, exist_ok=True)
    # Allowlist prevents provider and mail credentials leaking into child tests.
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG') if k in os.environ}
    env.update(MM_ROOT=str(state), PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / 'money-machine'),
               MM_PYTHON=sys.executable,
               MM_EXTERNAL_SEND_DISABLED='1', ZERO_LLM='1',
               PYTHONPYCACHEPREFIX=str(state / 'fresh-pycache'),
               WA_BROWSER_E2E='1' if name == 'browser' else '0',
               WA_E2E_OUTPUT=str(evidence / 'browser-artifacts'))
    if name.startswith(('money-machine-synthetic', 'acceptance-synthetic')):
        source = state / 'synthetic-source.db'
        if source.exists():
            raise RuntimeError('Use a fresh suite name/state directory')
        with sqlite3.connect(source) as d:
            schema = (ROOT / 'money-machine/database/schema.sql').read_text()
            tables, guards = schema.split('-- Triggers', 1)
            d.executescript(tables)
            # Fixture contract: three historical unverified claims. These are
            # synthetic legacy rows, never transport operations or approvals.
            for _ in range(3):
                d.execute("INSERT INTO outreach(draft,sent_at) VALUES(?,?)",
                          ('SYNTHETIC UNVERIFIED CLAIM; NO MESSAGE SENT', '2000-01-01'))
            d.commit()
            d.executescript(guards)
            assert d.execute('SELECT count(*) FROM businesses').fetchone()[0] == 0
            assert d.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        env['MM_TEST_SOURCE'] = str(source)
    sources = [ROOT / p for p in ('money-machine/mm_pipeline.py', 'money-machine/mm_queue_health.py',
                                 'money-machine/supervisor/cli.py', 'money-machine/supervisor/daemon.py')]
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    before = hashes()
    start = time.monotonic()
    with (evidence / (name + '.txt')).open('w') as out:
        result = subprocess.run([sys.executable, '-m', 'pytest', *args], cwd=ROOT, env=env,
                                stdout=out, stderr=subprocess.STDOUT, timeout=1200)
    receipt = dict(command=['pytest', *args], exit_code=result.returncode,
                   elapsed_seconds=round(time.monotonic()-start, 3), source_hashes=before,
                   changed_during_run=hashes() != before, state_root=str(state),
                   credentials_inherited=False)
    (evidence / (name + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
