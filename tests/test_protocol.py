"""Observe persisted protocol results and actual refusal/crash paths."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mini_sla_harness.artifacts import ArtifactStore
from mini_sla_harness.contracts import (
    MAX_INT,
    Command,
    Object,
    ProtocolError,
    Role,
    TaskSpec,
    canonical,
    parse_object,
)
from mini_sla_harness.m0 import SCENARIOS, OfflineRun, row
from mini_sla_harness.state import StateStore


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_offline_acceptance_scenarios(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("M0 must not access the network")):
            for name, _, scenario in SCENARIOS:
                with self.subTest(scenario=name):
                    scenario(self.root / name)

    def test_attempt_retry_cap_persists_failure_after_reopen(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            run.accept_plan()
            run.trial()
            for _ in range(2):
                run.now += 1000000000
                run.claim("ClaimTrial", "trial_id", "trial")
            run.reopen()
            for _ in range(2):
                with self.assertRaises(ProtocolError) as exhausted:
                    run.command(
                        "ClaimTrial",
                        {
                            "trial_id": "trial",
                            "attempt_id": "attempt-over-cap",
                            "owner": "offline",
                            "lease_ns": 1000000000,
                        },
                        key="claim-over-cap",
                    )
                self.assertEqual(exhausted.exception.code, "RETRY_EXHAUSTED")
            self.assertEqual(row(run.store.snapshot(), "trials")["state"], "FAILED")

    def test_assignment_edit_scope_is_enforced_against_its_base(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.store.close()
            run.database = run.root / "narrow-scope.sqlite3"
            run.store = StateStore(run.database, run.artifacts, clock=lambda: run.now)
            run.task = TaskSpec.parse(
                run.task.value
                | {
                    "editable_files": ["src/processor.py", "src/helper.py"],
                }
            )
            helper = run.workspace / "src/helper.py"
            helper.write_bytes(b"protected by this Assignment\n")
            run.command(
                "CreateRun",
                {
                    "task": run.task.value,
                    "artifact_hash": run.artifacts.freeze(run.workspace, run.task),
                    "budget_limit": 1000,
                },
            )
            run.initialize()
            invocation, advisor, response = run.open_plan()
            plan = parse_object(run.artifacts.read(response))
            assignments = plan["assignments"]
            assert isinstance(assignments, list) and isinstance(assignments[0], dict)
            assignments[0]["editable_files"] = ["src/processor.py"]
            response = run.artifacts.put(plan)
            run.command(
                "RecordAdvisorResponse",
                {"artifact_hash": response},
                run.principal(advisor, Role.CONTROLLER),
            )
            run.command("CommitPlan", {"invocation_id": invocation})
            worker = run.trial()
            helper.write_bytes(b"unauthorized modification\n")
            with self.assertRaises(ProtocolError) as forbidden:
                run.candidate(worker)
            self.assertEqual(forbidden.exception.code, "ARTIFACT_INVALID")
            self.assertEqual(row(run.store.snapshot(), "trials")["state"], "RUNNING")

    def test_task_rejects_missing_fields_bool_fraction_overflow_and_alias_paths(self) -> None:
        with OfflineRun(self.root / "run") as run:
            for field in ("editable_files", "metric"):
                invalid = run.task.value.copy()
                del invalid[field]
                with self.subTest(field=field), self.assertRaises(ProtocolError):
                    TaskSpec.parse(invalid)
            for value in (True, -1, 0.5, 10001):
                invalid = run.task.value | {"min_improvement_bps": value}
                with self.subTest(value=value), self.assertRaises(ProtocolError):
                    TaskSpec.parse(invalid)
            for name in (
                "../secret",
                "/absolute",
                "C:/data",
                "//host/share",
                "a:stream",
                "NUL.py",
                "a.",
                "a ",
                "a\\b",
            ):
                invalid = run.task.value | {"editable_files": [name]}
                with self.subTest(path=name), self.assertRaises(ProtocolError):
                    TaskSpec.parse(invalid)
            with self.assertRaises(ProtocolError):
                TaskSpec.parse(run.task.value | {"editable_files": ["src/a.py", "src/A.py"]})
            with self.assertRaises(ProtocolError):
                parse_object('{"schema_version":1,"schema_version":2}')

    def test_artifact_round_trip_empty_file_and_no_overwrite(self) -> None:
        with OfflineRun(self.root / "run") as run:
            source = run.workspace / "src" / "processor.py"
            for index, data in enumerate((b"", b"# UTF-8 \xe4\xbd\xa0\xe5\xa5\xbd\n")):
                source.write_bytes(data)
                digest = run.artifacts.freeze(run.workspace, run.task)
                self.assertEqual(run.artifacts.freeze(run.workspace, run.task), digest)
                destination = self.root / f"materialized-{index}"
                run.artifacts.materialize(digest, run.task, destination)
                self.assertEqual((destination / "src" / "processor.py").read_bytes(), data)
                with self.assertRaises(FileExistsError):
                    run.artifacts.materialize(digest, run.task, destination)
                self.assertEqual((destination / "src" / "processor.py").read_bytes(), data)

    def test_hardlink_and_corrupt_references_are_rejected(self) -> None:
        with OfflineRun(self.root / "run") as run:
            source = run.workspace / "src" / "processor.py"
            alias = self.root / "alias.py"
            os.link(source, alias)
            with self.assertRaises(ProtocolError) as rejected:
                run.artifacts.freeze(run.workspace, run.task)
            self.assertEqual(rejected.exception.code, "ARTIFACT_INVALID")
            alias.unlink()
            baseline = row(run.store.snapshot(), "candidates")
            run.artifacts.path(str(baseline["artifact_hash"])).write_bytes(b"tampered")
            run.reopen()
            state = row(run.store.snapshot(), "runs")
            self.assertEqual(state["status"], "FAILED")
            self.assertEqual(state["completion_reason"], "ARTIFACT_CORRUPT")

    def test_second_controller_is_refused_across_processes(self) -> None:
        with OfflineRun(self.root / "run") as run:
            source = (
                "from pathlib import Path; from mini_sla_harness.state import StateStore; "
                "from mini_sla_harness.artifacts import ArtifactStore; "
                f"StateStore(Path({str(run.database)!r}),ArtifactStore(Path({str(run.artifacts.root)!r})))"
            )
            result = subprocess.run(
                [sys.executable, "-I", "-c", source], capture_output=True, text=True, timeout=10
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CONTROLLER_BUSY", result.stderr)

    def test_active_trial_unique_constraint_and_atomic_plan_failure(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            invocation, attempt, _ = run.open_plan()
            duplicate: Object = {
                "assignment_id": "assignment",
                "branch_id": "branch",
                "mode": "NEW",
                "worker_slot": 0,
                "max_trials": 3,
                "direction_key": "offline",
                "hypothesis": "fixed fake result",
                "objective": "verify atomic plan commit",
                "editable_files": ["src/processor.py"],
            }
            response = run.artifacts.put({"assignments": [duplicate, duplicate]})
            run.command(
                "RecordAdvisorResponse",
                {"artifact_hash": response},
                run.principal(attempt, Role.CONTROLLER),
            )
            with self.assertRaises(ProtocolError):
                run.command("CommitPlan", {"invocation_id": invocation})
            self.assertEqual(run.store.snapshot()["assignments"], [])
            self.assertEqual(run.store.snapshot()["branches"], [])
            run.command("RetryAdvisor", {"invocation_id": invocation, "reason": "repairs"})
            attempt = run.claim("ClaimAdvisor", "invocation_id", invocation)
            response = run.artifacts.put({"assignments": [duplicate]})
            run.command(
                "RecordAdvisorResponse",
                {"artifact_hash": response},
                run.principal(attempt, Role.CONTROLLER),
            )
            run.command("CommitPlan", {"invocation_id": invocation})
            run.trial(assignment="assignment")
            with self.assertRaises(ProtocolError):
                run.command(
                    "CreateTrial",
                    {"assignment_id": "assignment", "trial_id": "other", "budget_limit": 100},
                )
            self.assertEqual(row(run.store.snapshot(), "assignments")["trials_created"], 1)

    def test_worker_cannot_supply_official_score_or_wrong_scope(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            run.accept_plan(count=2)
            first = run.trial("first", "assignment-0")
            run.trial("second", "assignment-1")
            with self.assertRaises(ProtocolError) as forbidden:
                run.command(
                    "RecordEvaluation",
                    {"verdict": "VALID_SCORED", "score_i": 999999},
                    run.principal(first, Role.WORKER),
                )
            self.assertEqual(forbidden.exception.code, "FORBIDDEN")
            with self.assertRaises(ProtocolError) as scope:
                run.reserve(first, "second", "wrong-scope", 10)
            self.assertEqual(scope.exception.code, "FORBIDDEN")
            self.assertEqual(row(run.store.snapshot(), "runs")["held"], 0)

    def test_invalid_candidate_score_does_not_change_best_and_result_is_immutable(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            run.accept_plan()
            attempt = run.trial()
            job = run.candidate(attempt)
            evaluator = run.claim("ClaimEvaluation", "evaluation_id", job)
            with self.assertRaises(ProtocolError):
                run.command(
                    "RecordEvaluation",
                    {"verdict": "INCORRECT", "score_i": 999999},
                    run.principal(evaluator, Role.EVALUATOR),
                )
            run.command(
                "RecordEvaluation",
                {"verdict": "INCORRECT", "score_i": None},
                run.principal(evaluator, Role.EVALUATOR),
            )
            run.command("FinalizeTrial", {"trial_id": "trial", "evaluation_id": job})
            with self.assertRaises(ProtocolError):
                run.command(
                    "RecordEvaluation",
                    {"verdict": "VALID_SCORED", "score_i": 999999},
                    run.principal(evaluator, Role.EVALUATOR),
                )
            snapshot = run.store.snapshot()
            self.assertEqual(row(snapshot, "runs")["best_score"], 90000)
            self.assertIsNone(row(snapshot, "evaluations", job)["score"])

    def test_evaluator_lease_takeover_and_retry_exhaustion(self) -> None:
        with OfflineRun(self.root / "run") as run:
            old = run.claim("ClaimEvaluation", "evaluation_id", "baseline-evaluation")
            run.now += 1000000000
            current = run.claim("ClaimEvaluation", "evaluation_id", "baseline-evaluation")
            with self.assertRaises(ProtocolError):
                run.command(
                    "RecordEvaluation",
                    {"verdict": "VALID_SCORED", "score_i": 1},
                    run.principal(old, Role.EVALUATOR),
                )
            run.command(
                "RecordEvaluation",
                {"verdict": "INFRA_ERROR"},
                run.principal(current, Role.EVALUATOR),
            )
            run.evaluate("baseline-evaluation", verdict="INFRA_ERROR")
            self.assertEqual(row(run.store.snapshot(), "runs")["status"], "FAILED")
            self.assertEqual(row(run.store.snapshot(), "evaluations")["state"], "FAILED")

    def test_started_baseline_drains_retries_through_pause_stop_and_reopen(self) -> None:
        for command in ("Pause", "Stop"):
            for interrupted in ("infra", "reopen"):
                with (
                    self.subTest(command=command, interrupted=interrupted),
                    OfflineRun(self.root / f"{command}-{interrupted}") as run,
                ):
                    if interrupted == "infra":
                        run.evaluate("baseline-evaluation", None, "INFRA_ERROR")
                    else:
                        run.claim("ClaimEvaluation", "evaluation_id", "baseline-evaluation")
                    run.command(command)
                    run.reopen()
                    expected = "PAUSING" if command == "Pause" else "STOPPING"
                    self.assertEqual(row(run.store.snapshot(), "runs")["status"], expected)
                    run.evaluate("baseline-evaluation", 90000)
                    run.command("InitializeBaseline")
                    run.reopen()
                    snapshot = run.store.snapshot()
                    self.assertEqual(row(snapshot, "runs")["best_score"], 90000)
                    self.assertEqual(
                        row(snapshot, "runs")["status"],
                        "PAUSED" if command == "Pause" else "COMPLETED",
                    )
                    self.assertEqual(row(snapshot, "evaluations")["state"], "DONE")

    def test_drain_reclaims_only_started_trial_after_reopen(self) -> None:
        for stop_before_reopen in (True, False):
            with (
                self.subTest(stop_before_reopen=stop_before_reopen),
                OfflineRun(self.root / str(stop_before_reopen)) as run,
            ):
                run.initialize()
                run.accept_plan(count=2)
                run.trial()
                run.command(
                    "CreateTrial",
                    {"trial_id": "unstarted", "assignment_id": "assignment-1", "budget_limit": 100},
                )
                if stop_before_reopen:
                    run.command("Stop")
                run.reopen()
                if not stop_before_reopen:
                    run.command("Stop")
                snapshot = run.store.snapshot()
                self.assertEqual(row(snapshot, "runs")["status"], "STOPPING")
                self.assertEqual(row(snapshot, "trials", "trial")["state"], "PENDING")
                self.assertEqual(row(snapshot, "trials", "unstarted")["state"], "CANCELLED")
                with self.assertRaises(ProtocolError):
                    run.claim("ClaimTrial", "trial_id", "unstarted")
                attempt = run.claim("ClaimTrial", "trial_id", "trial")
                run.finish("trial", attempt, 95000)
                run.reopen()
                snapshot = run.store.snapshot()
                self.assertEqual(row(snapshot, "runs")["status"], "COMPLETED")
                self.assertEqual(row(snapshot, "runs")["best_score"], 95000)
                self.assertEqual(row(snapshot, "assignments")["state"], "DONE")
                self.assertEqual(row(snapshot, "assignments")["skipped"], 2)
                self.assertEqual(row(snapshot, "assignments", "assignment-1")["skipped"], 3)
                self.assertEqual(row(snapshot, "epochs")["state"], "CLOSED")

    def test_unknown_cannot_be_released_and_usage_breach_is_not_truncated(self) -> None:
        with OfflineRun(self.root / "run", budget=100) as run:
            run.initialize()
            run.accept_plan()
            attempt = run.trial(limit=100)
            run.reserve(attempt, "trial", "call", 20)
            run.dispatch(attempt, "call")
            run.command("UnknownCall", {"call_id": "call"}, run.principal(attempt, Role.GATEWAY))
            with self.assertRaises(ProtocolError):
                run.command(
                    "ReleaseCall", {"call_id": "call"}, run.principal(attempt, Role.GATEWAY)
                )
            run.settle("call", 100, 10)
            state = row(run.store.snapshot(), "runs")
            self.assertEqual(state["confirmed"], 110)
            self.assertEqual(state["held"], 0)
            self.assertEqual(state["completion_reason"], "BUDGET_BOUND_BREACH")
            with self.assertRaises(ProtocolError):
                run.reserve(attempt, "trial", "another", 1)

    def test_pause_before_advisor_dispatch_releases_unsent_reservation(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            invocation, attempt, _ = run.open_plan()
            run.reserve(attempt, invocation, "unsent", 100)
            run.command("Pause")
            snapshot = run.store.snapshot()
            self.assertEqual(row(snapshot, "runs")["held"], 0)
            self.assertEqual(row(snapshot, "runs")["status"], "PAUSED")
            self.assertEqual(row(snapshot, "invocations")["state"], "PLANNED")
            with self.assertRaises(ProtocolError):
                run.dispatch(attempt, "unsent")

    def test_advisor_repairs_and_scope_survive_restart(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            invocation, attempt, response = run.open_plan()
            run.reserve(attempt, invocation, "first", 1900)
            run.dispatch(attempt, "first")
            run.command(
                "RecordAdvisorResponse",
                {"artifact_hash": response},
                run.principal(attempt, Role.CONTROLLER),
            )
            run.command("RetryAdvisor", {"invocation_id": invocation, "reason": "repairs"})
            run.reopen()
            attempt = run.claim("ClaimAdvisor", "invocation_id", invocation)
            run.command(
                "RecordAdvisorResponse",
                {"artifact_hash": response},
                run.principal(attempt, Role.CONTROLLER),
            )
            with self.assertRaises(ProtocolError) as exhausted:
                run.command("RetryAdvisor", {"invocation_id": invocation, "reason": "repairs"})
            self.assertEqual(exhausted.exception.code, "ADVISOR_PLAN_EXHAUSTED")
            self.assertEqual(row(run.store.snapshot(), "runs")["status"], "FAILED")
            self.assertEqual(row(run.store.snapshot(), "budget_scopes")["held"], 1900)

    def test_scope_exhaustion_commits_terminal_state_and_replays_error(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            invocation, attempt, _ = run.open_plan()
            run.reserve(attempt, invocation, "first", 1900)
            run.dispatch(attempt, "first")
            payload: Object = {
                "scope_id": invocation,
                "call_id": "second",
                "request_hash": "second",
                "input_upper_bound": 101,
                "output_cap": 0,
            }
            principal = run.principal(attempt, Role.GATEWAY)
            for _ in range(2):
                with self.assertRaises(ProtocolError) as scope:
                    run.command("ReserveCall", payload, principal, key="exhausted-call")
                self.assertEqual(scope.exception.code, "SCOPE_BUDGET_EXHAUSTED")
            run.reopen()
            self.assertEqual(row(run.store.snapshot(), "runs")["status"], "COMPLETED")
            self.assertEqual(row(run.store.snapshot(), "invocations")["state"], "FAILED")
            self.assertEqual(row(run.store.snapshot(), "runs")["held"], 1900)
            self.assertEqual(
                run.store.snapshot()["accounting"],
                {
                    "confirmed": 0,
                    "held_reserved": 0,
                    "held_unknown": 1900,
                    "available": 8100,
                    "state": "OPEN",
                },
            )

    def test_stop_counts_never_started_pending_trial_as_skipped(self) -> None:
        for kind in ("Stop", "ForceStop"):
            with self.subTest(kind=kind), OfflineRun(self.root / kind) as run:
                run.initialize()
                run.accept_plan()
                run.command(
                    "CreateTrial",
                    {
                        "trial_id": "pending",
                        "assignment_id": "assignment-0",
                        "budget_limit": 100,
                    },
                )
                run.command(kind)
                snapshot = run.store.snapshot()
                self.assertEqual(row(snapshot, "assignments")["skipped"], 3)
                self.assertEqual(row(snapshot, "trials")["state"], "CANCELLED")
                self.assertEqual(row(snapshot, "runs")["status"], "COMPLETED")

    def test_invalid_integer_score_is_rejected_before_write(self) -> None:
        with OfflineRun(self.root / "run") as run:
            attempt = run.claim("ClaimEvaluation", "evaluation_id", "baseline-evaluation")
            for invalid in (True, -1, 1.25, MAX_INT + 1):
                with self.subTest(score=invalid), self.assertRaises(ProtocolError):
                    run.command(
                        "RecordEvaluation",
                        {"verdict": "VALID_SCORED", "score_i": invalid},
                        run.principal(attempt, Role.EVALUATOR),
                    )
            self.assertEqual(row(run.store.snapshot(), "evaluations")["state"], "RUNNING")

    def test_committed_facts_and_uncommitted_writes_after_process_death(self) -> None:
        for point in ("candidate", "done", "finalized", "forced", "uncommitted", "orphan"):
            with self.subTest(point=point):
                directory = self.root / point
                source = (
                    "import os; from pathlib import Path; "
                    "from mini_sla_harness.m0 import OfflineRun; "
                    f"r=OfflineRun(Path({str(directory)!r})); "
                    "r.initialize(); r.accept_plan(); a=r.trial(); "
                )
                if point != "orphan":
                    source += "j=r.candidate(a); "
                else:
                    source += "r.artifacts.freeze(r.workspace,r.task); "
                if point in {"done", "finalized", "forced"}:
                    source += "r.evaluate(j,110000); "
                if point == "finalized":
                    source += "r.command('FinalizeTrial',{'trial_id':'trial','evaluation_id':j}); "
                elif point == "forced":
                    source += "r.command('ForceStop'); "
                elif point == "uncommitted":
                    source += (
                        "r.store.connection.execute('BEGIN IMMEDIATE'); "
                        "r.store.connection.execute('UPDATE runs SET best_score=999999'); "
                    )
                source += "os._exit(71)"
                result = subprocess.run(
                    [sys.executable, "-I", "-c", source], capture_output=True, text=True, timeout=15
                )
                self.assertEqual(result.returncode, 71, result.stderr)
                with StateStore(
                    directory / "state.sqlite3", ArtifactStore(directory / "cas")
                ) as store:
                    snapshot = store.snapshot()
                    self.assertEqual(
                        row(snapshot, "runs")["best_score"],
                        110000 if point == "finalized" else 90000,
                    )
                    trial = row(snapshot, "trials")
                    expected = {
                        "candidate": "CANDIDATE_READY",
                        "done": "EVALUATING",
                        "finalized": "COMPLETED",
                        "forced": "CANCELLED",
                        "uncommitted": "CANDIDATE_READY",
                        "orphan": "PENDING",
                    }
                    self.assertEqual(trial["state"], expected[point])
                    if point == "done":
                        for index in range(2):
                            store.execute(
                                Command(
                                    f"finish-{index}",
                                    "FinalizeTrial",
                                    "run",
                                    {"trial_id": "trial", "evaluation_id": trial["evaluation_id"]},
                                ),
                                store.controller,
                            )
                        self.assertEqual(row(store.snapshot(), "runs")["best_score"], 110000)

    def test_task_cli_and_foreign_database_refusal(self) -> None:
        with OfflineRun(self.root / "run") as run:
            task = self.root / "task.json"
            task.write_bytes(canonical(run.task.value))
            result = subprocess.run(
                [sys.executable, "-I", "-m", "mini_sla_harness", "task", "validate", str(task)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(parse_object(result.stdout)["task_spec_hash"], run.task.digest)
        with closing(sqlite3.connect(self.root / "demo.sqlite3")) as demo, demo:
            demo.execute("CREATE TABLE demo_records(value TEXT)")
        with self.assertRaises(ProtocolError):
            StateStore(self.root / "demo.sqlite3", ArtifactStore(self.root / "cas"))

    def test_open_epoch_rejects_stale_context_before_creating_entities(self) -> None:
        with OfflineRun(self.root / "run") as run:
            run.initialize()
            state = row(run.store.snapshot(), "runs")
            context = run.artifacts.put(
                {
                    "task_spec_hash": run.task.digest,
                    "snapshot_version": state["evidence_version"],
                }
            )
            with self.assertRaises(ProtocolError) as stale:
                run.command(
                    "OpenEpoch",
                    {
                        "epoch_id": "epoch",
                        "epoch_no": 1,
                        "artifact_hash": context,
                        "budget_limit": 100,
                        "expected_version": 0,
                    },
                )
            self.assertEqual(stale.exception.code, "STALE_SNAPSHOT")
            self.assertEqual(run.store.snapshot()["epochs"], [])
            self.assertEqual(run.store.snapshot()["budget_scopes"], [])


if __name__ == "__main__":
    unittest.main()
