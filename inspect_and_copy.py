import sqlite3
import shutil
from pathlib import Path

# Copy fixtures to evidence/heatforce-*.html
src = Path('money-machine/fixtures/email_captures')
dst = Path('evidence')
for i in range(3):
    s = src / f'5-{i}.html'
    d = dst / f'heatforce-{i}.html'
    if not d.exists():
        shutil.copy2(s, d)
        print(f"Copied {s} -> {d}")
    else:
        print(f"Already exists: {d}")

# Inspect DB
d = sqlite3.connect('database/money_machine.db')
d.row_factory = sqlite3.Row

print("\n=== Evidence meta for business 5 ===")
for row in d.execute('SELECT * FROM mm_evidence_meta WHERE evidence_id IN (SELECT id FROM mm_evidence WHERE business_id=5)'):
    print(dict(row))

print("\n=== Table existence ===")
for tbl in ('email_policy', 'email_evidence', 'email_verifications', 'email_candidates'):
    exists = d.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl}'").fetchone()
    print(f"{tbl}: {'EXISTS' if exists else 'MISSING'}")

print("\n=== Full business 5 evidence ===")
for row in d.execute('SELECT * FROM mm_evidence WHERE business_id=5 ORDER BY id'):
    print(dict(row))
