"""Append a decision and its evidence to a single-writer UTF-8 TSV log."""

import argparse
import csv
import io
import sys
from datetime import UTC, datetime
from pathlib import Path

FIELDS = ("ts", "run_id", "phase", "decision", "why", "evidence", "result")


def clean(value: str) -> str:
    value = value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    if not value:
        raise ValueError("All fields must contain text")
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def read_rows(path: Path) -> list[list[str]]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return []
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise ValueError("Log has an incomplete final line; preserve it and use a new log")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8")), delimiter="\t", strict=True))
    if rows[0] != list(FIELDS):
        raise ValueError("Log header does not match the decision log format")
    for number, row in enumerate(rows[1:], 2):
        if len(row) != len(FIELDS) or any(
            not value.strip() or any(char in value for char in "\t\r\n") for value in row
        ):
            raise ValueError(f"Log row {number} is malformed; preserve it and use a new log")
    return rows


def append(path: Path, values: list[str]) -> int:
    cells = [clean(value) for value in values]
    rows = read_rows(path)
    if (len(rows) < 2 or rows[-1][1] != cells[0]) and cells[1] != "start":
        raise ValueError("The first row of a session or handoff must use --phase start")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    if not rows:
        writer.writerow(FIELDS)
    writer.writerow([datetime.now(UTC).isoformat(timespec="microseconds"), *cells])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(buffer.getvalue().encode("utf-8"))
    return max(1, len(rows)) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile", type=Path)
    parser.add_argument("--run", required=True, dest="run_id")
    for field in FIELDS[2:]:
        parser.add_argument(f"--{field}", required=True)
    arguments = parser.parse_args(argv)
    values = [getattr(arguments, field) for field in FIELDS[1:]]
    try:
        line = append(arguments.logfile, values)
    except (OSError, ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"{arguments.logfile}:{line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
