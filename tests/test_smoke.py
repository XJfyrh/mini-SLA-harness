"""Offline behavior checks for the scaffold, not Mini-SLA protocol acceptance tests."""

import json
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mini_sla_harness.demo import run_demo
from mini_sla_harness.fake import CASES, DemoRecord, FakeProvider
from mini_sla_harness.store import load_records, save_records


class FakeProviderTests(unittest.TestCase):
    def test_fixed_responses_without_network_or_environment(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(socket, "socket", side_effect=AssertionError("network forbidden")),
        ):
            for _, prompt, response in CASES:
                self.assertEqual(FakeProvider().complete(prompt), response)
                self.assertEqual(FakeProvider().complete(prompt), response)

    def test_unknown_prompt_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            FakeProvider().complete("not a fixture")


class PersistenceTests(unittest.TestCase):
    def test_reopen_unicode_path_and_wal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "\u6d4b\u8bd5 space #1" / "demo.sqlite3"
            record = DemoRecord("case", "prompt", "\u4f60\u597d")
            save_records(database, (record,))
            self.assertEqual(load_records(database), (record,))
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone(), ("wal",))

    def test_identical_replay_does_not_duplicate_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "demo.sqlite3"
            record = DemoRecord("case", "prompt", "response")
            save_records(database, (record,))
            save_records(database, (record,))
            self.assertEqual(load_records(database), (record,))

    def test_conflict_preserves_previous_data_and_rolls_back_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "demo.sqlite3"
            original = DemoRecord("case", "prompt", "response")
            save_records(database, (original,))
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                save_records(
                    database,
                    (DemoRecord("new", "prompt", "new"), replace(original, response="changed")),
                )
            self.assertEqual(load_records(database), (original,))

    def test_missing_database_read_does_not_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "missing.sqlite3"
            with self.assertRaises(sqlite3.OperationalError):
                load_records(database)
            self.assertFalse(database.exists())


class DemoTests(unittest.TestCase):
    def test_repeated_and_fresh_runs_have_identical_json(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(socket, "socket", side_effect=AssertionError("network forbidden")),
        ):
            first = Path(temp) / "first"
            report = run_demo(first)
            original_bytes = (first / "result.json").read_bytes()
            self.assertEqual(json.loads(original_bytes), report)
            self.assertEqual(report["case_count"], 3)
            self.assertEqual(report["research_effect"], "not_evaluated")
            self.assertEqual(run_demo(first), report)
            self.assertEqual((first / "result.json").read_bytes(), original_bytes)
            fresh = Path(temp) / "fresh"
            self.assertEqual(run_demo(fresh), report)
            self.assertEqual((fresh / "result.json").read_bytes(), original_bytes)


class CliTests(unittest.TestCase):
    def invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mini_sla_harness", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

    def test_json_stdout_and_export_match_in_separate_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "\u7ed3\u679c space #2"
            result = self.invoke("demo", "--output-dir", str(output), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout), json.loads((output / "result.json").read_bytes())
            )

    def test_human_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self.invoke("demo", "--output-dir", temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("3 cases", result.stdout)
            self.assertIn("SQLite round-trip: passed", result.stdout)
            self.assertIn("not evaluated", result.stdout)

    def test_unwritable_output_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "file"
            output.write_text("preserve me", encoding="utf-8")
            result = self.invoke("demo", "--output-dir", str(output))
            self.assertEqual(result.returncode, 1)
            self.assertIn("error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve me")

    def test_unknown_command_fails(self) -> None:
        result = self.invoke("run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
