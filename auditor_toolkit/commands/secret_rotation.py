"""Secret rotation command implementation."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from auditor_toolkit.secret_rotation import RotationPolicy, SecretRotationManager

from .base import Command, register_command


class SecretRotationCommand(Command):
    """Manage secret rotation policies."""

    name = "secret-rotation"
    help = "Manage secret rotation policies"

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="rotation_action", required=True)

        # add-policy
        add_policy = sub.add_parser("add-policy")
        add_policy.add_argument("name")
        add_policy.add_argument("--max-age", type=int, default=90)
        add_policy.add_argument("--warning", type=int, default=14)
        add_policy.add_argument("--auto-rotate", action="store_true")
        add_policy.add_argument("--generator", help="Command to generate new secret")

        # set
        set_secret = sub.add_parser("set")
        set_secret.add_argument("name")
        set_secret.add_argument("value")
        set_secret.add_argument("--policy", help="Policy name to apply")

        # rotate
        rotate = sub.add_parser("rotate")
        rotate.add_argument("name")
        rotate.add_argument("--value", help="New value (optional, uses generator if not provided)")

        # check
        sub.add_parser("check")

        # rotate-all
        sub.add_parser("rotate-all")

        # list
        sub.add_parser("list")

        # delete
        delete = sub.add_parser("delete")
        delete.add_argument("name")

    def execute(self, args: Namespace) -> int:
        manager = SecretRotationManager()

        if args.rotation_action == "add-policy":
            policy = RotationPolicy(
                name=args.name,
                max_age_days=args.max_age,
                warning_days=args.warning,
                auto_rotate=args.auto_rotate,
                generator=args.generator,
            )
            manager.add_policy(policy)
            print(f"Policy '{args.name}' added")
            return 0

        elif args.rotation_action == "set":
            policy = manager.get_policy(args.policy) if args.policy else None
            manager.set_secret(args.name, args.value, policy)
            print(f"Secret '{args.name}' set")
            return 0

        elif args.rotation_action == "rotate":
            result = manager.rotate_secret(args.name, args.value)
            if result:
                print(f"Secret '{args.name}' rotated to version {result.version}")
                return 0
            else:
                print(f"Failed to rotate secret '{args.name}'")
                return 1

        elif args.rotation_action == "check":
            needed = manager.check_rotation_needed()
            if needed:
                print("Secrets needing rotation:")
                for meta in needed:
                    days = meta.days_until_expiry()
                    print(f"  {meta.name}: expires in {days} days (v{meta.version})")
            else:
                print("All secrets up to date")
            return 0

        elif args.rotation_action == "rotate-all":
            rotated = manager.rotate_all_needed()
            print(f"Rotated {len(rotated)} secrets")
            for name, meta in rotated.items():
                print(f"  {name}: v{meta.version}")
            return 0

        elif args.rotation_action == "list":
            secrets = manager.list_secrets()
            for meta in secrets:
                status = "EXPIRED" if meta.is_expired() else ("NEEDS ROTATION" if meta.needs_rotation() else "OK")
                days = meta.days_until_expiry()
                print(f"  {meta.name}: v{meta.version}, {status}, expires in {days} days")
            return 0

        elif args.rotation_action == "delete":
            if manager.delete_secret(args.name):
                print(f"Secret '{args.name}' deleted")
                return 0
            else:
                print(f"Failed to delete secret '{args.name}'")
                return 1

        return 1


register_command(SecretRotationCommand())
