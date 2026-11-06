"""Loop and drift-recovery tests for the continuous pipeline.

All fixtures are synthetic and disposable. No network, no model calls, no real
businesses, no sends.
"""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mm_approval as a
import mm_core as c
import mm_pipeline as p
import mm_workers as w


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='mm-loop-'))
        (self.root/'database').mkdir()
        self.env = patch.dict(os.environ, {"MM_ROOT": str(self.root)})
        self.env.start()
        path = self.root / "database/money_machine.db"
        with sqlite3.connect(path) as database:
            database.executescript((Path(__file__).resolve().parent / "database/schema.sql").read_text())
        self.d = c.connect(str(self.root)+'/database/money_machine.db')
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) "
            "VALUES('Loop Demo','Loopville','https://example.com','loop-test',?,'discovered',1)",
            (c.now(),)).lastrowid

    def tearDown(self):
        self.d.close()
        self.env.stop()
        shutil.rmtree(str(self.root), ignore_errors=True)

    def test_loop_once_uses_migrate_and_reports(self):
        a.migrate(self.d)
        p.migrate(self.d)
        p.enqueue(self.d, self.bid)
        workers = [p.Worker('w-identity', w.WORKERS['identity'][0], w.WORKERS['identity'][1])]
        snap = p.RunPipeline.run_pipelineloop(self.d, workers, max_cycles=1)
        self.assertEqual(snap, 1)

    def test_driftfirst_applies_migrate(self):
        self.assertEqual(p.driftfirst_apply(self.d), None)
        cols = {r[1] for r in self.d.execute('PRAGMA table_info(pipeline_events)')}
        self.assertTrue({'to_state','actor','reason','evidence'} <= cols)


if __name__ == '__main__':
    unittest.main()
