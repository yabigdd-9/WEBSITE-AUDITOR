import argparse
import json

from .layer import status
from .server import run_http, run_mcp, serve_omniroute_mcp


def main():
    parser = argparse.ArgumentParser(prog="python -m integrations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    http = sub.add_parser("serve")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", type=int, default=8091)
    http.add_argument("--no-worker", action="store_true")
    sub.add_parser("mcp")
    sub.add_parser("omniroute-mcp")
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "mcp":
        run_mcp()
    elif args.command == "omniroute-mcp":
        serve_omniroute_mcp()
    else:
        run_http(host=args.host, port=args.port, worker=not args.no_worker)


if __name__ == "__main__":
    main()
