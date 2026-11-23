"""Distributed tracing CLI commands."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from .base import Command, register_command
from auditor_toolkit.tracing import (
    init_tracing,
    init_tracing_from_env,
    get_tracer,
    is_tracing_enabled,
    TracedAuditContext,
)


class TracingCommand(Command):
    """Manage distributed tracing configuration."""

    name = "tracing"
    help = "Manage distributed tracing configuration"

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="tracing_command", required=True)

        # init subcommand
        init_parser = sub.add_parser("init", help="Initialize tracing")
        init_parser.add_argument(
            "--service-name",
            default="website-auditor",
            help="Service name for traces",
        )
        init_parser.add_argument(
            "--otlp-endpoint",
            help="OTLP endpoint (e.g., localhost:4317 or http://localhost:4318/v1/traces)",
        )
        init_parser.add_argument(
            "--otlp-protocol",
            choices=["http", "grpc"],
            default="http",
            help="OTLP protocol",
        )
        init_parser.add_argument(
            "--console",
            action="store_true",
            help="Export to console",
        )
        init_parser.add_argument(
            "--sample-rate",
            type=float,
            default=1.0,
            help="Sampling rate (0.0 to 1.0)",
        )

        # status subcommand
        status_parser = sub.add_parser("status", help="Show tracing status")

        # env subcommand
        env_parser = sub.add_parser("env", help="Initialize from environment variables")
        env_parser.add_argument(
            "--service-name",
            default="website-auditor",
            help="Service name for traces",
        )

        # test subcommand
        test_parser = sub.add_parser("test", help="Test tracing by creating sample spans")
        test_parser.add_argument(
            "--run-id",
            default="test-run",
            help="Run ID for test audit",
        )
        test_parser.add_argument(
            "--url",
            default="https://example.com",
            help="URL for test audit",
        )
        test_parser.add_argument(
            "--profile",
            default="default",
            help="Profile for test audit",
        )

    def execute(self, args: Namespace) -> int:
        if args.tracing_command == "init":
            return self._cmd_init(args)
        elif args.tracing_command == "status":
            return self._cmd_status(args)
        elif args.tracing_command == "env":
            return self._cmd_env(args)
        elif args.tracing_command == "test":
            return self._cmd_test(args)
        return 1

    def _cmd_init(self, args: Namespace) -> int:
        tracer = init_tracing(
            service_name=args.service_name,
            otlp_endpoint=args.otlp_endpoint,
            otlp_protocol=args.otlp_protocol,
            console_export=args.console,
            sample_rate=args.sample_rate,
        )
        if tracer:
            print(f"Tracing initialized for service: {args.service_name}")
            if args.otlp_endpoint:
                print(f"  OTLP endpoint: {args.otlp_endpoint} ({args.otlp_protocol})")
            if args.console or not args.otlp_endpoint:
                print("  Console export: enabled")
            print(f"  Sample rate: {args.sample_rate}")
        else:
            print("Tracing initialization failed")
            return 1
        return 0

    def _cmd_status(self, args: Namespace) -> int:
        print("Tracing Status:")
        print(f"  Enabled: {is_tracing_enabled()}")
        tracer = get_tracer()
        print(f"  Tracer available: {tracer is not None}")
        return 0

    def _cmd_env(self, args: Namespace) -> int:
        import os
        os.environ["WA_TRACING_ENABLED"] = "true"
        os.environ["WA_TRACING_SERVICE_NAME"] = args.service_name
        tracer = init_tracing_from_env()
        if tracer:
            print("Tracing initialized from environment variables")
        else:
            print("Tracing not enabled (WA_TRACING_ENABLED != 'true')")
            return 1
        return 0

    def _cmd_test(self, args: Namespace) -> int:
        from auditor_toolkit.tracing import audit_span, check_span, http_span, add_span_event

        # Initialize with console export
        init_tracing(
            service_name="website-auditor-test",
            console_export=True,
            sample_rate=1.0,
        )

        print(f"Testing tracing with run_id={args.run_id}, url={args.url}")

        # Test audit span
        with audit_span(args.run_id, args.url, args.profile) as span:
            add_span_event(span, "audit_started", {"profile": args.profile})

            # Test check spans
            for check_name in ["fetch", "page", "schema", "headers", "hygiene"]:
                with check_span(check_name, args.run_id, args.url) as check_span_obj:
                    add_span_event(check_span_obj, "check_started", {"check": check_name})
                    # Simulate some work
                    add_span_event(check_span_obj, "check_completed", {"findings_count": 2})

            # Test HTTP span
            with http_span("GET", args.url, "example.com") as http_span_obj:
                add_span_event(http_span_obj, "http_request", {"method": "GET"})
                set_span_attribute(http_span_obj, "http.status_code", 200)

            add_span_event(span, "audit_completed", {"status": "ok"})

        print("Test spans created successfully")
        return 0


# Helper function moved to tracing module
def set_span_attribute(span, key, value):
    if span is not None:
        span.set_attribute(key, value)


register_command(TracingCommand())