"""Loop and drift-recovery tests for the continuous pipeline.

All fixtures are synthetic and disposable. No network, no model calls, no real
businesses, no sends.
"""
import unittest, tempfile, sqlite3, shutil
import os
from pathlib import Path

import mm_core as c, mm_pipeline as p, mm_workers as w, mm_approval as a
from mm_test_capabilities import HAS_HERMES_SOURCE_DB

# These tests clone the legacy Hermes source DB as their starting fixture.
# When that host-only fixture is absent (sandbox), skip explicitly instead of
# failing with sqlite noise — see FABLE_MASTER_EXECUTION_PLAN P4.
SOURCE_DB_ABSENT = (
    "BLOCKED_FIXTURE: /Users/dd/agent-trials/hermes/database/money_machine.db "
    "not present in this environment"
)


@unittest.skipUnless(HAS_HERMES_SOURCE_DB, SOURCE_DB_ABSENT)
class LoopTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='mm-loop-'))
        (self.root/'database').mkdir()
        os.environ['MM_ROOT'] = str(self.root)
        src = c.connect(Path('/Users/dd/agent-trials/hermes/database/money_machine.db'), readonly=True)
        s2 = sqlite3.connect(str(self.root)+'/database/money_machine.db')
        src.backup(s2); src.close(); s2.close()
        self.d = c.connect(str(self.root)+'/database/money_machine.db')
        self.bid = self.d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,current_status,is_dummy) "
            "VALUES('Loop Demo','Loopville','https://example.com','loop-test',?,'discovered',1)",
            (c.now(),)).lastrowid

    def tearDown(self):
        self.d.close()
        shutil.rmtree(str(self.root), ignore_errors=True)

    def test_loop_once_uses_migrate_and_reports(self):
        a.migrate(self.d)
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