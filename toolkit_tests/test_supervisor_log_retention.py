import os
import time

from supervisor.daemon import rotate_logs


def test_archive_retention_preserves_recent_and_active_logs(tmp_path):
    old = tmp_path / 'worker.jsonl.20000101_000000.gz'
    recent = tmp_path / 'worker.jsonl.20990101_000000.gz'
    active = tmp_path / 'supervisor.jsonl'
    unrelated = tmp_path / 'evidence.gz'
    for file in (old, recent, active, unrelated):
        file.write_bytes(b'fixture')
    os.utime(old, (time.time()-31*86400,) * 2)
    rotate_logs(tmp_path, retention_days=30)
    assert not old.exists()
    assert recent.exists() and active.exists() and unrelated.exists()


def test_old_daily_log_is_compressed_and_symbolic_links_ignored(tmp_path):
    import gzip
    old = tmp_path / '2000-01-01.jsonl'
    old.write_bytes(b'{"kind":"synthetic"}\n')
    os.utime(old, (time.time()-31*86400,) * 2)
    link = tmp_path / 'linked.jsonl'
    link.symlink_to(old)
    archives = rotate_logs(tmp_path)
    assert not old.exists() and link.is_symlink()
    assert len(archives) == 1
    with gzip.open(archives[0]) as stream:
        assert stream.read() == b'{"kind":"synthetic"}\n'
