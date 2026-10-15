"""Observe development and Windows host prerequisites; container probes remain separate."""

import argparse
import platform
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evidence import Evidence

ROOT = Path(__file__).resolve().parents[1]


def wal_reset_fixed(version: tuple[int, ...]) -> bool:
    return (
        version >= (3, 51, 3)
        or (version[:2] == (3, 44) and version >= (3, 44, 6))
        or (version[:2] == (3, 50) and version >= (3, 50, 7))
    )


def probe(root: Path) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = [
        {
            "name": "python",
            "required_for": "development",
            "observed": platform.python_version(),
            "status": "passed" if sys.version_info[:2] == (3, 14) else "failed",
        },
        {
            "name": "target_os",
            "required_for": "target",
            "observed": platform.system(),
            "status": "passed" if sys.platform == "win32" else "failed",
        },
        {
            "name": "sqlite_wal_reset_fix",
            "required_for": "target",
            "observed": sqlite3.sqlite_version,
            "status": "passed" if wal_reset_fixed(sqlite3.sqlite_version_info) else "failed",
        },
    ]
    try:
        temporary = root / "artifacts" / "tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary, prefix="doctor-") as name:
            path = Path(name) / "probe.sqlite3"
            with closing(sqlite3.connect(path)) as connection, connection:
                mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
                connection.execute("CREATE TABLE probe(value TEXT)")
                connection.execute("INSERT INTO probe VALUES (?)", ("persisted",))
            with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as reopened:
                row = reopened.execute("SELECT value FROM probe").fetchone()
                integrity = reopened.execute("PRAGMA integrity_check").fetchone()
            if mode != ("wal",) or row != ("persisted",) or integrity != ("ok",):
                raise RuntimeError(f"Unexpected SQLite result: {mode}, {row}, {integrity}")
        observations.append(
            {
                "name": "sqlite_wal_round_trip",
                "required_for": "development",
                "observed": {"mode": mode, "row": row, "integrity": integrity},
                "status": "passed",
            }
        )
    except (OSError, sqlite3.Error, RuntimeError) as error:
        observations.append(
            {
                "name": "sqlite_wal_round_trip",
                "required_for": "development",
                "status": "failed",
                "error": str(error),
            }
        )
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    recording = Evidence(ROOT, "doctor", args.evidence_dir)
    observations = probe(ROOT)
    recording.report.update(
        profile="target-prerequisites" if args.target else "development",
        observations=observations,
        pending_runtime_probes=[
            "docker_desktop_wsl2_backend",
            "container_permissions",
            "local_control_pipe_access",
            "cross_process_lock",
            "host_and_container_cancellation",
            "windows_artifact_publication",
            "measurement_calibration",
        ],
    )
    for item in observations:
        print(
            f"{item['name']} ({item['required_for']}): {item['status']}; "
            f"{item.get('observed', item.get('error'))}"
        )
    failed = [
        item
        for item in observations
        if item["status"] != "passed" and (args.target or item["required_for"] == "development")
    ]
    return recording.finish("Required environment probes failed" if failed else None)


if __name__ == "__main__":
    raise SystemExit(main())
