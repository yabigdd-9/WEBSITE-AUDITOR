"""Private ciphertext custody/indexing; no decryption, network or storage provisioning."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.report_vault import FORMAT, MAX_ENVELOPE_BYTES
from scripts.review_ledger import _is_safe_db_location, _timestamp

MAX_ARCHIVE_BYTES = 50_000_000
MAX_ARTIFACTS = 1000
MAX_RETENTION_SECONDS = 365 * 86400
HASH = re.compile(r"[0-9a-f]{64}\Z")
METADATA_FIELDS = {
    "artifact_id", "ciphertext_sha256", "format", "byte_count", "created_at",
    "source_expires_at", "retain_until", "source_run_id", "source_artifact_id",
    "archived_at", "verification_status",
}


def validate_metadata(metadata):
    if not isinstance(metadata, dict) or set(metadata) != METADATA_FIELDS:
        raise ValueError("Invalid archive metadata fields")
    identity = metadata["artifact_id"]
    if (not isinstance(identity, str) or not HASH.fullmatch(identity)
            or identity != metadata["ciphertext_sha256"] or metadata["format"] != FORMAT
            or metadata["verification_status"] != "envelope_and_checksum_only"
            or type(metadata["byte_count"]) is not int
            or not 0 < metadata["byte_count"] <= MAX_ENVELOPE_BYTES):
        raise ValueError("Invalid archive metadata identity or size")
    for key in ("source_run_id", "source_artifact_id"):
        value = metadata[key]
        if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
            raise ValueError("Invalid source reference")
    for key in ("created_at", "source_expires_at", "retain_until", "archived_at"):
        if _timestamp(metadata[key]) != metadata[key]:
            raise ValueError("Archive timestamps must be canonical UTC")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate envelope field")
        result[key] = value
    return result


def validate_envelope(data):
    """Validate structure only. Authenticated decryption remains owner-side."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_ENVELOPE_BYTES:
        raise ValueError("Invalid bounded encrypted report")
    value = json.loads(data, object_pairs_hook=unique_object)
    fields = {"format", "ephemeral_public_key", "salt", "nonce", "ciphertext"}
    if not isinstance(value, dict) or set(value) != fields or value["format"] != FORMAT:
        raise ValueError("Only the existing report-vault envelope is accepted")
    sizes = {"ephemeral_public_key": 32, "salt": 16, "nonce": 12}
    for key, size in sizes.items():
        if not isinstance(value[key], str) or len(base64.b64decode(value[key], validate=True)) != size:
            raise ValueError("Invalid envelope field")
    if not isinstance(value["ciphertext"], str) or len(base64.b64decode(value["ciphertext"], validate=True)) < 16:
        raise ValueError("Missing authenticated ciphertext")
    return hashlib.sha256(data).hexdigest()


def read_envelope(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Regular ciphertext file required")
    with path.open("rb") as stream:
        data = stream.read(MAX_ENVELOPE_BYTES + 1)
    validate_envelope(data)
    return data


class EncryptedReportArchive:
    def __init__(self, root):
        raw = Path(root).expanduser().absolute()
        if raw.is_symlink() or not raw.is_dir() or raw.stat().st_mode & 0o077:
            raise ValueError("Create a private 0700 archive directory first")
        self.root = raw.resolve()
        # Reuse the installed/source checkout and replacement protections.
        _is_safe_db_location(self.root / "archive-location-check.sqlite3")

    def check_location(self):
        if self.root.is_symlink() or not self.root.is_dir() or self.root.stat().st_mode & 0o077:
            raise ValueError("Archive directory permissions changed")
        _is_safe_db_location(self.root / "archive-location-check.sqlite3")

    def path(self, artifact_id):
        if not isinstance(artifact_id, str) or not HASH.fullmatch(artifact_id):
            raise ValueError("Invalid ciphertext identity")
        self.check_location()
        return self.root / (artifact_id + ".enc.json")

    def read(self, artifact_id):
        path = self.path(artifact_id)
        if path.stat().st_mode & 0o077:
            raise ValueError("Ciphertext file must have private permissions")
        data = read_envelope(path)
        if hashlib.sha256(data).hexdigest() != artifact_id:
            raise ValueError("Ciphertext checksum changed")
        return data

    def usage(self):
        total = count = 0
        for entry in self.root.iterdir():
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("Dedicated archive cannot contain links or directories")
            total += entry.stat().st_size
            count += 1
            if count > MAX_ARTIFACTS or total > MAX_ARCHIVE_BYTES:
                raise ValueError("Private archive capacity reached")
        return count, total

    def put(self, data):
        artifact_id = validate_envelope(data)
        target = self.path(artifact_id)
        if target.exists() or target.is_symlink():
            self.read(artifact_id)
            return artifact_id
        count, total = self.usage()
        if count >= MAX_ARTIFACTS or total + len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("Private archive capacity reached")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix=".sealed-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)  # Exclusive publication; never overwrite.
            except FileExistsError:
                self.read(artifact_id)
            directory = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return artifact_id


def registration(state, data, *, expected_sha256, audit_ids, source_run_id, source_artifact_id,
                 created_at, source_expires_at, retain_until, owner_reviewed, actor, reason, now):
    artifact_id = validate_envelope(data)
    if artifact_id != expected_sha256:
        raise ValueError("Downloaded ciphertext does not match the expected checksum")
    if owner_reviewed is not True:
        raise ValueError("Owner must review the archive/audit association locally")
    from scripts.approval_controls import actor_record

    decision = actor_record(actor, reason, now)
    if not all(isinstance(v, str) and re.fullmatch(r"[1-9][0-9]{0,19}", v)
               for v in (source_run_id, source_artifact_id)):
        raise ValueError("Numeric GitHub source references required")
    created, expires, retain = map(_timestamp, (created_at, source_expires_at, retain_until))
    created_time, expires_time, retain_time = (
        datetime.fromisoformat(value).timestamp() for value in (created, expires, retain)
    )
    if (created_time > now + 300 or not 0 < expires_time - created_time <= 30 * 86400 + 300
            or not now < retain_time <= now + MAX_RETENTION_SECONDS):
        raise ValueError("Invalid explicit source/local retention dates")
    if (not isinstance(audit_ids, list) or not 1 <= len(audit_ids) <= 10 or not all(isinstance(identity, str) for identity in audit_ids)
            or len(set(audit_ids)) != len(audit_ids)):
        raise ValueError("One to ten distinct recorded audit references required")
    audits = {audit["audit_id"]: audit for audit in state.get("audit_runs", [])}
    if any(identity not in audits for identity in audit_ids):
        raise ValueError("Archive must link to known audit attempts")
    indexed = state.get("report_artifacts", {})
    links = state.get("audit_artifact_links", [])
    metadata = {
        "artifact_id": artifact_id, "ciphertext_sha256": artifact_id,
        "format": FORMAT, "byte_count": len(data), "created_at": created,
        "source_expires_at": expires, "retain_until": retain,
        "source_run_id": source_run_id, "source_artifact_id": source_artifact_id,
        "archived_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "verification_status": "envelope_and_checksum_only",
    }
    validate_metadata(metadata)
    existing = indexed.get(artifact_id)
    if existing is not None:
        metadata["archived_at"] = existing["archived_at"]
        if metadata != existing:
            raise ValueError("Conflicting immutable archive metadata")
    additions = [
        {"artifact_id": artifact_id, "audit_id": identity,
         "canonical_run_id": audits[identity].get("canonical_run_id"),
         "audit_status": audits[identity]["status"], "owner_reviewed": True, **decision}
        for identity in audit_ids
        if not any(link["artifact_id"] == artifact_id and link["audit_id"] == identity for link in links)
    ]
    if len(set(indexed) | {artifact_id}) > MAX_ARTIFACTS or len(links) + len(additions) > 10000:
        raise ValueError("Archive index capacity reached")
    working = copy.deepcopy(state)
    working.setdefault("report_artifacts", {})[artifact_id] = metadata
    working.setdefault("audit_artifact_links", []).extend(additions)
    return working, artifact_id


def availability(metadata, archive, *, now):
    validate_metadata(metadata)
    if datetime.fromisoformat(metadata["retain_until"]).timestamp() <= now:
        return "EXPIRED"
    if archive is None:
        return "ARCHIVE_NOT_CONFIGURED"
    try:
        data = archive.read(metadata["artifact_id"])
        if len(data) != metadata["byte_count"]:
            return "CORRUPT"
    except FileNotFoundError:
        return "MISSING"
    except (ValueError, OSError):
        return "CORRUPT"
    return "AVAILABLE"


def import_ciphertext(store, archive, path, **options):
    data = read_envelope(path)
    with store.transaction() as state:
        working, identity = registration(state, data, **options)
        archive.put(data)
        state.clear()
        state.update(working)
    return identity


def main(argv=None):
    parser = argparse.ArgumentParser(description="Index an owner-reviewed encrypted report; never decrypts")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--audit-id", action="append", required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--source-artifact-id", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--source-expires-at", required=True)
    parser.add_argument("--retain-until", required=True)
    parser.add_argument("--owner-reviewed", action="store_true", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        import time

        from scripts.pipeline_store import PipelineStore

        import_ciphertext(
            PipelineStore(args.database), EncryptedReportArchive(args.archive_dir), args.input,
            expected_sha256=args.expected_sha256, audit_ids=args.audit_id,
            source_run_id=args.source_run_id, source_artifact_id=args.source_artifact_id,
            created_at=args.created_at, source_expires_at=args.source_expires_at,
            retain_until=args.retain_until, owner_reviewed=args.owner_reviewed,
            actor="local-owner", reason=args.reason, now=int(time.time()),
        )
        print("Encrypted report indexed. No decryption, network request or storage service activation performed.")
        return 0
    except Exception:
        print("Archive import blocked; inspect configuration and ciphertext privately.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
