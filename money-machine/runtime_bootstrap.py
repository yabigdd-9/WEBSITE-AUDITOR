"""Verify committed module execution before starting the existing supervisor.

This entry point is opt-in. Adding it does not change launchd or restart a
service. The operator must select an exact revision and approve its activation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import io
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ENTRY_CODE = sys._getframe().f_code


class RevisionError(RuntimeError):
    """A bounded, redacted startup failure code."""


def git(root, *arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments], timeout=30)


def committed_sources(root, revision):
    try:
        listing = git(root, "ls-tree", "-r", "-l", "-z", revision, "--",
                      "money-machine", "auditor_toolkit", "website_auditor")
    except subprocess.SubprocessError as exc:
        raise RevisionError("committed_source_read_failed") from exc
    entries = []
    try:
        for raw in listing.split(b"\0"):
            if not raw:
                continue
            metadata, name = raw.split(b"\t", 1)
            if not name.endswith(b".py"):
                continue
            mode, kind, oid, size = metadata.split()
            if kind != b"blob" or mode not in (b"100644", b"100755"):
                raise RevisionError("committed_source_type_invalid")
            count = int(size)
            if not re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid) or not 0 <= count <= 64 * 1024 * 1024:
                raise RevisionError("committed_source_size_invalid")
            entries.append((name.decode("utf-8", "surrogateescape"), oid, count))
        if sum(size for _, _, size in entries) > 256 * 1024 * 1024:
            raise RevisionError("committed_sources_too_large")
        if not entries:
            return {}
        result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                                input=b"".join(oid + b"\n" for _, oid, _ in entries),
                                capture_output=True, check=True, timeout=30)
        stream = io.BytesIO(result.stdout)
        sources = {}
        for name, oid, size in entries:
            if stream.readline() != oid + b" blob " + str(size).encode() + b"\n":
                raise RevisionError("committed_source_batch_invalid")
            data = stream.read(size)
            if len(data) != size or stream.read(1) != b"\n":
                raise RevisionError("committed_source_batch_truncated")
            sources[name] = data
        if stream.read(1):
            raise RevisionError("committed_source_batch_trailing_data")
        return sources
    except (ValueError, subprocess.SubprocessError) as exc:
        raise RevisionError("committed_source_read_failed") from exc


class ManifestGuard:
    """Pinned operator input: startup identity only, never release approval."""

    FIELDS = {"schema_version", "release_id", "source_sha", "repository_realpath",
              "python_realpath", "database_realpath", "configuration", "scheduler_identity"}

    def __init__(self, path, digest, root, revision):
        self.path = Path(path)
        self.digest = digest
        self.root = root
        self.revision = revision
        self.document = None
        self.verify()

    @staticmethod
    def canonical(value):
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise RevisionError("manifest_path_invalid")
        path = Path(value)
        if str(path.resolve()) != value:
            raise RevisionError("manifest_path_alias")
        return path

    @staticmethod
    def unique_fields(pairs):
        document = {}
        for key, value in pairs:
            if key in document:
                raise RevisionError("manifest_duplicate_field")
            document[key] = value
        return document

    def verify(self):
        try:
            raw = self.path.read_bytes()
            if not re.fullmatch(r"[0-9a-f]{64}", self.digest) or hashlib.sha256(raw).hexdigest() != self.digest:
                raise RevisionError("manifest_approval_mismatch")
            doc = json.loads(raw, object_pairs_hook=self.unique_fields)
            if not isinstance(doc, dict) or set(doc) != self.FIELDS or type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
                raise RevisionError("manifest_schema_invalid")
            if not isinstance(doc["release_id"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", doc["release_id"]):
                raise RevisionError("manifest_release_invalid")
            if doc["source_sha"] != self.revision:
                raise RevisionError("manifest_revision_mismatch")
            if self.canonical(doc["repository_realpath"]) != self.root:
                raise RevisionError("manifest_repository_mismatch")
            if self.canonical(doc["python_realpath"]) != Path(sys.executable).resolve():
                raise RevisionError("manifest_interpreter_mismatch")
            if self.canonical(doc["database_realpath"]) != self.root / "database/money_machine.db":
                raise RevisionError("manifest_database_mismatch")
            scheduler = doc["scheduler_identity"]
            if not isinstance(scheduler, str) or not scheduler or scheduler != os.environ.get("MM_SCHEDULER_ID"):
                raise RevisionError("manifest_scheduler_mismatch")
            configs = doc["configuration"]
            if not isinstance(configs, list) or not configs:
                raise RevisionError("manifest_configuration_missing")
            seen = set()
            for config in configs:
                if not isinstance(config, dict) or set(config) != {"realpath", "sha256"}:
                    raise RevisionError("manifest_configuration_invalid")
                path = self.canonical(config["realpath"])
                if not path.is_relative_to(self.root) or path in seen:
                    raise RevisionError("manifest_configuration_path_invalid")
                seen.add(path)
                digest = config["sha256"]
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise RevisionError("manifest_configuration_changed")
            self.document = doc
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RevisionError("manifest_unreadable_or_invalid") from exc

    def identity(self):
        return {"manifest_sha256": self.digest, "release_id": self.document["release_id"],
                "repository_realpath": str(self.root),
                "python_realpath": str(Path(sys.executable).resolve()),
                "database_realpath": self.document["database_realpath"],
                "configuration": self.document["configuration"],
                "scheduler_identity": self.document["scheduler_identity"],
                "parent_pid": os.getppid(), "existing_runtime_status": "UNKNOWN"}


class Verifier(importlib.abc.MetaPathFinder):
    def __init__(self, root, sources, record, failure, guard=None):
        self.root = root
        self.sources = sources
        self.record = record
        self.failure = failure
        self.guard = guard

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if not spec or not spec.origin:
            return spec
        origin = Path(spec.origin).resolve()
        owned_name = fullname.startswith(("auditor_toolkit", "website_auditor", "supervisor", "mm_"))
        if not origin.is_relative_to(self.root) or any(part.startswith(".venv") for part in origin.parts):
            if owned_name:
                self.failure("application_module_outside_checkout")
            return spec
        if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            relative = str(origin.relative_to(self.root))
            if relative not in self.sources:
                self.failure("uncommitted_application_module")
            spec.loader = CheckedLoader(fullname, str(origin), self, relative)
        return spec


class CheckedLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, verifier, relative):
        super().__init__(name, path)
        self.verifier = verifier
        self.relative = relative

    def exec_module(self, module):
        if self.verifier.guard is not None:
            try:
                self.verifier.guard.verify()
            except RevisionError as exc:
                self.verifier.failure(str(exc))
        expected = self.verifier.sources[self.relative]
        if Path(self.path).read_bytes() != expected:
            self.verifier.failure("application_source_changed")
        code = self.get_code(module.__name__)
        fresh = compile(expected, self.path, "exec", dont_inherit=True, optimize=sys.flags.optimize)
        if code != fresh:
            self.verifier.failure("stale_loaded_code")
        self.verifier.record(self.relative, hashlib.sha256(expected).hexdigest())
        exec(code, module.__dict__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not sys.flags.isolated:
        parser.error("launch with python -I to prevent inherited import-path shadowing")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
        parser.error("expected-sha must be an exact 40-character commit SHA")
    if bool(args.manifest) != bool(args.manifest_sha256):
        parser.error("manifest and manifest-sha256 must be supplied together")
    root = Path(__file__).resolve().parents[1]
    folder = root / "state/runtime-startup"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt_path = folder / (str(os.getpid()) + ".json")
    receipt = {"pid": os.getpid(), "expected_sha": args.expected_sha,
               "started_at": datetime.now(UTC).isoformat(), "status": "VERIFYING",
               "python_executable": sys.executable, "python_version": sys.version,
               "isolated_python": True, "modules": [], "scope": "Executed application imports; not soak or release acceptance."}

    def save():
        temporary = receipt_path.with_suffix(".tmp")
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, receipt_path)

    def record(path, digest):
        receipt["modules"].append({"path": path, "sha256": digest})
        save()

    def failure(code):
        receipt.update(status="FAILED", identity_status="FAILED", failure_code=code)
        save()
        raise RevisionError(code)

    finder = None
    try:
        if git(root, "rev-parse", "HEAD").decode().strip() != args.expected_sha:
            raise RevisionError("checkout_revision_changed")
        sources = committed_sources(root, args.expected_sha)
        entry = str(Path(__file__).resolve().relative_to(root))
        if Path(__file__).read_bytes() != sources.get(entry):
            raise RevisionError("bootstrap_source_changed")
        if ENTRY_CODE != compile(sources[entry], str(Path(__file__).resolve()), "exec",
                                 dont_inherit=True, optimize=sys.flags.optimize):
            raise RevisionError("bootstrap_execution_changed")
        record(entry, hashlib.sha256(sources[entry]).hexdigest())
        configured = Path(os.environ.get("MM_ROOT", str(root))).resolve()
        if configured != root:
            raise RevisionError("runtime_root_mismatch")
        guard = ManifestGuard(args.manifest, args.manifest_sha256, root, args.expected_sha) if args.manifest else None
        receipt["attestation_mode"] = "PINNED_STARTUP" if guard else "SOURCE_ONLY"
        if guard:
            receipt.update(guard.identity())
        os.environ["MM_ROOT"] = str(root)
        os.environ["MM_EXTERNAL_SEND_DISABLED"] = "1"
        sys.path[:0] = [str(root), str(root / "money-machine")]
        finder = Verifier(root, sources, record, failure, guard)
        sys.meta_path.insert(0, finder)
        module = importlib.import_module("supervisor.cli")
        if receipt["status"] == "FAILED":
            raise RevisionError(receipt["failure_code"])
        if guard:
            guard.verify()
            if any((root / name).read_bytes() != source for name, source in sources.items()):
                raise RevisionError("application_source_changed")
        receipt["status"] = "IMPORTS_VERIFIED"
        receipt["identity_status"] = "STARTUP_IDENTITY_VERIFIED" if guard else "SOURCE_ONLY"
        save()
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        result = module.main(arguments)
        if guard:
            guard.verify()
            if git(root, "rev-parse", "HEAD").decode().strip() != args.expected_sha:
                raise RevisionError("checkout_revision_changed")
            if any((root / name).read_bytes() != source for name, source in sources.items()):
                raise RevisionError("application_source_changed")
        receipt["target_exit_code"] = result
        save()
        return result
    except (RevisionError, OSError) as exc:
        receipt.update(status="FAILED", identity_status="FAILED", failure_code=str(exc) if isinstance(exc, RevisionError) else "runtime_identity_io_error")
        save()
        print("Runtime startup rejected: " + receipt["failure_code"], file=sys.stderr)
        return 3
    finally:
        if finder is not None:
            sys.meta_path.remove(finder)


if __name__ == "__main__":
    raise SystemExit(main())
