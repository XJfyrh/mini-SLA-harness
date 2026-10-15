"""Content-addressed objects with no-clobber publication and verified reconstruction."""

import base64
import hashlib
import os
import stat
import tempfile
from pathlib import Path

from mini_sla_harness.contracts import (
    Json,
    Object,
    TaskSpec,
    canonical,
    integer,
    parse_object,
    relative_path,
    require,
    text,
)


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str) -> Path:
        require(
            len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            "ARTIFACT_INVALID",
            "Invalid object hash",
        )
        return self.root / f"{digest}.json"

    def read(self, digest: str) -> bytes:
        path = self.path(digest)
        require(path.is_file() and not path.is_symlink(), "ARTIFACT_CORRUPT", digest)
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == digest, "ARTIFACT_CORRUPT", digest)
        return data

    def put(self, value: Object) -> str:
        data = canonical(value)
        digest = hashlib.sha256(data).hexdigest()
        target = self.path(digest)
        if target.exists():
            self.read(digest)
            return digest
        descriptor, temporary = tempfile.mkstemp(dir=self.root, prefix="publishing-")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                if os.name == "nt":
                    os.rename(temporary, target)  # Windows refuses an existing destination.
                else:
                    os.link(temporary, target)  # POSIX rename would replace an existing object.
            except FileExistsError:
                self.read(digest)
            if os.name != "nt":
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.read(digest)
        return digest

    def freeze(self, workspace: Path, task: TaskSpec) -> str:
        entries: list[Json] = []
        names = task.value["editable_files"]
        require(isinstance(names, list), "INVALID_TASK", "editable_files required")
        if not isinstance(names, list):
            raise ValueError("editable_files required")
        root = workspace.resolve()
        total = 0
        for item in sorted(str(name) for name in names):
            name = relative_path(item)
            path = root
            for part in name.split("/"):
                path = path / part
                info = path.lstat()
                require(
                    not path.is_symlink()
                    and not path.is_junction()
                    and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "ARTIFACT_INVALID",
                    f"Link or reparse point: {name}",
                )
            before = path.stat()
            require(
                stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                "ARTIFACT_INVALID",
                f"Not a regular, unlinked file: {name}",
            )
            data = path.read_bytes()
            after = path.stat()
            require(
                (before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_ino, after.st_size, after.st_mtime_ns),
                "ARTIFACT_INVALID",
                f"Workspace changed while freezing: {name}",
            )
            total += len(data)
            require(
                total <= 8 * 1024 * 1024 and len(entries) < 100, "ARTIFACT_INVALID", "Too large"
            )
            entries.append(
                {
                    "path": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                    "executable": False,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )
        return self.put({"schema_version": 1, "kind": "candidate", "files": entries})

    def files(self, digest: str, task: TaskSpec) -> dict[str, bytes]:
        bundle = parse_object(self.read(digest))
        require(bundle.get("kind") == "candidate", "ARTIFACT_INVALID", "Not a candidate bundle")
        entries = bundle.get("files")
        require(isinstance(entries, list), "ARTIFACT_INVALID", "Missing files")
        result: dict[str, bytes] = {}
        if isinstance(entries, list):
            for entry in entries:
                require(isinstance(entry, dict), "ARTIFACT_INVALID", "Invalid file entry")
                if not isinstance(entry, dict):
                    continue
                name = relative_path(text(entry, "path"))
                encoded = entry.get("data")
                require(isinstance(encoded, str), "ARTIFACT_INVALID", "Invalid base64 file")
                if not isinstance(encoded, str):
                    raise ValueError("Invalid base64 file")
                data = base64.b64decode(encoded, validate=True)
                require(
                    name.casefold() not in {key.casefold() for key in result}
                    and len(data) == integer(entry, "size")
                    and hashlib.sha256(data).hexdigest() == text(entry, "sha256")
                    and entry.get("executable") is False,
                    "ARTIFACT_INVALID",
                    f"Invalid file: {name}",
                )
                result[name] = data
        require(
            set(result) == set(task.editable_files),
            "ARTIFACT_INVALID",
            "Bundle must exactly match editable_files",
        )
        return result

    def materialize(self, digest: str, task: TaskSpec, destination: Path) -> None:
        files = self.files(digest, task)
        destination.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
