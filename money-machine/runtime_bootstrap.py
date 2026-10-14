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
    names = git(root, "ls-tree", "-r", "--name-only", "-z", revision, "--",
                "money-machine", "auditor_toolkit", "website_auditor").decode().split("\0")
    return {name: git(root, "show", revision + ":" + name)
            for name in names if name.endswith(".py")}


class Verifier(importlib.abc.MetaPathFinder):
    def __init__(self, root, sources, record, failure):
        self.root = root
        self.sources = sources
        self.record = record
        self.failure = failure

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
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not sys.flags.isolated:
        parser.error("launch with python -I to prevent inherited import-path shadowing")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
        parser.error("expected-sha must be an exact 40-character commit SHA")
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
        receipt.update(status="FAILED", failure_code=code)
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
        os.environ["MM_ROOT"] = str(root)
        os.environ["MM_EXTERNAL_SEND_DISABLED"] = "1"
        sys.path[:0] = [str(root), str(root / "money-machine")]
        finder = Verifier(root, sources, record, failure)
        sys.meta_path.insert(0, finder)
        module = importlib.import_module("supervisor.cli")
        if receipt["status"] == "FAILED":
            raise RevisionError(receipt["failure_code"])
        receipt["status"] = "IMPORTS_VERIFIED"
        save()
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        return module.main(arguments)
    except RevisionError as exc:
        receipt.update(status="FAILED", failure_code=str(exc))
        save()
        print("Runtime startup rejected: " + str(exc), file=sys.stderr)
        return 3
    finally:
        if finder is not None:
            sys.meta_path.remove(finder)


if __name__ == "__main__":
    raise SystemExit(main())
