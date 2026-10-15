"""Portable developer entry points. Run with Python; shell activation is unnecessary."""

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evidence import CommandFailure, Evidence

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command: list[str]) -> None:
    print("+ " + subprocess.list2cmdline(command), flush=True)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def bootstrap() -> None:
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Use Python 3.14 to bootstrap this project.")
    if not PYTHON.is_file():
        if VENV.exists():
            raise RuntimeError(".venv exists without its Python executable; inspect it first.")
        venv.EnvBuilder(with_pip=True).create(VENV)
    run([str(PYTHON), "-m", "ensurepip", "--upgrade"])
    run(
        [
            str(PYTHON),
            "-m",
            "pip",
            "--isolated",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "install",
            "--index-url",
            "https://pypi.org/simple",
            "--only-binary=:all:",
            "--require-hashes",
            "--no-deps",
            "-r",
            "requirements-dev.lock",
        ]
    )
    run(
        [
            str(PYTHON),
            "-m",
            "pip",
            "--isolated",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "install",
            "--no-index",
            "--no-build-isolation",
            "--no-deps",
            "-e",
            ".",
        ]
    )
    run([str(PYTHON), "-m", "pip", "--isolated", "check"])


def run_checks(evidence: Evidence, commands: list[tuple[str, list[str], float]]) -> int:
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1")
    error: str | None = None
    try:
        for name, command, timeout in commands:
            try:
                evidence.run(
                    name,
                    command,
                    timeout=timeout,
                    environment=environment,
                    echo=name in {"doctor", "demo"},
                )
            except CommandFailure:
                continue  # Independent checks still provide useful feedback.
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as failure:
        error = str(failure) or "Interrupted"
    return evidence.finish(error)


def check() -> int:
    evidence = Evidence(ROOT, "check")
    python = str(PYTHON)
    return run_checks(
        evidence,
        [
            (
                "doctor",
                [python, "scripts/doctor.py", "--evidence-dir", str(evidence.directory / "doctor")],
                30,
            ),
            ("format", [python, "-m", "ruff", "format", "--check", "."], 30),
            ("lint", [python, "-m", "ruff", "check", "."], 30),
            ("types", [python, "-m", "mypy"], 60),
            ("repository", [python, "scripts/repo_check.py"], 30),
            ("tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"], 120),
            ("dependencies", [python, "-m", "pip", "--isolated", "check"], 30),
            (
                "package",
                [
                    python,
                    "scripts/package_check.py",
                    "--evidence-dir",
                    str(evidence.directory / "package"),
                ],
                180,
            ),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["bootstrap", "check", "demo", "package-check", "doctor"]
    )
    parser.add_argument(
        "--target", action="store_true", help="Check Linux runtime prerequisites (doctor only)"
    )
    args = parser.parse_args()
    if args.target and args.command != "doctor":
        parser.error("--target requires doctor")
    try:
        temp_root = ROOT / "artifacts" / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        for variable in ("TEMP", "TMP", "TMPDIR"):
            os.environ[variable] = str(temp_root)
        tempfile.tempdir = None
        if args.command == "bootstrap":
            bootstrap()
        else:
            if not PYTHON.is_file():
                raise RuntimeError("Run: python scripts/dev.py bootstrap")
            if args.command == "check":
                return check()
            elif args.command == "package-check":
                run([str(PYTHON), "scripts/package_check.py"])
            elif args.command == "doctor":
                run([str(PYTHON), "scripts/doctor.py", *(["--target"] if args.target else [])])
            else:
                evidence = Evidence(ROOT, "demo")
                return run_checks(
                    evidence, [("demo", [str(PYTHON), "-m", "mini_sla_harness", "demo"], 30)]
                )
    except subprocess.CalledProcessError as error:
        return error.returncode
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
