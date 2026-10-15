"""Small command-line entry point."""

import argparse

from mini_sla_harness import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mini-SLA development scaffold")
    parser.add_argument("--version", action="version", version=f"mini-sla {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
