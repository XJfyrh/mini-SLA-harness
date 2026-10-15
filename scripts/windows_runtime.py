"""Prepare and verify the pinned, repository-local Windows x64 source-test runtime."""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "windows-python-3.14.8-sqlite-3.54.0"
# Official release checksums; updating these is an explicit environment change.
ARCHIVES = (
    (
        "https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-amd64.zip",
        "sha256",
        "a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310",
    ),
    (
        "https://www.sqlite.org/2026/sqlite-dll-win-x64-3540000.zip",
        "sha3_256",
        "f5fb500c73a3afd89976386bb8e4fdc8b5b65c052e187fb1ada1f5de034cd45b",
    ),
)
PATH_CONFIG = "python314.zip\n.\n../../../src\n../../..\n"


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def archive(cache: Path, source: tuple[str, str, str]) -> Path:
    url, algorithm, expected = source
    destination = cache / url.rsplit("/", 1)[1]
    if not destination.exists():
        # Interrupted downloads never become cache entries. Keep existing files on failure.
        with tempfile.TemporaryDirectory(dir=cache, prefix="download-") as temporary:
            pending = Path(temporary) / "archive.zip"
            print(f"Download: {url}", flush=True)
            with urllib.request.urlopen(url, timeout=30) as response, pending.open("wb") as output:
                shutil.copyfileobj(response, output)
            if file_hash(pending, algorithm) != expected:
                raise RuntimeError(f"Archive checksum mismatch: {url}")
            pending.replace(destination)
    if file_hash(destination, algorithm) != expected:
        raise RuntimeError(f"Cached archive checksum mismatch; inspect: {destination}")
    return destination


def runtime_directory(root: Path) -> Path:
    return root / "artifacts" / "runtime" / NAME


def verified_python(root: Path) -> Path:
    directory = runtime_directory(root)
    try:
        manifest = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
        if manifest["archives"] != [list(item) for item in ARCHIVES]:
            raise ValueError("Runtime lock differs")
        files = manifest["files"]
        if not isinstance(files, dict) or not {
            "python.exe",
            "python314.dll",
            "python314.zip",
            "_sqlite3.pyd",
            "sqlite3.dll",
            "python314._pth",
        }.issubset(files):
            raise ValueError("Runtime manifest is incomplete")
        for name, expected in files.items():
            if Path(name).name != name or file_hash(directory / name) != expected:
                raise ValueError(f"Runtime file changed: {name}")
        if (directory / "python314._pth").read_text(encoding="utf-8") != PATH_CONFIG:
            raise ValueError("Source import paths differ")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "Pinned Windows runtime missing or changed; "
            "run python scripts/dev.py runtime-bootstrap. "
            f"Existing directories are preserved: {directory}; {error}"
        ) from error
    return directory / "python.exe"


def prepare(root: Path) -> Path:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The pinned runtime requires Windows x64.")
    directory = runtime_directory(root)
    if directory.exists():
        return verified_python(root)
    parent = directory.parent
    cache = parent / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    python_archive, sqlite_archive = [archive(cache, item) for item in ARCHIVES]
    # Moving a populated Python directory fails on this Windows host. Publish readiness
    # through the final manifest instead; interrupted directories are preserved and refused.
    directory.mkdir()
    with zipfile.ZipFile(python_archive) as bundle:
        bundle.extractall(directory)  # Only the checksum-verified official archive is extracted.
    with zipfile.ZipFile(sqlite_archive) as bundle:
        (directory / "sqlite3.dll").write_bytes(bundle.read("sqlite3.dll"))
    (directory / "python314._pth").write_text(PATH_CONFIG, encoding="utf-8", newline="\n")
    files = {item.name: file_hash(item) for item in directory.iterdir() if item.is_file()}
    (directory / "runtime.json").write_text(
        json.dumps({"archives": ARCHIVES, "files": files}, indent=2) + "\n",
        encoding="utf-8",
    )
    return verified_python(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bootstrap", "check"])
    args = parser.parse_args()
    try:
        python = prepare(ROOT) if args.command == "bootstrap" else verified_python(ROOT)
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import json,platform,sqlite3,sys; "
                "assert platform.python_version() == '3.14.8'; "
                "assert sqlite3.sqlite_version == '3.54.0'; "
                "print(json.dumps(dict(python=platform.python_version(), "
                "sqlite=sqlite3.sqlite_version, executable=sys.executable)))",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(result.stdout, end="")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
