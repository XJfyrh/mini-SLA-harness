"""Small command-line entry point."""

import argparse
import json
import sqlite3
from pathlib import Path

from mini_sla_harness import __version__
from mini_sla_harness.demo import run_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mini-SLA development scaffold")
    parser.add_argument("--version", action="version", version=f"mini-sla {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run deterministic fake / SQLite smoke checks")
    demo.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    demo.add_argument("--json", action="store_true", help="Print only machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        report = run_demo(args.output_dir)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    else:
        print(f"Offline smoke demo: {report['status']} ({report['case_count']} cases)")
        print("Provider: deterministic-fake-v1")
        print("SQLite round-trip: passed")
        print(f"Database: {args.output_dir / 'demo.sqlite3'}")
        print(f"JSON result: {args.output_dir / 'result.json'}")
        print("Research effect: not evaluated")
    return 0
