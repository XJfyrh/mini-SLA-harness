"""Portable developer entry points. Run with Python; shell activation is unnecessary."""

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

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


def check() -> None:
    run([str(PYTHON), "-m", "ruff", "format", "--check", "."])
    run([str(PYTHON), "-m", "ruff", "check", "."])
    run([str(PYTHON), "-m", "mypy"])
    run([str(PYTHON), "scripts/repo_check.py"])
    run([str(PYTHON), "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([str(PYTHON), "-m", "pip", "--isolated", "check"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bootstrap", "check", "demo"])
    args = parser.parse_args()
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
                check()
            else:
                run([str(PYTHON), "-m", "mini_sla_harness", "demo"])
    except subprocess.CalledProcessError as error:
        return error.returncode
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
