"""PID file management with atomic operations and locking."""
import os
import fcntl
import signal
import atexit
from pathlib import Path
from typing import Optional


class PIDFile:
    """Manages a PID file with atomic operations and process verification."""
    
    def __init__(self, path: Path):
        self.path = Path(path)
        self._fd: Optional[int] = None
        self._locked = False
    
    def acquire(self) -> bool:
        """Acquire the PID lock. Returns True if successful, False if another process holds the lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open with O_CREAT | O_EXCL for atomic creation attempt
        try:
            self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        except FileExistsError:
            # PID file exists, check if process is still alive
            if self._is_stale():
                # Stale PID, remove and retry
                self.path.unlink()
                try:
                    self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
                except FileExistsError:
                    return False
            else:
                return False
        
        # Lock the file
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
        except BlockingIOError:
            os.close(self._fd)
            self._fd = None
            return False
        
        # Write our PID
        pid = str(os.getpid())
        os.write(self._fd, pid.encode())
        os.fsync(self._fd)
        
        # Register cleanup
        atexit.register(self.release)
        return True
    
    def _is_stale(self) -> bool:
        """Check if the PID in the file corresponds to a dead process."""
        try:
            content = self.path.read_text().strip()
            if not content:
                return True
            pid = int(content)
            # Signal 0 doesn't send a signal but checks process existence
            os.kill(pid, 0)
            return False  # Process exists
        except (ValueError, OSError, ProcessLookupError):
            return True  # Stale or invalid
    
    def release(self) -> None:
        """Release the PID lock and remove the file."""
        if self._locked and self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            self._locked = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        # Remove the PID file
        with suppress(FileNotFoundError):
            self.path.unlink()
    
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


# Import suppress for use in PIDFile
from contextlib import suppress