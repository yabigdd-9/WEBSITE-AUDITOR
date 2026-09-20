"""Transactional history; old runs and their evidence are immutable."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

STATES = {'detected', 'acknowledged', 'scheduled', 'in_progress', 'patched', 'verified',
          'regressed', 'accepted_risk', 'false_positive'}


def finding_id(finding):
    key = [finding.get('check'), finding.get('defect_key'), finding.get('source_url'),
           finding.get('selector', '')]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]


class History:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'history.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 1:
                raise ValueError('History schema is newer than this toolkit')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, url TEXT, timestamp TEXT, report TEXT);
            CREATE TABLE IF NOT EXISTS remediations(id TEXT PRIMARY KEY, state TEXT, metadata TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT, payload TEXT);
            PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self, query='', limit=100):
        with self.connect() as db:
            rows = db.execute('SELECT report FROM runs WHERE url LIKE ? ORDER BY timestamp DESC LIMIT ?',
                              ('%' + query + '%', min(max(limit, 1), 1000))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT report FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def compare(self, report):
        previous = [r for r in self.list(report['url'], 1000) if r['url'] == report['url']]
        # A partial scan cannot establish resolution or a regression baseline.
        baseline = next((r for r in previous if r['status'] == 'complete' and
                         r['profile'] == report['profile']), None)
        current = {d['finding_id'] for d in report['defects']}
        old = {d['finding_id'] for d in baseline['defects']} if baseline else set()
        historic = {d['finding_id'] for r in previous if r['status'] == 'complete'
                    for d in r['defects']}
        return {'baseline': baseline['run_id'] if baseline else None,
                'new': sorted(current - old - historic), 'persistent': sorted(current & old),
                'regressed': sorted((current - old) & historic),
                'resolved': sorted(old - current) if report['status'] == 'complete' else [],
                'resolution_assessed': report['status'] == 'complete' and baseline is not None}

    def save(self, report):
        with self.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?)',
                       (report['run_id'], report['url'], report['timestamp'], json.dumps(report)))
            for d in report['defects']:
                db.execute('INSERT OR IGNORE INTO remediations VALUES(?,?,?)',
                           (d['finding_id'], 'detected', '{}'))

    def transition(self, identity, state, metadata=None):
        if state not in STATES:
            raise ValueError('Unknown remediation state')
        metadata = metadata or {}
        if state == 'verified':
            run = self.get(metadata.get('verification_run', ''))
            if run['status'] != 'complete' or any(d['finding_id'] == identity for d in run['defects']):
                raise ValueError('Verification needs a complete run without the finding')
            with self.connect() as db:
                originals = [json.loads(r[0]) for r in db.execute('SELECT report FROM runs')]
            if not any(r['url'] == run['url'] and r['profile'] == run['profile'] and
                       r['timestamp'] < run['timestamp'] and
                       any(d['finding_id'] == identity for d in r['defects']) for r in originals):
                raise ValueError('Verification must cover the same site and profile after detection')
        with self.connect() as db:
            if db.execute('UPDATE remediations SET state=?, metadata=? WHERE id=?',
                          (state, json.dumps(metadata), identity)).rowcount != 1:
                raise KeyError(identity)
            db.execute('INSERT INTO events(kind,payload) VALUES(?,?)',
                       ('remediation', json.dumps({'id': identity, 'state': state, **metadata})))

    def artifact(self, run_id, kind):
        report = self.get(run_id)
        path = Path(report['artifacts'][kind]).resolve()
        run_dir = self.root / run_id
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise ValueError('Unregistered artifact path')
        expected = report.get('manifest', {}).get(kind, {}).get('sha256')
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Artifact integrity check failed')
        return path
