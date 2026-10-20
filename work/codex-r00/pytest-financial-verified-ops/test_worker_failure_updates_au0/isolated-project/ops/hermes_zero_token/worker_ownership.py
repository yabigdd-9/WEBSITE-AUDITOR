"""One advisory ownership protocol for scheduled and standalone local workers.

Locks use a stable inode and are never unlinked. A runner may explicitly pass its
locked descriptor to its worker child; merely setting an environment flag is not
proof of ownership. Borrowers close their descriptor without unlocking the shared
open-file description, so the parent remains protected until it finishes cleanup.
"""

import fcntl
import json
import os
import re
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

STAGING_WORKERS = frozenset({"staging_db", "screenshot_worker", "demo_blueprint", "outreach_draft"})
ZERO_TOKEN_ENV = {
    "HERMES_ZERO_TOKEN_MODE": "ZERO_LLM",
    "HERMES_ALLOW_HOSTED_LLM": "0",
    "HERMES_ALLOW_PAID_FALLBACK": "0",
    "WEBSITE_AUDITOR_OUTREACH_SEND": "0",
    "MM_EXTERNAL_SEND_DISABLED": "1",
}
FD_ENV = "HERMES_WORKER_LOCK_FD"
GROUP_ENV = "HERMES_WORKER_LOCK_GROUP"
_active = threading.local()


class OwnershipError(ValueError):
    """An inherited descriptor or lock path cannot establish ownership."""


@dataclass(frozen=True)
class Lease:
    descriptor: int
    group: str
    pid: int
    worker_id: str

    def child_environment(self):
        return {**os.environ, **ZERO_TOKEN_ENV, FD_ENV: str(self.descriptor), GROUP_ENV: self.group}


def _group(worker_id):
    if not isinstance(worker_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", worker_id):
        raise OwnershipError("invalid worker identifier")
    if worker_id in STAGING_WORKERS:
        return "staging-artifacts"
    return "testing" if worker_id == "testing_worker" else worker_id


def _check_inode(descriptor, path):
    opened = os.fstat(descriptor)
    named = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode)
            or opened.st_nlink != 1 or opened.st_uid != os.geteuid()
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)):
        raise OwnershipError("lock descriptor does not match its owned regular file")


@contextmanager
def worker_lock(lock_directory, worker_id):
    """Nonblocking lock, reentrant only in this process's owning thread."""
    group = _group(worker_id)
    directory = Path(lock_directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise OwnershipError("lock directory cannot be a symlink")
    path = directory / (group + ".lock")
    key = (str(directory.resolve()), group)
    active = getattr(_active, "leases", {})
    current = active.get(key)
    if current is not None and current.pid == os.getpid():
        if current.worker_id != worker_id:
            raise BlockingIOError("shared worker artifacts already owned by another worker")
        _check_inode(current.descriptor, path)
        yield current
        return

    inherited = os.environ.get(FD_ENV)
    borrowed = inherited is not None
    descriptor = None
    acquired = False
    try:
        if borrowed:
            if (os.environ.get(GROUP_ENV) != group or not inherited.isdecimal()
                    or len(inherited) > 10):
                raise OwnershipError("invalid worker ownership handoff")
            descriptor = os.dup(int(inherited))
            os.set_inheritable(int(inherited), False)
        else:
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        _check_inode(descriptor, path)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        lease = Lease(descriptor, group, os.getpid(), worker_id)
        active = dict(active)
        active[key] = lease
        _active.leases = active
        try:
            yield lease
        finally:
            active = dict(getattr(_active, "leases", {}))
            active.pop(key, None)
            _active.leases = active
    finally:
        if descriptor is not None:
            try:
                if acquired and not borrowed:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def run_owned_worker(project_root, worker_id, action):
    """Standalone entry point: enforce policy and the same lock as the runner."""
    os.environ.update(ZERO_TOKEN_ENV)
    if os.environ.get("HERMES_ZERO_TOKEN_DISABLE_ALL", "0") == "1":
        code, status, reason = 3, "blocked", "worker emergency stop is enabled"
    else:
        try:
            with worker_lock(Path(project_root) / "state/hermes_zero_token/locks", worker_id):
                return action()
        except BlockingIOError:
            code, status, reason = 75, "blocked", "shared worker artifacts already owned"
        except (OwnershipError, OSError):
            code, status, reason = 3, "blocked", "worker ownership could not be verified"
    print(json.dumps({"worker_id": worker_id, "status": status,
                      "production_written": False, "error": reason}))
    return code
