"""Build a wheel and verify its real installed CLI in a fresh, disposable environment."""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
from contextlib import closing
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evidence import Evidence

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "deterministic-fake-v1"
EXPECTED_ROWS = [
    ("sort", "Sort 3, 1 and 2 ascending.", "1,2,3", PROVIDER),
    ("sum", "Add 2, 3 and 5.", "10", PROVIDER),
    ("unicode", "Echo: \u4f60\u597d\uff0cMini-SLA", "\u4f60\u597d\uff0cMini-SLA", PROVIDER),
]
EXPECTED_RECORDS = [
    dict(zip(("case_id", "prompt", "response", "provider"), row, strict=True))
    for row in EXPECTED_ROWS
]
EXPECTED_REPORT = {
    "schema_version": 1,
    "scope": "development-smoke",
    "status": "ok",
    "provider": PROVIDER,
    "case_count": 3,
    "sqlite_round_trip": "passed",
    "research_effect": "not_evaluated",
    "records": EXPECTED_RECORDS,
}
PROBE = """
import json, sys
from dataclasses import asdict
from importlib.metadata import distribution
from pathlib import Path
import mini_sla_harness
from mini_sla_harness.store import load_records
dist = distribution('mini-sla-harness')
print(json.dumps({
    'package_path': str(Path(mini_sla_harness.__file__).resolve()),
    'prefix': sys.prefix,
    'version': dist.version,
    'entry': next(ep.value for ep in dist.entry_points if ep.name == 'mini-sla'),
    'records': [asdict(record) for record in load_records(Path(sys.argv[1]))],
}, ensure_ascii=True))
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def rows_from_disk(database: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        require(
            connection.execute("PRAGMA integrity_check").fetchone() == ("ok",), "SQLite integrity"
        )
        require(connection.execute("PRAGMA journal_mode").fetchone() == ("wal",), "SQLite WAL")
        return [
            tuple(row)
            for row in connection.execute(
                "SELECT case_id, prompt, response, provider FROM demo_records ORDER BY case_id"
            ).fetchall()
        ]


def accept_wheel(root: Path, recording: Evidence) -> dict[str, object]:
    evidence = recording.directory
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP", "TMPDIR"}
    }
    environment.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1")

    def invoke(
        label: str, command: list[str], cwd: Path, expected_exit: int = 0
    ) -> subprocess.CompletedProcess[str]:
        return recording.run(
            label, command, cwd=cwd, environment=environment, expected_exit=expected_exit
        )

    with (root / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    temp_root = root / "artifacts" / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-check-", dir=temp_root) as name:
        workspace = Path(name)
        built = workspace / "built"
        invoke(
            "build",
            [
                sys.executable,
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "wheel",
                "--no-index",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(built),
                ".",
            ],
            root,
        )
        wheels = list(built.glob("*.whl"))
        require(len(wheels) == 1, "Build must produce exactly one wheel")
        wheel = wheels[0]
        clean = workspace / "venv"
        invoke("create-environment", [sys.executable, "-m", "venv", str(clean)], root)
        python = clean / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cli = clean / ("Scripts/mini-sla.exe" if os.name == "nt" else "bin/mini-sla")
        outside = workspace / "outside-source"
        outside.mkdir()
        (outside / "mini_sla_harness.py").write_text(
            "raise RuntimeError('cwd must not supply the runtime package')\n", encoding="utf-8"
        )
        invoke(
            "install",
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            outside,
        )
        version = invoke("version", [str(cli), "--version"], outside)
        require(
            version.stdout.strip() == f"mini-sla {project['version']}", "Installed version mismatch"
        )
        help_result = invoke("help", [str(cli), "--help"], outside)
        require("demo" in help_result.stdout, "Installed help lacks demo")
        output = outside / "\u6570\u636e space #1"
        human = invoke("demo", [str(cli), "demo", "--output-dir", str(output)], outside)
        require("3 cases" in human.stdout, "Human summary does not describe the demo")
        database = output / "demo.sqlite3"
        actual_rows = rows_from_disk(database)
        require(actual_rows == EXPECTED_ROWS, "Persisted SQLite values differ from known fixtures")
        result_path = output / "result.json"
        original_json = result_path.read_bytes()
        require(
            json.loads(original_json) == EXPECTED_REPORT, "Exported JSON differs from known result"
        )
        restarted = invoke(
            "restart-demo", [str(cli), "demo", "--output-dir", str(output), "--json"], outside
        )
        require(json.loads(restarted.stdout) == EXPECTED_REPORT, "Restarted CLI JSON mismatch")
        require(
            rows_from_disk(database) == EXPECTED_ROWS, "Restart changed or duplicated stored rows"
        )
        require(
            result_path.read_bytes() == original_json, "Restart changed deterministic JSON bytes"
        )
        probe = json.loads(
            invoke("restart-read", [str(python), "-I", "-c", PROBE, str(database)], outside).stdout
        )
        package_path = Path(probe["package_path"])
        require(
            Path(probe["prefix"]).resolve() == clean.resolve(), "Probe escaped clean environment"
        )
        require(
            package_path.is_relative_to(clean), "Runtime imported outside installed environment"
        )
        require(not package_path.is_relative_to(root / "src"), "Runtime imported the source tree")
        require(probe["entry"] == project["scripts"]["mini-sla"], "Installed entry point differs")
        require(probe["version"] == project["version"], "Installed distribution metadata differs")
        require(
            probe["records"] == EXPECTED_RECORDS, "Fresh process could not read persisted records"
        )
        invoke("unknown-command", [str(cli), "unknown"], outside, expected_exit=2)
        protected = outside / "existing-file"
        protected.write_bytes(b"preserve existing file")
        invoke("invalid-output", [str(cli), "demo", "--output-dir", str(protected)], outside, 1)
        require(
            protected.read_bytes() == b"preserve existing file", "CLI overwrote an existing file"
        )
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "UPDATE demo_records SET response = 'external conflict' WHERE case_id = 'sum'"
            )
        conflicting_rows = rows_from_disk(database)
        invoke("database-conflict", [str(cli), "demo", "--output-dir", str(output)], outside, 1)
        require(
            rows_from_disk(database) == conflicting_rows, "Conflict handling changed existing data"
        )
        require(result_path.read_bytes() == original_json, "Failed demo rewrote JSON")
        for label in ("unknown-command", "invalid-output", "database-conflict"):
            require(
                "Traceback" not in (evidence / f"{label}.log").read_text(encoding="utf-8"),
                f"{label} leaked an unhandled traceback",
            )
        destination = root / "dist" / wheel.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(wheel, destination)
        (evidence / "demo-result.json").write_bytes(original_json)
        result: dict[str, object] = {
            "wheel": str(destination),
            "wheel_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "version": project["version"],
            "installed_package_path": str(package_path),
            "installed_cwd": str(outside),
            "database_rows": actual_rows,
            "demo_json_sha256": hashlib.sha256(original_json).hexdigest(),
            "restart_read_passed": True,
            "source_import_excluded": True,
            "failure_exits": {"unknown-command": 2, "invalid-output": 1, "database-conflict": 1},
        }
    require(not workspace.exists(), "Temporary installed environment was not cleaned up")
    result["temporary_environment_removed"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    recording = Evidence(ROOT, "package-check", args.evidence_dir)
    error_message: str | None = None
    try:
        recording.report.update(accept_wheel(ROOT, recording))
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as error:
        error_message = str(error) or "Interrupted"
        print(f"Package acceptance failed: {error_message}", file=sys.stderr)
    return recording.finish(error_message)


if __name__ == "__main__":
    raise SystemExit(main())
