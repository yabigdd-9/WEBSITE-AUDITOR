"""PID file management with atomic operations and locking."""
import os
import fcntl
import signal
import atexit
from contextlib import suppress
from pathlib import Path
from typing import Optional


class PIDFile:
    """Manages a PID file with atomic operations and process verification."""
    
    def __init__(self, path: Path):
        self.path = Path(path)
        self._fd: Optional[int] = None
        self._locked = False
    
    def acquire(self) -> bool:
        """Lock a stable inode before inspecting or writing process ownership.

        Keep the file in place on release: unlinking a flock-protected file
        permits a second inode, and consequently a second independent lock.
        """
        if self._locked:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return False
            # Respect live legacy owners which did not acquire flock.
            self._fd = fd
            if not self._is_stale():
                self._fd = None
                os.close(fd)
                return False
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(os.getpid()).encode())
            os.fsync(fd)
        except BaseException:
            self._fd = None
            os.close(fd)
            raise
        self._locked = True
        atexit.register(self.release)
        return True

    def _is_stale(self) -> bool:
        """Only absent/malformed/dead ownership is recoverable."""
        try:
            if self._fd is not None:
                os.lseek(self._fd, 0, os.SEEK_SET)
                content = os.read(self._fd, 128).decode().strip()
            else:
                content = self.path.read_text().strip()
            pid = int(content)
            if pid <= 0:
                return True
            os.kill(pid, 0)
            return False
        except (ValueError, UnicodeError, FileNotFoundError, ProcessLookupError):
            return True
        except OSError:
            # Permission errors and unknown inspection failures deny recovery.
            return False

    def release(self) -> None:
        """Clear only our locked descriptor; never unlink a replacement path."""
        if not self._locked or self._fd is None:
            return
        fd = self._fd
        self._fd = None
        self._locked = False
        try:
            os.ftruncate(fd, 0)
            os.fsync(fd)
        finally:
            os.close(fd)  # close releases flock, after clearing ownership

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire PID lock at {self.path}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def write_pid_atomic(path: Path, pid: int) -> None:
    """Atomically write PID to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(str(pid))
    os.fsync(tmp.open().fileno())
    tmp.replace(path)


def read_pid(path: Path) -> Optional[int]:
    """Read PID from file, returns None if not found or invalid."""
    try:
        return int(path.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def is_process_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
