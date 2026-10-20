"""Read-only live-supervisor identity; no process control or database connection.

Independently pinned expectations bind startup evidence to an OS birth token,
executable, command, scheduler and primary DB descriptor. Ambiguity is UNKNOWN.
This is sampled identity evidence, never release approval or provider clearance.
"""

import ast
import ctypes
import hashlib
import json
import math
import os
import plistlib
import re
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from runtime_bootstrap import ManifestGuard, RevisionError, committed_sources, git, process_birth


class IdentityError(RuntimeError):
    pass


def document(path, limit=4 * 1024 * 1024):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise IdentityError("identity_document_type_or_size_invalid")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise IdentityError("identity_document_too_large")
    value = json.loads(raw, object_pairs_hook=ManifestGuard.unique_fields)
    if not isinstance(value, dict):
        raise IdentityError("identity_document_not_object")
    return raw, value


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > 64 * 1024 * 1024:
            raise IdentityError("identity_artifact_too_large")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    if not isinstance(value, str) or not Path(value).is_absolute() or str(Path(value).resolve()) != value:
        raise IdentityError("identity_path_invalid_or_aliased")
    return Path(value)


def _command(command):
    result = subprocess.run(command, capture_output=True, timeout=5,
                            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"})
    if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
        raise IdentityError("identity_os_evidence_unavailable")
    return result.stdout


def process_arguments(pid):
    """Decode only argc argv entries, never the trailing process environment."""
    if sys.platform.startswith("linux"):
        raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        if len(raw) > 1024 * 1024 or not raw.endswith(b"\0"):
            raise IdentityError("process_arguments_invalid")
        return [os.fsdecode(item) for item in raw[:-1].split(b"\0")]
    if sys.platform != "darwin":
        raise IdentityError("process_arguments_platform_unsupported")
    # Apple sysctl.h: CTL_KERN=1, KERN_PROCARGS2=49. Only the argv prefix
    # is interpreted. Raw buffers and environment values are never exported.
    library = ctypes.CDLL(None, use_errno=True)
    library.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                               ctypes.c_void_p, ctypes.c_size_t]
    library.sysctl.restype = ctypes.c_int
    name = (ctypes.c_int * 3)(1, 49, pid)
    size = ctypes.c_size_t()
    if library.sysctl(name, 3, None, ctypes.byref(size), None, 0) or not 4 < size.value <= 1024 * 1024:
        raise IdentityError("process_arguments_unavailable")
    buffer = ctypes.create_string_buffer(size.value)
    if library.sysctl(name, 3, buffer, ctypes.byref(size), None, 0):
        raise IdentityError("process_arguments_unavailable")
    raw = buffer.raw[:size.value]
    argc = ctypes.c_int.from_buffer_copy(raw[:4]).value
    if not 1 <= argc <= 512:
        raise IdentityError("process_argument_count_invalid")
    offset = raw.index(b"\0", 4) + 1  # skip the kernel's executable path
    while offset < len(raw) and raw[offset] == 0:
        offset += 1
    result = []
    for _ in range(argc):
        finish = raw.index(b"\0", offset)
        result.append(os.fsdecode(raw[offset:finish]))
        offset = finish + 1
    return result


def _lsof_files(pid):
    raw = _command(["/usr/sbin/lsof", "-a", "-p", str(pid), "-F0pftDin"])
    records, current = [], {}
    for field in raw.split(b"\0"):
        field = field.lstrip(b"\n")
        if not field:
            continue
        key, value = chr(field[0]), os.fsdecode(field[1:])
        if key == "p" and value != str(pid):
            raise IdentityError("process_file_owner_mismatch")
        if key == "f":
            if current:
                records.append(current)
            current = {}
        if key in {"f", "t", "D", "i", "n"}:
            current[key] = value
    if current:
        records.append(current)
    cwd = next((entry["n"] for entry in records if entry.get("f") == "cwd"), None)
    files = [{"path": entry["n"], "device": int(entry["D"], 16), "inode": int(entry["i"])}
             for entry in records if entry.get("f", "").isdigit() and entry.get("t") == "REG"
             and all(key in entry for key in ["D", "i", "n"])]
    if not cwd:
        raise IdentityError("process_working_directory_unavailable")
    return cwd, files


class NativeObserver:
    def birth(self, pid):
        return process_birth(pid)

    def arguments(self, pid):
        return process_arguments(pid)

    def files(self, pid):
        if sys.platform == "darwin":
            return _lsof_files(pid)
        if not sys.platform.startswith("linux"):
            raise IdentityError("process_files_platform_unsupported")
        folder = Path("/proc") / str(pid)
        files = []
        for entry in (folder / "fd").iterdir():
            try:
                name, info = os.readlink(entry), entry.stat()
                if stat.S_ISREG(info.st_mode):
                    files.append({"path": name, "device": info.st_dev, "inode": info.st_ino})
            except FileNotFoundError:
                continue  # a descriptor closed; required descriptors still must match
        return str((folder / "cwd").resolve(strict=True)), files

    def candidates(self):
        if sys.platform == "darwin":
            rows = _command(["/bin/ps", "-axo", "pid=,comm="]).decode().splitlines()
            pids = [int(row.strip().split(None, 1)[0]) for row in rows if "python" in row.lower()]
        elif sys.platform.startswith("linux"):
            pids = [int(p.name) for p in Path("/proc").iterdir() if p.name.isdecimal()]
        else:
            raise IdentityError("process_inventory_platform_unsupported")
        result = []
        for pid in pids:
            try:
                born = self.birth(pid)
                if born["uid"] != os.geteuid():
                    continue
                argv = self.arguments(pid)
            except (ProcessLookupError, FileNotFoundError, RevisionError):
                continue
            if (any(argv[index:index + 3] == ["-m", "supervisor.cli", "_run-foreground"]
                    for index in range(len(argv)))
                    or (any(arg.endswith("/runtime_bootstrap.py") for arg in argv)
                        and "_run-foreground" in argv)):
                result.append(pid)
            if len(result) > 64:
                raise IdentityError("supervisor_inventory_exceeds_bound")
        return result

    def scheduler(self, service):
        if sys.platform != "darwin" or not re.fullmatch(r"gui/[0-9]+/[A-Za-z0-9_.-]+", service):
            raise IdentityError("scheduler_service_unsupported")
        raw = _command(["/bin/launchctl", "print", service]).decode()
        depth, result = 0, {}
        for line in raw.splitlines():
            stripped = line.strip()
            if depth == 1:
                match = re.fullmatch(r"(pid|state) = ([^{}]+)", stripped)
                if match:
                    key, value = match.groups()
                    if key in result:
                        raise IdentityError("scheduler_fields_ambiguous")
                    result[key] = int(value) if key == "pid" and value.isdecimal() else value
            # Values inside environment/argument blocks cannot impersonate
            # top-level scheduler identity. Never return the raw output.
            depth += stripped.count("{") - stripped.count("}")
            if depth < 0:
                raise IdentityError("scheduler_structure_invalid")
        if depth or set(result) != {"pid", "state"}:
            raise IdentityError("scheduler_identity_unavailable")
        return result


def _expected(path, digest):
    raw, expected = document(path, 65536)
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise IdentityError("runtime_expectation_approval_mismatch")
    required = {"schema_version", "startup_manifest", "executable", "working_directory",
                "database_identity", "command", "workers", "scheduler", "max_heartbeat_age_seconds"}
    if set(expected) != required or type(expected["schema_version"]) is not int or expected["schema_version"] != 1:
        raise IdentityError("runtime_expectation_schema_invalid")
    for field in ["startup_manifest", "executable"]:
        value = expected[field]
        if (not isinstance(value, dict) or set(value) != {"realpath", "sha256"}
                or not isinstance(value["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
            raise IdentityError("runtime_expectation_artifact_invalid")
        canonical(value["realpath"])
    canonical(expected["working_directory"])
    identity = expected["database_identity"]
    if (not isinstance(identity, dict) or set(identity) != {"device", "inode"}
            or any(type(identity[k]) is not int or identity[k] < 0 for k in identity)):
        raise IdentityError("runtime_expected_database_identity_invalid")
    workers = expected["workers"]
    if (not isinstance(workers, list) or not workers or any(not isinstance(w, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", w) for w in workers)
            or len(workers) != len(set(workers))):
        raise IdentityError("runtime_expected_workers_invalid")
    if type(expected["max_heartbeat_age_seconds"]) is not int or not 1 <= expected["max_heartbeat_age_seconds"] <= 600:
        raise IdentityError("runtime_heartbeat_bound_invalid")
    return raw, expected


def _worker_scope(expected, root, manifest, sha, sources):
    command = expected["command"]
    if (not isinstance(command, list) or not command or len(command) > 100
            or any(not isinstance(arg, str) or len(arg) > 8192 for arg in command)):
        raise IdentityError("runtime_expected_command_invalid")
    prefix = [command[0], "-I", str(root / "money-machine/runtime_bootstrap.py"), "--expected-sha", sha,
              "--manifest", manifest["realpath"], "--manifest-sha256", manifest["sha256"], "--", "_run-foreground"]
    if command[:len(prefix)] != prefix or not Path(command[0]).is_absolute():
        raise IdentityError("runtime_bootstrap_command_mismatch")
    trailing = command[len(prefix):]
    if len(trailing) % 2:
        raise IdentityError("runtime_worker_arguments_invalid")
    workers, seen = [], set()
    for option, value in zip(trailing[::2], trailing[1::2]):
        if option == "--worker":
            workers.append(value)
        elif option in {"--sleep", "--lease", "--rotate-every"} and option not in seen:
            number = float(value)
            if not math.isfinite(number) or number <= 0 or (option != "--sleep" and not value.isdecimal()):
                raise IdentityError("runtime_worker_arguments_invalid")
            seen.add(option)
        else:
            raise IdentityError("runtime_worker_arguments_invalid")
    if workers != expected["workers"]:
        raise IdentityError("runtime_worker_scope_mismatch")
    tree = ast.parse(sources["money-machine/mm_workers.py"])
    registries = [n.value for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "WORKERS" for t in n.targets)]
    if len(registries) != 1 or not isinstance(registries[0], ast.Dict):
        raise IdentityError("committed_worker_registry_unavailable")
    known = [key.value for key in registries[0].keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
    if not set(workers) <= set(known):
        raise IdentityError("runtime_worker_not_in_approved_registry")


def collect_runtime_identity(root, *, expectations_path=None, expectations_sha256=None, observer=None, clock=time.time):
    """Read a bounded sample. Omission/failure is UNKNOWN, never a weak pass."""
    result = {"verified": False, "runtime_identity_status": "UNKNOWN", "failure_code": "runtime_expectations_missing",
              "scope": "Sampled primary-supervisor identity; no release, provider or ancillary-worker approval"}
    if expectations_path is None or expectations_sha256 is None:
        return result
    root = Path(root).resolve()
    observer = observer or NativeObserver()
    try:
        raw_expected, expected = _expected(expectations_path, expectations_sha256)
        from mm_soak import verify_startup_identity

        pid_path = root / "state/supervisor.pid"
        pid_info = pid_path.stat()
        pid = int(pid_path.read_text().strip())
        if pid <= 0:
            raise IdentityError("runtime_pid_invalid")
        birth = observer.birth(pid)
        if birth["uid"] != os.geteuid():
            raise IdentityError("runtime_owner_mismatch")
        receipt_path = root / "state/runtime-startup" / (str(pid) + ".json")
        receipt_bytes, receipt = document(receipt_path)
        if receipt.get("status") != "IMPORTS_VERIFIED" or receipt.get("process_birth") != birth:
            raise IdentityError("runtime_birth_receipt_mismatch")
        manifest = expected["startup_manifest"]
        verify_startup_identity(receipt, pid, manifest["realpath"], manifest["sha256"], root=root,
                                python_executable=expected["command"][0])
        sources = committed_sources(root, receipt["expected_sha"])
        if git(root, "rev-parse", "HEAD").decode().strip() != receipt["expected_sha"]:
            raise IdentityError("runtime_revision_changed")
        for name, data in sources.items():
            if (root / name).read_bytes() != data:
                raise IdentityError("runtime_source_changed")
        required = {"money-machine/runtime_bootstrap.py", "money-machine/supervisor/cli.py",
                    "money-machine/mm_core.py", "money-machine/mm_workers.py", "money-machine/mm_pipeline.py"}
        if not required <= {entry["path"] for entry in receipt["modules"]}:
            raise IdentityError("runtime_required_execution_evidence_missing")
        _worker_scope(expected, root, manifest, receipt["expected_sha"], sources)
        if observer.arguments(pid) != expected["command"]:
            raise IdentityError("runtime_live_command_mismatch")
        if (birth["executable_realpath"] != expected["executable"]["realpath"]
                or fingerprint(canonical(birth["executable_realpath"])) != expected["executable"]["sha256"]):
            raise IdentityError("runtime_executable_mismatch")
        cwd, files = observer.files(pid)
        if canonical(cwd) != canonical(expected["working_directory"]) or canonical(cwd) != root / "money-machine":
            raise IdentityError("runtime_working_directory_mismatch")
        database = root / "database/money_machine.db"
        database_info = database.stat()
        db_identity = {"device": database_info.st_dev, "inode": database_info.st_ino}
        if canonical(str(database)) != database or db_identity != expected["database_identity"]:
            raise IdentityError("runtime_database_file_replaced")
        matching = lambda entries, path, info: any(entry == {"path": str(path), "device": info.st_dev, "inode": info.st_ino} for entry in entries)
        if not matching(files, database, database_info) or not matching(files, pid_path, pid_info):
            raise IdentityError("runtime_primary_database_or_pid_handle_mismatch")
        for other in observer.candidates():
            if other == pid:
                continue
            other_cwd, other_files = observer.files(other)
            if Path(other_cwd).resolve() == cwd or matching(other_files, database, database_info):
                raise IdentityError("duplicate_supervisor_or_primary_database_owner")
        scheduler = expected["scheduler"]
        if not isinstance(scheduler, dict) or scheduler.get("identity") != receipt["scheduler_identity"]:
            raise IdentityError("runtime_scheduler_identity_mismatch")
        if scheduler.get("kind") == "parent" and set(scheduler) == {"kind", "identity", "process_birth"}:
            if observer.birth(birth["parent_pid"]) != scheduler["process_birth"]:
                raise IdentityError("runtime_scheduler_parent_mismatch")
        elif scheduler.get("kind") == "launchd" and set(scheduler) == {"kind", "identity", "service", "plist"}:
            plist = scheduler["plist"]
            plist_path = canonical(plist["realpath"])
            if fingerprint(plist_path) != plist["sha256"]:
                raise IdentityError("runtime_scheduler_configuration_changed")
            with plist_path.open("rb") as stream:
                config = plistlib.load(stream)
            env = config.get("EnvironmentVariables", {})
            if (config.get("Label") != scheduler["service"].rsplit("/", 1)[-1]
                    or config.get("ProgramArguments") != expected["command"]
                    or config.get("WorkingDirectory") != cwd
                    or env.get("MM_ROOT") != str(root) or env.get("MM_EXTERNAL_SEND_DISABLED") != "1"
                    or observer.scheduler(scheduler["service"]) != {"pid": pid, "state": "running"}):
                raise IdentityError("runtime_scheduler_binding_mismatch")
        else:
            raise IdentityError("runtime_scheduler_evidence_unsupported")
        _, heartbeat = document(root / "state/supervisor.heartbeat", 65536)
        at = datetime.fromisoformat(heartbeat["at"])
        if at.tzinfo is None:
            raise IdentityError("runtime_heartbeat_timezone_missing")
        epoch = at.timestamp()
        if (heartbeat.get("pid") != pid or heartbeat.get("status") != "running"
                or not birth["start_epoch"] <= epoch <= clock()
                or clock() - epoch > expected["max_heartbeat_age_seconds"]):
            raise IdentityError("runtime_heartbeat_stale_or_stopped")
        if (observer.birth(pid) != birth or document(receipt_path)[0] != receipt_bytes
                or document(expectations_path, 65536)[0] != raw_expected
                or pid_path.stat().st_ino != pid_info.st_ino or int(pid_path.read_text()) != pid):
            raise IdentityError("runtime_identity_changed_during_observation")
        result.update(verified=True, runtime_identity_status="VERIFIED", failure_code=None,
                      pid=pid, process_start_id=birth["start_id"], expected_sha=receipt["expected_sha"],
                      startup_manifest_sha256=manifest["sha256"], expectations_sha256=expectations_sha256,
                      worker_ids=expected["workers"], primary_database_identity=db_identity,
                      scheduler_kind=scheduler["kind"], heartbeat_status="running",
                      sampled_at_utc=datetime.fromtimestamp(clock(), timezone.utc).isoformat())
    except (IdentityError, RevisionError) as exc:
        result["failure_code"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration, RecursionError,
            subprocess.SubprocessError, sqlite3.Error):
        result["failure_code"] = "runtime_identity_evidence_unavailable_or_invalid"
    return result
