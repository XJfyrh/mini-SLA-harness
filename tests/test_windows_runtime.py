"""Reject damaged runtime inputs before execution, using real files and ZIPs."""

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.windows_runtime import (
    PATH_CONFIG,
    archive,
    prepare,
    runtime_directory,
    verified_python,
)


class WindowsRuntimeTests(unittest.TestCase):
    def test_cached_archive_mismatch_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            damaged = cache / "runtime.zip"
            damaged.write_bytes(b"damaged")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                archive(cache, ("https://example.invalid/runtime.zip", "sha256", "0" * 64))
            self.assertEqual(damaged.read_bytes(), b"damaged")

    def test_new_download_mismatch_never_becomes_a_cached_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.zip"
            source.write_bytes(b"not the pinned archive")
            cache = root / "cache"
            cache.mkdir()
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                archive(cache, (source.as_uri(), "sha256", "0" * 64))
            self.assertEqual(list(cache.iterdir()), [])

    def test_prepare_reuse_and_corruption_refusal_preserve_existing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python_zip = root / "python.zip"
            sqlite_zip = root / "sqlite.zip"
            with zipfile.ZipFile(python_zip, "w") as bundle:
                for name in ("python.exe", "python314.dll", "python314.zip", "_sqlite3.pyd"):
                    bundle.writestr(name, name.encode())
                bundle.writestr("sqlite3.dll", b"original")
            with zipfile.ZipFile(sqlite_zip, "w") as bundle:
                bundle.writestr("sqlite3.dll", b"pinned-sqlite")
            sources = tuple(
                (path.as_uri(), "sha256", hashlib.sha256(path.read_bytes()).hexdigest())
                for path in (python_zip, sqlite_zip)
            )
            with (
                patch("scripts.windows_runtime.sys.platform", "win32"),
                patch("scripts.windows_runtime.platform.machine", return_value="AMD64"),
                patch("scripts.windows_runtime.ARCHIVES", sources),
            ):
                python = prepare(root)
                directory = python.parent
                manifest = (directory / "runtime.json").read_bytes()
                self.assertEqual((directory / "sqlite3.dll").read_bytes(), b"pinned-sqlite")
                self.assertEqual((directory / "python314._pth").read_text(), PATH_CONFIG)
                self.assertEqual(prepare(root), python)
                self.assertEqual((directory / "runtime.json").read_bytes(), manifest)
                changed = json.loads(manifest)
                changed["archives"][0][2] = "0" * 64
                (directory / "runtime.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError, "Runtime lock differs"):
                    verified_python(root)
                (directory / "runtime.json").write_bytes(manifest)
                (directory / "sqlite3.dll").write_bytes(b"manual drift")
                with self.assertRaisesRegex(RuntimeError, "Runtime file changed"):
                    prepare(root)
                self.assertEqual((directory / "sqlite3.dll").read_bytes(), b"manual drift")

    def test_missing_runtime_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "runtime-bootstrap"):
                verified_python(root)
            directory = runtime_directory(root)
            directory.mkdir(parents=True)
            (directory / "python.exe").write_bytes(b"incomplete")
            with self.assertRaisesRegex(RuntimeError, "runtime-bootstrap"):
                verified_python(root)
            self.assertEqual((directory / "python.exe").read_bytes(), b"incomplete")


if __name__ == "__main__":
    unittest.main()
