"""Exercise real failures and inspect evidence outside the child process."""

import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.dev import run_checks
from scripts.doctor import probe, wal_reset_fixed
from scripts.evidence import CommandFailure, Evidence, source_state, terminate_tree
from scripts.package_check import accept_wheel


class FeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / ".gitignore").write_text("artifacts/\n", encoding="utf-8")
        (self.root / "source.txt").write_text("initial\n", encoding="utf-8")
        for arguments in (
            ["init", "--quiet"],
            ["add", "."],
            [
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
        ):
            subprocess.run(
                ["git", *arguments], cwd=self.root, check=True, capture_output=True, timeout=15
            )

    def command(self, source: str) -> list[str]:
        return [sys.executable, "-I", "-c", source]

    def test_independent_failures_are_collected_and_later_check_runs(self) -> None:
        evidence = Evidence(self.root, "check")
        marker = self.root / "artifacts" / "later.txt"
        code = run_checks(
            evidence,
            [
                ("first", self.command("raise SystemExit(3)"), 5),
                ("second", self.command("raise AssertionError('second observed failure')"), 5),
                (
                    "later",
                    self.command(
                        f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"
                    ),
                    5,
                ),
            ],
        )
        report = json.loads((evidence.directory / "summary.json").read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual([step["exit_code"] for step in report["commands"]], [3, 1, 0])
        self.assertEqual(marker.read_text(), "ran")
        self.assertIn(
            "second observed failure", (evidence.directory / "second.stderr.log").read_text()
        )

    def test_running_record_exists_before_child_executes(self) -> None:
        evidence = Evidence(self.root, "record")
        summary = evidence.directory / "summary.json"
        evidence.run(
            "observe",
            self.command(
                "import json; from pathlib import Path; "
                f"r=json.loads(Path({str(summary)!r}).read_text()); "
                "assert r['status']=='running'; assert r['commands'][0]['status']=='running'"
            ),
        )
        self.assertEqual(evidence.finish(), 0)

    def test_timeout_preserves_both_output_streams_and_allows_later_check(self) -> None:
        evidence = Evidence(self.root, "timeout")
        code = run_checks(
            evidence,
            [
                (
                    "slow",
                    self.command(
                        "import sys,time; print('stdout-marker',flush=True); "
                        "print('stderr-marker',file=sys.stderr,flush=True); time.sleep(60)"
                    ),
                    1,
                ),
                ("later", self.command("print('continued')"), 5),
            ],
        )
        self.assertEqual(code, 1)
        self.assertEqual(evidence.commands[0]["status"], "timed_out")
        self.assertEqual(evidence.commands[1]["status"], "passed")
        self.assertIn("stdout-marker", (evidence.directory / "slow.stdout.log").read_text())
        self.assertIn("stderr-marker", (evidence.directory / "slow.stderr.log").read_text())
        self.assertIsInstance(evidence.commands[0]["exit_code"], int)

    def test_unstartable_command_is_recorded(self) -> None:
        evidence = Evidence(self.root, "missing")
        with self.assertRaises(CommandFailure):
            evidence.run("missing", [str(self.root / "missing-executable")])
        self.assertEqual(evidence.commands[0]["status"], "start_failed")
        self.assertIsNone(evidence.commands[0]["exit_code"])
        self.assertEqual(evidence.finish(), 1)

    def test_timeout_closes_descendant_endpoint_even_in_a_new_session(self) -> None:
        evidence = Evidence(self.root, "tree")
        child = (
            "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); "
            "s.listen(); print(s.getsockname()[1],flush=True); time.sleep(60)"
        )
        parent = (
            "import subprocess,sys,socket,time; "
            f"p=subprocess.Popen([sys.executable,'-I','-c',{child!r}], "
            "stdout=subprocess.PIPE,text=True,start_new_session=True); "
            "assert p.stdout; port=int(p.stdout.readline()); "
            "s=socket.create_connection(('127.0.0.1',port),timeout=2); s.close(); "
            "print(p.pid,port,flush=True); time.sleep(60)"
        )
        with self.assertRaises(CommandFailure):
            evidence.run("parent", self.command(parent), timeout=2)
        pid, port = map(int, (evidence.directory / "parent.stdout.log").read_text().split())
        try:
            with self.assertRaises(OSError):
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
        finally:
            terminate_tree(pid)
        self.assertEqual(evidence.commands[0]["status"], "timed_out")
        self.assertEqual(evidence.finish(), 1)

    def test_expected_failure_exit_is_explicit_and_wrong_exit_fails(self) -> None:
        evidence = Evidence(self.root, "negative")
        evidence.run("expected", self.command("raise SystemExit(2)"), expected_exit=2)
        with self.assertRaises(CommandFailure):
            evidence.run("unexpected", self.command("raise SystemExit(0)"), expected_exit=2)
        self.assertEqual(evidence.finish(), 1)

    def test_evidence_is_unique_and_source_changes_invalidate_pass(self) -> None:
        first = Evidence(self.root, "check")
        second = Evidence(self.root, "check")
        self.assertNotEqual(first.directory, second.directory)
        self.assertEqual(first.finish(), 0)
        (self.root / "source.txt").write_text("changed\n", encoding="utf-8")
        self.assertEqual(second.finish(), 1)
        self.assertFalse(second.report["source_unchanged"])
        self.assertEqual(
            json.loads((first.directory / "summary.json").read_text())["status"], "passed"
        )

    def test_untracked_content_is_fingerprinted_but_artifacts_are_ignored(self) -> None:
        before = source_state(self.root)
        self.assertEqual(before["status"], "observed")
        extra = self.root / "untracked.py"
        extra.write_text("one", encoding="utf-8")
        added = source_state(self.root)
        extra.write_text("two", encoding="utf-8")
        changed = source_state(self.root)
        self.assertNotEqual(before, added)
        self.assertNotEqual(added, changed)
        Evidence(self.root, "ignored")
        self.assertEqual(changed, source_state(self.root))

    def test_unavailable_source_identity_cannot_report_pass(self) -> None:
        outside = self.root / "artifacts" / "no-git"
        outside.mkdir(parents=True)
        # An invalid nested .git must not make the parent's source identity acceptable.
        (outside / ".git").mkdir()
        evidence = Evidence(outside, "unknown")
        self.assertEqual(evidence.finish(), 1)
        self.assertEqual(evidence.report["source_end"], source_state(outside))

    def test_failed_wheel_build_does_not_start_dependent_install(self) -> None:
        (self.root / "pyproject.toml").write_text(
            '[project]\nname="broken-fixture"\nversion="0.0.1"\n'
            '[build-system]\nrequires=[]\nbuild-backend="missing_backend_for_negative_test"\n',
            encoding="utf-8",
        )
        evidence = Evidence(self.root, "package-check")
        with self.assertRaises(CommandFailure):
            accept_wheel(self.root, evidence)
        self.assertEqual([step["name"] for step in evidence.commands], ["build"])
        self.assertEqual(evidence.finish(), 1)
        self.assertEqual(list((self.root / "artifacts" / "tmp").iterdir()), [])

    def test_doctor_uses_real_sqlite_and_reports_io_failure(self) -> None:
        observations = {item["name"]: item for item in probe(self.root)}
        self.assertEqual(observations["sqlite_wal_round_trip"]["status"], "passed")
        blocked = self.root / "blocked"
        blocked.mkdir()
        (blocked / "artifacts").write_text("existing file", encoding="utf-8")
        failures = {item["name"]: item for item in probe(blocked)}
        self.assertEqual(failures["sqlite_wal_round_trip"]["status"], "failed")
        self.assertEqual((blocked / "artifacts").read_text(), "existing file")

    def test_wal_fix_accepts_only_fixed_branches(self) -> None:
        for version in ((3, 44, 6), (3, 44, 7), (3, 50, 7), (3, 51, 3), (3, 52, 0)):
            with self.subTest(version=version):
                self.assertTrue(wal_reset_fixed(version))
        for version in ((3, 44, 5), (3, 45, 9), (3, 49, 9), (3, 50, 4), (3, 50, 6), (3, 51, 2)):
            with self.subTest(version=version):
                self.assertFalse(wal_reset_fixed(version))


if __name__ == "__main__":
    unittest.main()
