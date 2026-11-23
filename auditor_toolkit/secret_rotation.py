"""Automated secret rotation for auditor_toolkit.

Provides scheduled secret rotation with configurable policies.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RotationPolicy:
    """Policy for secret rotation."""

    name: str
    max_age_days: int = 90
    warning_days: int = 14
    auto_rotate: bool = False
    generator: str | None = None  # Command to generate new secret
    required: bool = False


@dataclass
class SecretMetadata:
    """Metadata for a managed secret."""

    name: str
    created_at: str
    rotated_at: str | None = None
    expires_at: str | None = None
    policy: RotationPolicy | None = None
    version: int = 1

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.fromisoformat(self.expires_at) <= datetime.now(UTC)

    def needs_rotation(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.fromisoformat(self.expires_at) <= datetime.now(UTC) + timedelta(days=14)

    def days_until_expiry(self) -> int | None:
        if self.expires_at is None:
            return None
        delta = datetime.fromisoformat(self.expires_at) - datetime.now(UTC)
        return max(0, delta.days)


class SecretRotationManager:
    """Manages automated secret rotation."""

    def __init__(self, service_name: str = "website-auditor", metadata_dir: Path | None = None):
        self.service_name = service_name
        self.metadata_dir = metadata_dir or Path.cwd() / ".secrets_metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.policies: dict[str, RotationPolicy] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        """Load rotation policies from config file."""
        policy_file = self.metadata_dir / "policies.json"
        if policy_file.exists():
            try:
                data = json.loads(policy_file.read_text())
                for name, policy_data in data.items():
                    self.policies[name] = RotationPolicy(**policy_data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to load rotation policies: {e}")

    def _save_policies(self) -> None:
        """Save rotation policies to config file."""
        policy_file = self.metadata_dir / "policies.json"
        data = {name: policy.__dict__ for name, policy in self.policies.items()}
        policy_file.write_text(json.dumps(data, indent=2, default=str))

    def add_policy(self, policy: RotationPolicy) -> None:
        """Add or update a rotation policy."""
        self.policies[policy.name] = policy
        self._save_policies()

    def get_policy(self, name: str) -> RotationPolicy | None:
        """Get rotation policy for a secret."""
        return self.policies.get(name)

    def set_secret(self, name: str, value: str, policy: RotationPolicy | None = None) -> SecretMetadata:
        """Store a secret in macOS keychain with rotation metadata."""
        # Store in keychain
        subprocess.run([
            "security", "add-generic-password",
            "-s", self.service_name,
            "-a", name,
            "-w", value,
            "-U"
        ], check=True)

        # Create/update metadata
        now = datetime.now(UTC).isoformat()
        metadata = SecretMetadata(
            name=name,
            created_at=now,
            rotated_at=now,
            policy=policy,
        )

        if policy:
            if policy.max_age_days > 0:
                expires = datetime.now(UTC) + timedelta(days=policy.max_age_days)
                metadata.expires_at = expires.isoformat()

        self._save_metadata(metadata)
        logger.info(f"Secret '{name}' stored with rotation metadata")
        return metadata

    def get_secret(self, name: str) -> str | None:
        """Retrieve a secret from macOS keychain."""
        try:
            result = subprocess.run([
                "security", "find-generic-password",
                "-s", self.service_name,
                "-a", name,
                "-w"
            ], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def rotate_secret(self, name: str, new_value: str | None = None) -> SecretMetadata | None:
        """Rotate a secret, generating a new value if generator is configured."""
        metadata = self._load_metadata(name)
        if not metadata:
            logger.warning(f"No metadata found for secret '{name}'")
            return None

        policy = metadata.policy
        if not policy:
            logger.warning(f"No rotation policy for secret '{name}'")
            return None

        # Generate new value if not provided
        if new_value is None:
            if policy.generator:
                try:
                    result = subprocess.run(
                        policy.generator,
                        shell=True,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    new_value = result.stdout.strip()
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to generate new secret for '{name}': {e}")
                    return None
            else:
                logger.error(f"No generator configured for secret '{name}'")
                return None

        if not new_value:
            logger.error(f"Generated empty value for secret '{name}'")
            return None

        # Store new value
        self.set_secret(name, new_value)

        # Update metadata
        now = datetime.now(UTC).isoformat()
        metadata.rotated_at = now
        metadata.version += 1
        if policy.max_age_days > 0:
            expires = datetime.now(UTC) + timedelta(days=policy.max_age_days)
            metadata.expires_at = expires.isoformat()

        self._save_metadata(metadata)
        logger.info(f"Secret '{name}' rotated to version {metadata.version}")
        return metadata

    def check_rotation_needed(self) -> list[SecretMetadata]:
        """Check all managed secrets for rotation needs."""
        needed = []
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                metadata = json.loads(metadata_file.read_text())
                meta_obj = SecretMetadata(**metadata)
                if meta_obj.needs_rotation():
                    needed.append(meta_obj)
            except (json.JSONDecodeError, TypeError):
                continue
        return needed

    def rotate_all_needed(self) -> dict[str, SecretMetadata]:
        """Rotate all secrets that need rotation."""
        rotated = {}
        for metadata in self.check_rotation_needed():
            result = self.rotate_secret(metadata.name)
            if result:
                rotated[metadata.name] = result
        return rotated

    def _save_metadata(self, metadata: SecretMetadata) -> None:
        """Save secret metadata to file."""
        metadata_file = self.metadata_dir / f"{metadata.name}.json"
        data = metadata.__dict__
        # Convert policy to dict if present
        if metadata.policy:
            data['policy'] = metadata.policy.__dict__
        metadata_file.write_text(json.dumps(data, indent=2, default=str))

    def _load_metadata(self, name: str) -> SecretMetadata | None:
        """Load secret metadata from file."""
        metadata_file = self.metadata_dir / f"{name}.json"
        if not metadata_file.exists():
            return None
        try:
            data = json.loads(metadata_file.read_text())
            # Reconstruct policy if present
            if 'policy' in data and data['policy']:
                data['policy'] = RotationPolicy(**data['policy'])
            return SecretMetadata(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to load metadata for '{name}': {e}")
            return None

    def list_secrets(self) -> list[SecretMetadata]:
        """List all managed secrets with their metadata."""
        secrets = []
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                data = json.loads(metadata_file.read_text())
                if 'policy' in data and data['policy']:
                    data['policy'] = RotationPolicy(**data['policy'])
                secrets.append(SecretMetadata(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return sorted(secrets, key=lambda s: s.name)

    def delete_secret(self, name: str) -> bool:
        """Delete a secret from keychain and metadata."""
        try:
            subprocess.run([
                "security", "delete-generic-password",
                "-s", self.service_name,
                "-a", name
            ], check=True)
        except subprocess.CalledProcessError:
            return False

        metadata_file = self.metadata_dir / f"{name}.json"
        if metadata_file.exists():
            metadata_file.unlink()
        return True


def create_rotation_cli():
    """Create CLI for secret rotation management."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="wa secret-rotation")
    sub = parser.add_subparsers(dest="action", required=True)

    # Add policy
    add_policy = sub.add_parser("add-policy")
    add_policy.add_argument("name")
    add_policy.add_argument("--max-age", type=int, default=90)
    add_policy.add_argument("--warning", type=int, default=14)
    add_policy.add_argument("--auto-rotate", action="store_true")
    add_policy.add_argument("--generator", help="Command to generate new secret")

    # Set secret
    set_secret = sub.add_parser("set")
    set_secret.add_argument("name")
    set_secret.add_argument("value")
    set_secret.add_argument("--policy", help="Policy name to apply")

    # Rotate secret
    rotate = sub.add_parser("rotate")
    rotate.add_argument("name")
    rotate.add_argument("--value", help="New value (optional, uses generator if not provided)")

    # Check rotation
    check = sub.add_parser("check")

    # Rotate all needed
    rotate_all = sub.add_parser("rotate-all")

    # List
    sub.add_parser("list")

    # Delete
    delete = sub.add_parser("delete")
    delete.add_argument("name")

    args = parser.parse_args()

    manager = SecretRotationManager()

    if args.action == "add-policy":
        policy = RotationPolicy(
            name=args.name,
            max_age_days=args.max_age,
            warning_days=args.warning,
            auto_rotate=args.auto_rotate,
            generator=args.generator,
        )
        manager.add_policy(policy)
        print(f"Policy '{args.name}' added")

    elif args.action == "set":
        policy = manager.get_policy(args.policy) if args.policy else None
        manager.set_secret(args.name, args.value, policy)
        print(f"Secret '{args.name}' set")

    elif args.action == "rotate":
        result = manager.rotate_secret(args.name, args.value)
        if result:
            print(f"Secret '{args.name}' rotated to version {result.version}")
        else:
            print(f"Failed to rotate secret '{args.name}'")
            return 1

    elif args.action == "check":
        needed = manager.check_rotation_needed()
        if needed:
            print("Secrets needing rotation:")
            for meta in needed:
                days = meta.days_until_expiry()
                print(f"  {meta.name}: expires in {days} days (v{meta.version})")
        else:
            print("All secrets up to date")

    elif args.action == "rotate-all":
        rotated = manager.rotate_all_needed()
        print(f"Rotated {len(rotated)} secrets")
        for name, meta in rotated.items():
            print(f"  {name}: v{meta.version}")

    elif args.action == "list":
        secrets = manager.list_secrets()
        for meta in secrets:
            status = "EXPIRED" if meta.is_expired() else ("NEEDS ROTATION" if meta.needs_rotation() else "OK")
            days = meta.days_until_expiry()
            print(f"  {meta.name}: v{meta.version}, {status}, expires in {days} days")

    elif args.action == "delete":
        if manager.delete_secret(args.name):
            print(f"Secret '{args.name}' deleted")
        else:
            print(f"Failed to delete secret '{args.name}'")
            return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(create_rotation_cli())