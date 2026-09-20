"""CLI for the safe-default action engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .actions.executor import ActionExecutor


def emit(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def executor(args) -> ActionExecutor:
    return ActionExecutor(output_dir=args.output_dir, config_path=args.config)


def cmd_init(args) -> None:
    ex = executor(args)
    emit({"status": "initialized", **ex.status_summary(), "output_dir": str(ex.output_dir)})


def cmd_demo(args) -> None:
    emit({"actions": [a.to_dict() for a in executor(args).propose_demo(args.domain)]})


def cmd_propose(args) -> None:
    ex = executor(args)
    emit({"created": ex.propose_from_remediations(args.from_remediations), **ex.status_summary()})


def cmd_dry_run(args) -> None:
    emit(executor(args).dry_run_all())


def cmd_approve(args) -> None:
    emit(executor(args).approve(args.id, actor=args.approver, reason=args.reason))


def cmd_reject(args) -> None:
    emit(executor(args).reject(args.id, actor=args.approver, reason=args.reason))


def cmd_authorize(args) -> None:
    emit(executor(args).authorize(args.domain, scopes=args.scope, actor=args.actor, note=args.note))


def cmd_execute(args) -> None:
    emit(executor(args).execute(args.id))


def cmd_rollback(args) -> None:
    emit(executor(args).rollback(args.id))


def cmd_status(args) -> None:
    emit(executor(args).status_summary())


def cmd_list(args) -> None:
    emit({"actions": [a.to_dict() for a in executor(args).actions.all()]})


def cmd_pause(args) -> None:
    ex = executor(args)
    ex.kill_switch.pause(args.actor)
    ex.audit_log.append("kill_switch_enabled", actor=args.actor)
    emit(ex.status_summary())


def cmd_resume(args) -> None:
    ex = executor(args)
    ex.kill_switch.resume()
    ex.audit_log.append("kill_switch_disabled", actor=args.actor)
    emit(ex.status_summary())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wa", description="Website Auditor action engine")
    parser.add_argument("--config", default="action-policy.json")
    parser.add_argument("--output-dir", default="outputs/actions")
    sub = parser.add_subparsers(dest="command", required=True)

    actions = sub.add_parser("actions")
    action_sub = actions.add_subparsers(dest="actions_command", required=True)

    p = action_sub.add_parser("init"); p.set_defaults(func=cmd_init)
    p = action_sub.add_parser("demo"); p.add_argument("--domain", default="example.co.nz"); p.set_defaults(func=cmd_demo)
    p = action_sub.add_parser("propose"); p.add_argument("--from-remediations", default="outputs/remediations"); p.set_defaults(func=cmd_propose)
    p = action_sub.add_parser("dry-run"); p.set_defaults(func=cmd_dry_run)
    p = action_sub.add_parser("approve"); p.add_argument("--id", required=True); p.add_argument("--approver", default="local_user"); p.add_argument("--reason", default=""); p.set_defaults(func=cmd_approve)
    p = action_sub.add_parser("reject"); p.add_argument("--id", required=True); p.add_argument("--approver", default="local_user"); p.add_argument("--reason", default=""); p.set_defaults(func=cmd_reject)
    p = action_sub.add_parser("authorize"); p.add_argument("--domain", required=True); p.add_argument("--scope", action="append", required=True); p.add_argument("--actor", default="local_user"); p.add_argument("--note", default=""); p.set_defaults(func=cmd_authorize)
    p = action_sub.add_parser("execute"); p.add_argument("--id", required=True); p.set_defaults(func=cmd_execute)
    p = action_sub.add_parser("rollback"); p.add_argument("--id", required=True); p.set_defaults(func=cmd_rollback)
    p = action_sub.add_parser("status"); p.set_defaults(func=cmd_status)
    p = action_sub.add_parser("list"); p.set_defaults(func=cmd_list)
    p = action_sub.add_parser("pause"); p.add_argument("--actor", default="local_user"); p.set_defaults(func=cmd_pause)
    p = action_sub.add_parser("resume"); p.add_argument("--actor", default="local_user"); p.set_defaults(func=cmd_resume)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
