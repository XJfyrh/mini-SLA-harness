"""Small command-line entry point."""

import argparse
import json
import sqlite3
import uuid
from pathlib import Path

from mini_sla_harness import __version__
from mini_sla_harness.contracts import TaskSpec
from mini_sla_harness.demo import run_demo
from mini_sla_harness.m0 import run_acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mini-SLA development scaffold")
    parser.add_argument("--version", action="version", version=f"mini-sla {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run deterministic fake / SQLite smoke checks")
    demo.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    demo.add_argument("--json", action="store_true", help="Print only machine-readable JSON")
    task = commands.add_parser("task", help="Validate a JSON TaskSpec")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    validate = task_commands.add_parser("validate")
    validate.add_argument("path", type=Path)
    acceptance = commands.add_parser("m0-check", help="Run offline protocol acceptance")
    acceptance.add_argument("--output-dir", type=Path)
    acceptance.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "task":
            spec = TaskSpec.load(args.path)
            print(json.dumps({"status": "valid", "task_spec_hash": spec.digest}, sort_keys=True))
            return 0
        if args.command == "m0-check":
            output = args.output_dir or Path("artifacts/m0") / uuid.uuid4().hex
            acceptance_report = run_acceptance(output)
            if args.json:
                print(json.dumps(acceptance_report, sort_keys=True))
            else:
                print(f"M0 offline acceptance: {acceptance_report['status']}")
                print(f"Report: {output / 'report.json'}")
            return 0 if acceptance_report["status"] == "passed" else 1
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
