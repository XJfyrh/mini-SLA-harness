"""Exercise the portable skill helper through real CLI calls and persisted bytes."""

import csv
import io
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / ".agents/skills/show-me-your-work/scripts/log.py"
HEADER = b"ts\trun_id\tphase\tdecision\twhy\tevidence\tresult\n"


class DecisionLogTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / "audit" / "decisions.tsv"

    def call(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        values = {
            "run": "session-a",
            "phase": "start",
            "decision": "Check the actual output",
            "why": "Determine whether the behavior matches the contract",
            "evidence": "tests/test_decision_log.py",
            "result": "pending",
        }
        values.update(overrides)
        arguments = [f"--{key}={value}" for key, value in values.items()]
        return subprocess.run(
            [sys.executable, "-I", str(HELPER), str(self.log), *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def rows(self) -> list[list[str]]:
        return list(csv.reader(io.StringIO(self.log.read_text(encoding="utf-8")), delimiter="\t"))

    def test_appends_one_header_and_utc_rows_without_rewriting_history(self) -> None:
        first = self.call()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(first.stdout.rstrip().endswith(":2"), first.stdout)
        original = self.log.read_bytes()
        second = self.call(phase="verify", result="failed")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(second.stdout.rstrip().endswith(":3"), second.stdout)
        self.assertTrue(self.log.read_bytes().startswith(original))
        self.assertEqual(self.log.read_bytes().count(HEADER), 1)
        rows = self.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], HEADER.decode().strip().split("\t"))
        self.assertEqual(
            rows[1][1:],
            [
                "session-a",
                "start",
                "Check the actual output",
                "Determine whether the behavior matches the contract",
                "tests/test_decision_log.py",
                "pending",
            ],
        )
        self.assertEqual(datetime.fromisoformat(rows[1][0]).utcoffset(), timedelta(0))
        self.assertEqual(rows[2][-1], "failed")

    def test_session_handoffs_require_start_and_preserve_rejected_writes(self) -> None:
        self.assertEqual(self.call(phase="verify").returncode, 1)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.call().returncode, 0)
        for previous, incoming in (("session-a", "session-b"), ("session-b", "session-a")):
            with self.subTest(incoming=incoming):
                original = self.log.read_bytes()
                rejected = self.call(run=incoming, phase="verify")
                self.assertEqual(rejected.returncode, 1, rejected.stderr)
                self.assertIn("--phase start", rejected.stderr)
                self.assertEqual(self.log.read_bytes(), original)
                accepted = self.call(run=incoming, phase="start", decision=f"Continue {previous}")
                self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(
            [row[1] for row in self.rows()[1:]], ["session-a", "session-b", "session-a"]
        )

    def test_wrong_header_corruption_and_truncation_leave_bytes_untouched(self) -> None:
        self.log.parent.mkdir()
        cases = (
            b"ts\tphase\nold\trow\n",
            HEADER + b"missing\tcolumns\n",
            HEADER + b'"unfinished\n',
            HEADER + b"invalid\t\xff\n",
            HEADER + b"partial row without newline",
            HEADER + b"t\trun\tstart\tdecision\t\tevidence\tresult\n",
        )
        for content in cases:
            with self.subTest(content=content):
                self.log.write_bytes(content)
                result = self.call()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self.log.read_bytes(), content)
                self.assertEqual(result.stdout, "")

    def test_utf8_quotes_and_formula_prefixes_remain_single_line_literal_cells(self) -> None:
        for value in ("=SUM(1,2)", "+command", "-command", "@command", " \t=command"):
            with self.subTest(value=value):
                result = self.call(decision=value, why='观察\t实际\r\n输出 "原值"')
                self.assertEqual(result.returncode, 0, result.stderr)
                row = self.rows()[-1]
                self.assertEqual(len(row), 7)
                self.assertTrue(row[3].startswith("'"), row[3])
                self.assertEqual(row[4], '观察 实际  输出 "原值"')
                self.assertFalse(any(char in cell for cell in row for char in "\t\r\n"))
        self.assertEqual(len(self.log.read_bytes().splitlines()), 6)

    def test_corrections_append_and_preserve_the_failed_and_unverified_results(self) -> None:
        self.assertEqual(self.call(result="unverified").returncode, 0)
        self.assertEqual(self.call(phase="verify", result="failed").returncode, 0)
        original = self.log.read_bytes()
        correction = self.call(
            phase="correction",
            decision="Correct row 3 after rerun",
            evidence="artifacts/new-run/summary.json",
            result="passed",
        )
        self.assertEqual(correction.returncode, 0, correction.stderr)
        self.assertTrue(self.log.read_bytes().startswith(original))
        self.assertEqual([row[-1] for row in self.rows()[1:]], ["unverified", "failed", "passed"])

    def test_empty_fields_and_filesystem_conflicts_fail_without_replacing_data(self) -> None:
        for key in ("run", "phase", "decision", "why", "evidence", "result"):
            with self.subTest(key=key):
                result = self.call(**{key: " \t\r\n "})
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(self.log.exists())
        self.log.mkdir(parents=True)
        marker = self.log / "preserve.txt"
        marker.write_text("original", encoding="utf-8")
        self.assertEqual(self.call().returncode, 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
