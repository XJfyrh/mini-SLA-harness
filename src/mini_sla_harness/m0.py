"""Repeatable offline acceptance using real SQLite, files, processes and competing requests."""

import platform
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from pathlib import Path
from threading import Barrier
from typing import Self

from mini_sla_harness.artifacts import ArtifactStore
from mini_sla_harness.contracts import (
    Command,
    Json,
    Object,
    Principal,
    ProtocolError,
    Role,
    TaskSpec,
    canonical,
    fingerprint,
    require,
    text,
)
from mini_sla_harness.state import StateStore


def expect_error(code: str, action: Callable[[], object]) -> None:
    try:
        action()
    except ProtocolError as error:
        require(error.code == code, "ACCEPTANCE_FAILED", f"Expected {code}, got {error.code}")
    else:
        raise ProtocolError("ACCEPTANCE_FAILED", f"Expected rejection: {code}")


def row(snapshot: Object, table: str, identifier: str | None = None) -> Object:
    entries = snapshot.get(table)
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and (identifier is None or entry.get("id") == identifier):
                return entry
    raise ProtocolError("ACCEPTANCE_FAILED", f"Missing {table}/{identifier}")


class OfflineRun(AbstractContextManager["OfflineRun"]):
    """Deterministic fake Agent/Evaluator/provider around the actual protocol boundary."""

    def __init__(self, root: Path, budget: int = 10000, bps: int = 100) -> None:
        root.mkdir(parents=True, exist_ok=False)
        self.root = root
        self.sequence = 0
        self.now = 10**9
        self.workspace = root / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "processor.py").write_bytes(
            b"def aggregate(data):\n    return []\n"
        )
        self.task = TaskSpec.parse(
            {
                "schema_version": 1,
                "task_id": "jsonl-offline-protocol",
                "editable_files": ["src/processor.py"],
                "metric": "end_to_end_records_per_second",
                "min_improvement_bps": bps,
                "evaluation_spec_hash": fingerprint(
                    {"purpose": "SEARCH", "scoring": "fake-v1", "bps": bps}
                ),
                "audit_spec_hash": fingerprint(
                    {"purpose": "FINAL_AUDIT", "scoring": "fake-v1", "bps": bps}
                ),
            }
        )
        self.artifacts = ArtifactStore(root / "cas")
        self.database = root / "state.sqlite3"
        self.store = StateStore(self.database, self.artifacts, clock=lambda: self.now)
        self.command(
            "CreateRun",
            {
                "task": self.task.value,
                "artifact_hash": self.artifacts.freeze(self.workspace, self.task),
                "budget_limit": budget,
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.store.close()

    def command(
        self,
        kind: str,
        payload: Object | None = None,
        who: Principal | None = None,
        key: str | None = None,
    ) -> Object:
        self.sequence += 1
        command = Command(key or f"command-{self.sequence}", kind, "run", payload or {})
        return self.store.execute(command, who or self.store.controller)

    def reopen(self) -> None:
        self.store.close()
        self.store = StateStore(self.database, self.artifacts, clock=lambda: self.now)

    def principal(self, attempt: str, role: Role) -> Principal:
        return Principal(role, self.store.generation, attempt, "offline")

    def claim(self, kind: str, key: str, identifier: str) -> str:
        attempt = f"attempt-{self.sequence + 1}"
        self.command(
            kind,
            {key: identifier, "attempt_id": attempt, "owner": "offline", "lease_ns": 1000000000},
        )
        return attempt

    def evaluate(self, job: str, score: int | None = 90000, verdict: str = "VALID_SCORED") -> None:
        attempt = self.claim("ClaimEvaluation", "evaluation_id", job)
        self.command(
            "RecordEvaluation",
            {"verdict": verdict, "score_i": score},
            self.principal(attempt, Role.EVALUATOR),
        )

    def initialize(self) -> None:
        self.evaluate("baseline-evaluation")
        self.command("InitializeBaseline")

    def open_plan(self, count: int = 1, max_trials: int = 3) -> tuple[str, str, str]:
        version = row(self.store.snapshot(), "runs")["evidence_version"]
        context = self.artifacts.put(
            {
                "task_spec_hash": self.task.digest,
                "kind": "fake-context",
                "snapshot_version": version,
            }
        )
        result = self.command(
            "OpenEpoch",
            {
                "epoch_id": "epoch",
                "epoch_no": 1,
                "artifact_hash": context,
                "budget_limit": 2000,
                "expected_version": version,
            },
        )
        invocation = text(result, "invocation_id")
        attempt = self.claim("ClaimAdvisor", "invocation_id", invocation)
        assignments: list[Json] = [
            {
                "assignment_id": f"assignment-{i}",
                "branch_id": f"branch-{i}",
                "mode": "NEW",
                "worker_slot": i,
                "max_trials": max_trials,
                "direction_key": f"offline-direction-{i}",
                "hypothesis": "Fixed fake result for protocol verification",
                "objective": "Exercise state transitions",
                "editable_files": [name for name in self.task.editable_files],
            }
            for i in range(count)
        ]
        response = self.artifacts.put({"assignments": assignments})
        return invocation, attempt, response

    def accept_plan(self, count: int = 1, max_trials: int = 3) -> None:
        invocation, attempt, response = self.open_plan(count, max_trials)
        self.command(
            "RecordAdvisorResponse",
            {"artifact_hash": response},
            self.principal(attempt, Role.CONTROLLER),
        )
        self.command("CommitPlan", {"invocation_id": invocation})

    def trial(
        self, identifier: str = "trial", assignment: str = "assignment-0", limit: int = 2000
    ) -> str:
        self.command(
            "CreateTrial",
            {"trial_id": identifier, "assignment_id": assignment, "budget_limit": limit},
        )
        return self.claim("ClaimTrial", "trial_id", identifier)

    def candidate(self, attempt: str) -> str:
        data = f"# candidate from {attempt}\ndef aggregate(data):\n    return []\n".encode()
        (self.workspace / "src" / "processor.py").write_bytes(data)
        result = self.command(
            "SubmitCandidate",
            {"artifact_hash": self.artifacts.freeze(self.workspace, self.task)},
            self.principal(attempt, Role.WORKER),
        )
        return text(result, "evaluation_id")

    def finish(self, trial: str, attempt: str, score: int) -> str:
        job = self.candidate(attempt)
        self.evaluate(job, score)
        self.command("FinalizeTrial", {"trial_id": trial, "evaluation_id": job})
        return job

    def reserve(self, attempt: str, scope: str, call: str, amount: int) -> None:
        self.command(
            "ReserveCall",
            {
                "scope_id": scope,
                "call_id": call,
                "request_hash": fingerprint({"call": call}),
                "input_upper_bound": amount,
                "output_cap": 0,
            },
            self.principal(attempt, Role.GATEWAY),
        )

    def dispatch(self, attempt: str, call: str) -> None:
        self.command("DispatchCall", {"call_id": call}, self.principal(attempt, Role.GATEWAY))

    def settle(self, call: str, input_tokens: int, output_tokens: int = 0, cached: int = 0) -> None:
        self.command(
            "SettleCall",
            {
                "call_id": call,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_input": cached,
                },
            },
            Principal(Role.GATEWAY, self.store.generation),
        )


def promotion(root: Path) -> Object:
    with OfflineRun(root) as run:
        run.initialize()
        run.accept_plan()
        for index, score in enumerate((85000, 83000, 96000)):
            identifier = f"trial-{index}"
            attempt = run.trial(identifier)
            job = run.finish(identifier, attempt, score)
            run.command("FinalizeTrial", {"trial_id": identifier, "evaluation_id": job})
            snapshot = run.store.snapshot()
            expected_head = (85000, 85000, 96000)[index]
            require(
                row(snapshot, "branches")["head_score"] == expected_head,
                "ACCEPTANCE_FAILED",
                "Local retention",
            )
        same: Object = {"trial_id": "trial-2", "evaluation_id": job}
        first = run.command("FinalizeTrial", same, key="same-command")
        require(
            run.command("FinalizeTrial", same, key="same-command") == first,
            "ACCEPTANCE_FAILED",
            "Receipt replay",
        )
        expect_error(
            "IDEMPOTENCY_CONFLICT",
            lambda: run.command("FinalizeTrial", {"trial_id": "trial-0"}, key="same-command"),
        )
        run.reopen()
        snapshot = run.store.snapshot()
        require(
            row(snapshot, "runs")["best_score"] == 96000, "ACCEPTANCE_FAILED", "Global promotion"
        )
        events = snapshot["events"]
        require(
            isinstance(events, list)
            and sum(
                isinstance(event, dict) and event["type"] == "FinalizeTrial" for event in events
            )
            == 3,
            "ACCEPTANCE_FAILED",
            "Duplicate finalization event",
        )
        return {"best_score": 96000, "head_scores": [85000, 85000, 96000]}


def concurrent_budget(root: Path) -> Object:
    with OfflineRun(root, budget=100) as run:
        run.initialize()
        run.accept_plan(count=2)
        attempts = [run.trial(f"trial-{i}", f"assignment-{i}", limit=100) for i in range(2)]
        barrier = Barrier(2)

        def reserve(index: int) -> str:
            barrier.wait(timeout=10)
            command = Command(
                f"competing-{index}",
                "ReserveCall",
                "run",
                {
                    "scope_id": f"trial-{index}",
                    "call_id": f"call-{index}",
                    "request_hash": f"request-{index}",
                    "input_upper_bound": 80,
                    "output_cap": 0,
                },
            )
            try:
                run.store.execute(command, run.principal(attempts[index], Role.GATEWAY))
                return "RESERVED"
            except ProtocolError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, range(2)))
        require(
            sorted(results) == ["BUDGET_EXHAUSTED", "RESERVED"],
            "ACCEPTANCE_FAILED",
            "Competing reservations",
        )
        require(
            row(run.store.snapshot(), "runs")["held"] == 80,
            "ACCEPTANCE_FAILED",
            "Budget conservation",
        )
        outcomes: list[Json] = [value for value in sorted(results)]
        return {"outcomes": outcomes, "held": 80}


def unknown_budget(root: Path) -> Object:
    with OfflineRun(root) as run:
        run.initialize()
        run.accept_plan()
        attempt = run.trial()
        run.reserve(attempt, "trial", "call-original", 1500)
        run.dispatch(attempt, "call-original")
        run.command(
            "UnknownCall", {"call_id": "call-original"}, run.principal(attempt, Role.GATEWAY)
        )
        old_generation = run.store.generation
        run.reopen()
        attempt = run.claim("ClaimTrial", "trial_id", "trial")
        run.reserve(attempt, "trial", "call-retry", 500)
        run.dispatch(attempt, "call-retry")
        expect_error(
            "SCOPE_BUDGET_EXHAUSTED", lambda: run.reserve(attempt, "trial", "call-too-large", 1)
        )
        run.settle("call-original", 1000, 100, 600)
        run.settle("call-original", 1000, 100, 600)
        run.settle("call-retry", 50)
        run.command("ForceStop")
        run.command(
            "SettleCall",
            {
                "call_id": "call-retry",
                "usage": {"input_tokens": 50, "output_tokens": 0, "cached_input": 0},
            },
            Principal(Role.GATEWAY, old_generation),
        )
        snapshot = run.store.snapshot()
        require(
            row(snapshot, "runs")["confirmed"] == 1150 and row(snapshot, "runs")["held"] == 0,
            "ACCEPTANCE_FAILED",
            "UNKNOWN reconciliation",
        )
        expect_error("USAGE_CONFLICT", lambda: run.settle("call-original", 1101))
        expect_error(
            "STATE_CONFLICT",
            lambda: run.command(
                "ReleaseCall",
                {"call_id": "call-original"},
                Principal(Role.GATEWAY, run.store.generation),
            ),
        )
        return {"confirmed": 1150, "held": 0, "cached_input_is_subset": True}


def force_orders(root: Path) -> Object:
    root.mkdir()
    for force_first in (True, False):
        with OfflineRun(root / str(force_first)) as run:
            run.initialize()
            run.accept_plan()
            attempt = run.trial()
            run.reserve(attempt, "trial", "in-flight", 100)
            run.dispatch(attempt, "in-flight")
            job = run.candidate(attempt)
            run.evaluate(job, 110000)

            def finalize(evaluation: str = job) -> Object:
                return run.command(
                    "FinalizeTrial", {"trial_id": "trial", "evaluation_id": evaluation}
                )

            if force_first:
                run.command("ForceStop")
                expect_error("RUN_FORCE_STOPPED", finalize)
            else:
                finalize()
                run.command("ForceStop")
                finalize()
            run.reopen()
            run.command("ForceStop")
            snapshot = run.store.snapshot()
            require(
                row(snapshot, "runs")["best_score"] == (90000 if force_first else 110000),
                "ACCEPTANCE_FAILED",
                "Force/finalize ordering",
            )
            require(
                row(snapshot, "evaluations", job)["state"] == "DONE",
                "ACCEPTANCE_FAILED",
                "DONE evidence retained",
            )
            require(
                row(snapshot, "model_calls")["state"] == "UNKNOWN"
                and row(snapshot, "runs")["held"] == 100,
                "ACCEPTANCE_FAILED",
                "Force cannot erase usage",
            )
            run.settle("in-flight", 73)
    return {"orders_checked": 2, "late_usage_settled": True}


def fencing(root: Path) -> Object:
    with OfflineRun(root) as run:
        run.initialize()
        run.accept_plan()
        old_attempt = run.trial()
        old_worker = run.principal(old_attempt, Role.WORKER)
        run.now += 1000000000
        digest = run.artifacts.freeze(run.workspace, run.task)
        expect_error(
            "STALE_CLAIM",
            lambda: run.command("SubmitCandidate", {"artifact_hash": digest}, old_worker),
        )
        expect_error(
            "STALE_CLAIM",
            lambda: run.command(
                "RenewLease", {"lease_ns": 2000000000}, run.principal(old_attempt, Role.CONTROLLER)
            ),
        )
        new_attempt = run.claim("ClaimTrial", "trial_id", "trial")
        expect_error(
            "STALE_CLAIM",
            lambda: run.command("SubmitCandidate", {"artifact_hash": digest}, old_worker),
        )
        run.finish("trial", new_attempt, 101000)
        previous = run.store.controller
        run.reopen()
        expect_error("STALE_CLAIM", lambda: run.command("Pause", who=previous))
        expect_error("CONTROLLER_BUSY", lambda: StateStore(run.database, run.artifacts))
        return {"expired_and_old_controller_rejected": True, "best_score": 101000}


def baseline_control(root: Path) -> Object:
    root.mkdir()
    for phase in ("queued", "running", "done"):
        with OfflineRun(root / phase) as run:
            attempt = ""
            if phase != "queued":
                attempt = run.claim("ClaimEvaluation", "evaluation_id", "baseline-evaluation")
            if phase == "done":
                run.command(
                    "RecordEvaluation",
                    {"verdict": "VALID_SCORED", "score_i": 90000},
                    run.principal(attempt, Role.EVALUATOR),
                )
            run.command("Pause")
            if phase == "running":
                run.command(
                    "RecordEvaluation",
                    {"verdict": "VALID_SCORED", "score_i": 90000},
                    run.principal(attempt, Role.EVALUATOR),
                )
            if phase != "queued":
                run.command("InitializeBaseline")
            require(
                row(run.store.snapshot(), "runs")["status"] == "PAUSED",
                "ACCEPTANCE_FAILED",
                "Baseline pause barrier",
            )
            run.reopen()
            run.command("Resume")
            snapshot = run.store.snapshot()
            require(
                row(snapshot, "runs")["status"] == ("CREATED" if phase == "queued" else "RUNNING"),
                "ACCEPTANCE_FAILED",
                "Resume initialization phase",
            )
    with OfflineRun(root / "stopped") as run:
        run.command("Stop")
        require(
            row(run.store.snapshot(), "runs")["best_candidate"] is None,
            "ACCEPTANCE_FAILED",
            "No invented baseline",
        )
        require(
            row(run.store.snapshot(), "evaluations")["state"] == "CANCELLED",
            "ACCEPTANCE_FAILED",
            "Queued baseline cancelled",
        )
        expect_error("STATE_CONFLICT", lambda: run.command("Resume"))
    return {"baseline_pause_phases": 3, "unstarted_stop_checked": True}


def advisor_recovery(root: Path) -> Object:
    root.mkdir()
    for phase in ("reserved", "sent", "orphan", "received", "committed"):
        with OfflineRun(root / phase) as run:
            run.initialize()
            invocation, attempt, response = run.open_plan()
            run.reserve(attempt, invocation, "advisor-call", 100)
            if phase != "reserved":
                run.dispatch(attempt, "advisor-call")
            if phase in {"received", "committed"}:
                run.command(
                    "RecordAdvisorResponse",
                    {"artifact_hash": response},
                    run.principal(attempt, Role.CONTROLLER),
                )
            if phase == "committed":
                run.command("CommitPlan", {"invocation_id": invocation})
            run.reopen()
            run.reopen()
            snapshot = run.store.snapshot()
            if phase in {"received", "committed"}:
                run.command("CommitPlan", {"invocation_id": invocation})
                run.command("CommitPlan", {"invocation_id": invocation})
                assignments = run.store.snapshot()["assignments"]
                require(
                    isinstance(assignments, list) and len(assignments) == 1,
                    "ACCEPTANCE_FAILED",
                    "One plan commit",
                )
            else:
                require(
                    row(snapshot, "invocations")["state"] == "PLANNED",
                    "ACCEPTANCE_FAILED",
                    "Unaccepted response is not authoritative",
                )
            expected_call = "RELEASED_UNSENT" if phase == "reserved" else "UNKNOWN"
            require(
                row(snapshot, "model_calls")["state"] == expected_call,
                "ACCEPTANCE_FAILED",
                "Planning reconciliation",
            )
    with OfflineRun(root / "paused-response") as run:
        run.initialize()
        invocation, attempt, response = run.open_plan()
        run.reserve(attempt, invocation, "advisor-call", 100)
        run.dispatch(attempt, "advisor-call")
        run.command("Pause")
        run.command(
            "RecordAdvisorResponse",
            {"artifact_hash": response},
            run.principal(attempt, Role.CONTROLLER),
        )
        expect_error(
            "STATE_CONFLICT", lambda: run.command("CommitPlan", {"invocation_id": invocation})
        )
        run.reopen()
        run.command("Resume")
        run.command("CommitPlan", {"invocation_id": invocation})
    return {"planning_checkpoints": 5, "paused_response_committed_without_new_call": True}


def integer_threshold(root: Path) -> Object:
    root.mkdir()
    for index, score in enumerate((102499, 102500)):
        with OfflineRun(root / str(index), bps=250) as run:
            run.evaluate("baseline-evaluation", 100000)
            run.command("InitializeBaseline")
            run.accept_plan()
            attempt = run.trial()
            run.finish("trial", attempt, score)
            require(
                row(run.store.snapshot(), "runs")["best_score"]
                == (100000 if index == 0 else 102500),
                "ACCEPTANCE_FAILED",
                "Integer threshold boundary",
            )
    with OfflineRun(root / "zero", bps=0) as run:
        run.initialize()
        run.accept_plan()
        attempt = run.trial()
        run.finish("trial", attempt, 90000)
        require(
            row(run.store.snapshot(), "runs")["best_candidate"] == "baseline",
            "ACCEPTANCE_FAILED",
            "Zero bps still needs +1",
        )
    return {
        "below_threshold_rejected": 102499,
        "exact_threshold_accepted": 102500,
        "zero_bps_requires_one": True,
    }


def controlled_process_stop(root: Path) -> Object:
    with OfflineRun(root) as run:
        run.initialize()
        run.accept_plan()
        attempt = run.trial()
        worker = run.principal(attempt, Role.WORKER)
        run.reserve(attempt, "trial", "started-call", 100)
        run.dispatch(attempt, "started-call")
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            require(process.poll() is None, "ACCEPTANCE_FAILED", "Fake process did not start")
            run.command("ForceStop")
            require(
                row(run.store.snapshot(), "trials")["state"] == "CANCELLED",
                "ACCEPTANCE_FAILED",
                "Durable fence must precede OS termination",
            )
            process.terminate()
            process.wait(timeout=5)
            digest = run.artifacts.freeze(run.workspace, run.task)
            expect_error(
                "STALE_CLAIM",
                lambda: run.command(
                    "SubmitCandidate",
                    {"artifact_hash": digest},
                    worker,
                ),
            )
            run.settle("started-call", 27)
            return {"process_exited": process.poll() is not None, "late_usage_tokens": 27}
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def artifact_contract(root: Path) -> Object:
    with OfflineRun(root) as run:
        invalid = run.task.value.copy()
        del invalid["editable_files"]
        expect_error("INVALID_TASK", lambda: TaskSpec.parse(invalid))
        digest = run.artifacts.freeze(run.workspace, run.task)
        run.artifacts.materialize(digest, run.task, root / "reconstructed")
        require(
            (root / "reconstructed/src/processor.py").read_bytes()
            == (run.workspace / "src/processor.py").read_bytes(),
            "ACCEPTANCE_FAILED",
            "Snapshot reconstruction",
        )
        run.artifacts.path(digest).write_bytes(b"corrupt object")
        expect_error("ARTIFACT_CORRUPT", lambda: run.artifacts.read(digest))
        run.reopen()
        require(
            row(run.store.snapshot(), "runs")["completion_reason"] == "ARTIFACT_CORRUPT",
            "ACCEPTANCE_FAILED",
            "Corrupt reference must fail recovery",
        )
        return {"missing_task_field_rejected": True, "corrupt_reference_rejected": True}


SCENARIOS: tuple[tuple[str, tuple[str, ...], Callable[[Path], Object]], ...] = (
    ("task-and-artifacts", ("T-01", "T-06"), artifact_contract),
    ("promotion-idempotency", ("T-03", "T-07", "T-27"), promotion),
    ("competing-reservations", ("T-16",), concurrent_budget),
    ("unknown-scope-accounting", ("T-17", "T-18", "T-26"), unknown_budget),
    ("force-finalize-orders", ("T-15", "T-24"), force_orders),
    ("leases-and-controller", ("T-11",), fencing),
    ("baseline-pause-resume", ("T-25",), baseline_control),
    ("advisor-recovery", ("T-25", "T-26"), advisor_recovery),
    ("integer-thresholds", ("T-27",), integer_threshold),
    ("controlled-process-force-stop", ("T-15",), controlled_process_stop),
)


def run_acceptance(output: Path) -> Object:
    """Refuse an existing destination so a failed run cannot erase earlier evidence."""
    output.mkdir(parents=True, exist_ok=False)
    results: list[Json] = []
    for name, requirements, check in SCENARIOS:
        try:
            observed = check(output / name)
            databases: list[Json] = [
                path.relative_to(output).as_posix()
                for path in sorted((output / name).rglob("state.sqlite3"))
            ]
            results.append(
                {
                    "name": name,
                    "requirements": list(requirements),
                    "status": "passed",
                    "observed": observed,
                    "databases": databases,
                }
            )
        except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
            results.append(
                {
                    "name": name,
                    "requirements": list(requirements),
                    "status": "failed",
                    "error": str(error),
                }
            )
    failed = [item for item in results if isinstance(item, dict) and item["status"] != "passed"]
    report: Object = {
        "schema_version": 1,
        "status": "failed" if failed else "passed",
        "provider": "deterministic-protocol-fake-v1",
        "external_model_requests": 0,
        "usage_kind": "simulated_tokens",
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "research_effect": "not_evaluated",
        "scenarios": results,
        "pending": [
            "docker_isolation",
            "windows_control_pipe",
            "power_loss_durability",
            "real_provider",
            "performance_calibration",
        ],
    }
    (output / "report.json").write_bytes(canonical(report) + b"\n")
    return report
