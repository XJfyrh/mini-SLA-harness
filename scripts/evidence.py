"""Record commands and observed outcomes, including incomplete and failed runs."""

import hashlib
import json
import os
import platform
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


def source_state(root: Path) -> dict[str, object]:
    """Fingerprint Git source contents, including untracked, non-ignored files."""

    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, check=True, timeout=15
        ).stdout

    try:
        actual_root = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
        if actual_root != root.resolve():
            return {"status": "unavailable", "error": "Evidence root is not the Git worktree root"}
        head = git("rev-parse", "HEAD").decode().strip()
        paths = sorted(
            set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0"))
        )
        digest = hashlib.sha256()
        for name in filter(None, paths):
            path = root / os.fsdecode(name)
            digest.update(name + b"\0")
            if path.is_symlink():
                value = b"symlink:" + os.fsencode(os.readlink(path))
            elif not path.exists():
                value = b"deleted"
            else:
                value = b"file:" + hashlib.sha256(path.read_bytes()).digest()
            digest.update(value + b"\0")
        return {"status": "observed", "head": head, "content_sha256": digest.hexdigest()}
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "unavailable", "error": str(error)}


class CommandFailure(RuntimeError):
    """A command did not produce its expected exit status."""


def terminate_tree(pid: int) -> dict[str, object]:
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": os.fsdecode(result.stdout),
            "stderr": os.fsdecode(result.stderr),
        }
    # Nested check runners start their own sessions; killing only the root group
    # would leave these descendants running after the outer timeout.
    descendants = [pid]
    try:
        snapshot = subprocess.run(
            ["ps", "-e", "-o", "pid=,ppid="],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        parents: dict[int, list[int]] = {}
        for row in snapshot.stdout.splitlines():
            child, parent = map(int, row.split())
            parents.setdefault(parent, []).append(child)
        for parent in descendants:
            descendants.extend(parents.get(parent, []))
    finally:
        for child in descendants:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return {"signalled_pids": descendants}


class Evidence:
    def __init__(self, root: Path, kind: str, directory: Path | None = None) -> None:
        self.root = root
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        self.directory = directory or (
            root / "artifacts" / "verification" / f"{kind}-{stamp}-{uuid.uuid4().hex[:8]}"
        )
        self.directory.mkdir(parents=True, exist_ok=False)
        self.commands: list[dict[str, object]] = []
        self.report: dict[str, object] = {
            "schema_version": 1,
            "kind": kind,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "environment": {
                "python": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
            },
            "source_start": source_state(root),
            "commands": self.commands,
        }
        self.save()
        print(f"Evidence: {self.directory / 'summary.json'}", flush=True)

    def save(self) -> None:
        temporary = self.directory / "summary.tmp"
        temporary.write_text(
            json.dumps(self.report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.directory / "summary.json")

    def run(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        expected_exit: int = 0,
        timeout: float = 60,
        echo: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        directory = cwd or self.root
        step: dict[str, object] = {
            "name": name,
            "command": command,
            "cwd": str(directory),
            "expected_exit": expected_exit,
            "timeout_seconds": timeout,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "exit_code": None,
            "stdout": f"{name}.stdout.log",
            "stderr": f"{name}.stderr.log",
        }
        self.commands.append(step)
        self.save()  # Persist intent before starting the child.
        print(f"+ {name}: {subprocess.list2cmdline(command)}", flush=True)
        started = time.monotonic()
        process: subprocess.Popen[bytes] | None = None
        try:
            with (
                (self.directory / f"{name}.stdout.log").open("wb") as stdout,
                (self.directory / f"{name}.stderr.log").open("wb") as stderr,
            ):
                process = subprocess.Popen(
                    command,
                    cwd=directory,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=os.name != "nt",
                )
                try:
                    code = process.wait(timeout=timeout)
                    step.update(
                        exit_code=code, status="passed" if code == expected_exit else "failed"
                    )
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                    step.update(
                        status="timed_out"
                        if isinstance(error, subprocess.TimeoutExpired)
                        else "interrupted",
                        error=str(error) or "Interrupted",
                    )
                    self.save()
                    step["tree_cleanup"] = terminate_tree(process.pid)
                    if isinstance(error, KeyboardInterrupt):
                        raise
        except OSError as error:
            step.update(status="start_failed" if process is None else "failed", error=str(error))
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                step["exit_code"] = process.wait(timeout=15)
            step["elapsed_seconds"] = round(time.monotonic() - started, 6)
            self.save()
        output = (self.directory / f"{name}.stdout.log").read_text(
            encoding="utf-8", errors="replace"
        )
        errors = (self.directory / f"{name}.stderr.log").read_text(
            encoding="utf-8", errors="replace"
        )
        (self.directory / f"{name}.log").write_text(
            output + "\n--- stderr ---\n" + errors, encoding="utf-8"
        )
        print(f"{name}: {step['status']} ({step['elapsed_seconds']}s)", flush=True)
        if echo:
            print(output, end="", flush=True)
            print(errors, end="", file=sys.stderr, flush=True)
        if step["status"] != "passed":
            print((output + errors)[-4000:], file=sys.stderr, flush=True)
            raise CommandFailure(
                f"{name}: {step['status']}; see {self.directory / (name + '.log')}"
            )
        return subprocess.CompletedProcess(command, expected_exit, output, errors)

    def finish(self, error: str | None = None) -> int:
        end = source_state(self.root)
        self.report["source_end"] = end
        self.report["source_unchanged"] = end == self.report["source_start"]
        if end["status"] != "observed":
            error = error or "Source identity unavailable"
        elif not self.report["source_unchanged"]:
            error = error or "Source changed during verification; rerun on a stable worktree"
        if error:
            self.report["error"] = error
        passed = not error and all(step["status"] == "passed" for step in self.commands)
        self.report.update(
            status="passed" if passed else "failed", finished_at=datetime.now(UTC).isoformat()
        )
        self.save()
        print(
            f"{self.report['kind']}: {self.report['status']}; {self.directory / 'summary.json'}",
            flush=True,
        )
        return 0 if passed else 1
