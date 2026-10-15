"""Single-controller transactional protocol. All identities here are trusted in-process inputs."""

import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, closing
from pathlib import Path
from typing import Self, cast

from mini_sla_harness.artifacts import ArtifactStore
from mini_sla_harness.contracts import (
    MAX_INT,
    Command,
    Json,
    Object,
    Principal,
    ProtocolError,
    Role,
    TaskSpec,
    assignment_spec,
    canonical,
    fingerprint,
    integer,
    parse_object,
    require,
    text,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(version INTEGER NOT NULL, generation INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
 id TEXT PRIMARY KEY, status TEXT NOT NULL, resume_phase TEXT NOT NULL,
 stop_mode TEXT NOT NULL DEFAULT 'NONE', completion_reason TEXT,
 task_json TEXT NOT NULL, task_spec_hash TEXT NOT NULL, evaluation_spec_hash TEXT NOT NULL,
 audit_spec_hash TEXT NOT NULL, bps INTEGER NOT NULL CHECK(bps BETWEEN 0 AND 10000),
 controller_generation INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 0,
 evidence_version INTEGER NOT NULL DEFAULT 0,
 budget_limit INTEGER NOT NULL CHECK(budget_limit>=0),
 confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed>=0),
 held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0), budget_breach INTEGER NOT NULL DEFAULT 0,
 baseline_id TEXT NOT NULL, best_candidate TEXT, best_evaluation TEXT, best_score INTEGER,
 CHECK((best_candidate IS NULL AND best_evaluation IS NULL AND best_score IS NULL)
 OR (best_candidate IS NOT NULL AND best_evaluation IS NOT NULL AND best_score IS NOT NULL)));
CREATE TABLE IF NOT EXISTS candidates(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 parent TEXT REFERENCES candidates(id),
 trial_id TEXT UNIQUE, attempt_id TEXT, artifact_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluations(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 candidate_id TEXT NOT NULL REFERENCES candidates(id), purpose TEXT NOT NULL,
 spec_hash TEXT NOT NULL, request_key TEXT NOT NULL UNIQUE, state TEXT NOT NULL DEFAULT 'QUEUED',
 started INTEGER NOT NULL DEFAULT 0, verdict TEXT, score INTEGER, result_hash TEXT,
 CHECK((state='DONE' AND verdict IS NOT NULL) OR (state<>'DONE' AND verdict IS NULL)),
 CHECK((verdict='VALID_SCORED' AND score IS NOT NULL AND score>=0)
 OR (verdict IS NOT 'VALID_SCORED' AND score IS NULL)));
CREATE TABLE IF NOT EXISTS epochs(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), epoch_no INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'PLANNING', snapshot_version INTEGER NOT NULL,
 context_hash TEXT NOT NULL, plan_hash TEXT, UNIQUE(run_id,epoch_no));
CREATE TABLE IF NOT EXISTS invocations(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 epoch_id TEXT NOT NULL UNIQUE REFERENCES epochs(id), state TEXT NOT NULL DEFAULT 'PLANNED',
 response_hash TEXT, repairs INTEGER NOT NULL DEFAULT 0 CHECK(repairs BETWEEN 0 AND 1),
 replans INTEGER NOT NULL DEFAULT 0 CHECK(replans BETWEEN 0 AND 1));
CREATE TABLE IF NOT EXISTS branches(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 base TEXT NOT NULL REFERENCES candidates(id), head_candidate TEXT REFERENCES candidates(id),
 head_evaluation TEXT REFERENCES evaluations(id), head_score INTEGER,
 CHECK((head_candidate IS NULL AND head_evaluation IS NULL AND head_score IS NULL)
 OR (head_candidate IS NOT NULL AND head_evaluation IS NOT NULL AND head_score IS NOT NULL)));
CREATE TABLE IF NOT EXISTS assignments(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 epoch_id TEXT NOT NULL REFERENCES epochs(id), branch_id TEXT NOT NULL REFERENCES branches(id),
 worker_slot INTEGER NOT NULL, max_trials INTEGER NOT NULL CHECK(max_trials BETWEEN 1 AND 3),
 spec_json TEXT NOT NULL, spec_hash TEXT NOT NULL,
 trials_created INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'READY', end_reason TEXT,
 UNIQUE(epoch_id,worker_slot), UNIQUE(epoch_id,branch_id));
CREATE TABLE IF NOT EXISTS trials(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 assignment_id TEXT NOT NULL REFERENCES assignments(id),
 branch_id TEXT NOT NULL REFERENCES branches(id),
 trial_no INTEGER NOT NULL, base TEXT NOT NULL REFERENCES candidates(id), state TEXT NOT NULL,
 accepted_attempt TEXT, candidate_id TEXT REFERENCES candidates(id),
 evaluation_id TEXT REFERENCES evaluations(id), finalization_hash TEXT,
 UNIQUE(assignment_id,trial_no));
CREATE UNIQUE INDEX IF NOT EXISTS active_trial ON trials(branch_id)
 WHERE state IN ('PENDING','RUNNING','CANDIDATE_READY','EVALUATING');
CREATE TABLE IF NOT EXISTS attempts(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
 object_id TEXT NOT NULL, generation INTEGER NOT NULL, controller_generation INTEGER NOT NULL,
 owner TEXT NOT NULL, lease_deadline INTEGER NOT NULL, state TEXT NOT NULL,
 UNIQUE(kind,object_id,generation));
CREATE TABLE IF NOT EXISTS budget_scopes(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
 owner_id TEXT NOT NULL, limit_tokens INTEGER NOT NULL CHECK(limit_tokens>=0),
 confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed>=0),
 held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0), UNIQUE(kind,owner_id));
CREATE TABLE IF NOT EXISTS model_calls(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 scope_id TEXT NOT NULL REFERENCES budget_scopes(id),
 attempt_id TEXT NOT NULL REFERENCES attempts(id),
 request_hash TEXT NOT NULL, reserved INTEGER NOT NULL CHECK(reserved>=0), state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage_ledger(
 call_id TEXT PRIMARY KEY REFERENCES model_calls(id), receipt_hash TEXT NOT NULL,
 input_tokens INTEGER NOT NULL CHECK(input_tokens>=0),
 output_tokens INTEGER NOT NULL CHECK(output_tokens>=0),
 cached_input INTEGER NOT NULL CHECK(cached_input>=0 AND cached_input<=input_tokens),
 raw_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS command_receipts(
 id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, result_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 command_id TEXT NOT NULL, type TEXT NOT NULL, result_json TEXT NOT NULL);
"""

TERMINAL = {"COMPLETED", "FAILED"}
FINAL_TRIAL = {"COMPLETED", "CANCELLED", "FAILED"}


class StateStore(AbstractContextManager["StateStore"]):
    def __init__(
        self,
        path: Path,
        artifacts: ArtifactStore,
        run_id: str = "run",
        clock: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.path = path.resolve()
        self.artifacts = artifacts
        self.run_id = run_id
        self.clock = clock
        self.mutex = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            if self.lock.tell() == 0:
                self.lock.write(b"\0")
                self.lock.flush()
            self.lock.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock.close()
            raise ProtocolError("CONTROLLER_BUSY", str(path)) from error
        try:
            self.connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            tables = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            names = {str(row[0]) for row in tables}
            require(
                not names or "metadata" in names, "INVALID_DATABASE", "Not a StateStore database"
            )
            if "metadata" in names:
                version = self.connection.execute("SELECT version FROM metadata").fetchone()
                require(
                    version is None or version[0] == 1,
                    "SCHEMA_MISMATCH",
                    "Unsupported StateStore schema",
                )
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self.connection.execute("PRAGMA busy_timeout=2000")
            self.connection.executescript(SCHEMA)
            existing_runs = self.connection.execute("SELECT id FROM runs").fetchall()
            require(
                not existing_runs
                or (len(existing_runs) == 1 and existing_runs[0][0] == self.run_id),
                "RUN_MISMATCH",
                "One Run per StateStore database",
            )
            artifacts_valid = True
            if existing_runs:
                try:
                    task_spec = self._task()
                    for candidate in self._rows("SELECT * FROM candidates"):
                        self.artifacts.files(text(candidate, "artifact_hash"), task_spec)
                    for table, column in (
                        ("epochs", "context_hash"),
                        ("invocations", "response_hash"),
                    ):
                        for entry in self._rows(f"SELECT * FROM {table}"):
                            if entry[column] is not None:
                                self.artifacts.read(text(entry, column))
                except OSError, ValueError:
                    artifacts_valid = False
            with self.connection:
                meta = self.connection.execute("SELECT * FROM metadata").fetchone()
                if meta is None:
                    self.connection.execute("INSERT INTO metadata VALUES (1,0)")
                else:
                    require(
                        meta["version"] == 1, "SCHEMA_MISMATCH", "Unsupported StateStore schema"
                    )
                self.connection.execute("UPDATE metadata SET generation=generation+1")
                self.generation = int(
                    self.connection.execute("SELECT generation FROM metadata").fetchone()[0]
                )
                if existing_runs:
                    self._recover(artifacts_valid)
                    self.connection.execute(
                        "INSERT INTO events(run_id,command_id,type,result_json) VALUES (?,?,?,?)",
                        (
                            self.run_id,
                            f"controller:{self.generation}",
                            "RecoverController",
                            canonical(
                                {"generation": self.generation, "status": self._run()["status"]}
                            ).decode(),
                        ),
                    )
        except BaseException:
            if hasattr(self, "connection"):
                self.connection.close()
            self.lock.close()
            raise

    def __enter__(self) -> Self:
        return self

    def close(self) -> None:
        self.connection.close()
        self.lock.close()

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def controller(self) -> Principal:
        return Principal(Role.CONTROLLER, self.generation)

    def _rows(self, sql: str, parameters: tuple[Json, ...] = ()) -> list[Object]:
        return [cast(Object, dict(row)) for row in self.connection.execute(sql, parameters)]

    def _one(self, table: str, identifier: str) -> Object:
        rows = self._rows(f"SELECT * FROM {table} WHERE id=?", (identifier,))
        require(bool(rows), "NOT_FOUND", f"{table}: {identifier}")
        row = rows[0]
        require(
            row.get("run_id", row.get("id") if table == "runs" else None) == self.run_id,
            "RUN_MISMATCH",
            identifier,
        )
        return row

    def _run(self) -> Object:
        return self._one("runs", self.run_id)

    def _write(self, sql: str, parameters: tuple[Json, ...] = ()) -> None:
        self.connection.execute(sql, parameters)
        self.changed = True

    def _task(self) -> TaskSpec:
        run = self._run()
        task = TaskSpec.parse(parse_object(text(run, "task_json")))
        require(task.digest == run["task_spec_hash"], "ARTIFACT_CORRUPT", "TaskSpec hash mismatch")
        return task

    def snapshot(self) -> Object:
        """A fresh read connection observes only committed facts."""
        with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True)) as reader:
            reader.row_factory = sqlite3.Row
            reader.execute("BEGIN")
            result: Object = {}
            for table in (
                "runs",
                "epochs",
                "invocations",
                "branches",
                "assignments",
                "trials",
                "attempts",
                "candidates",
                "evaluations",
                "budget_scopes",
                "model_calls",
                "usage_ledger",
                "events",
            ):
                result[table] = [
                    cast(Object, dict(row)) for row in reader.execute(f"SELECT * FROM {table}")
                ]
            reader.rollback()

        def records(table: str) -> list[Object]:
            entries = result[table]
            if not isinstance(entries, list) or not all(
                isinstance(entry, dict) for entry in entries
            ):
                raise ProtocolError("STATE_CORRUPT", table)
            return [entry for entry in entries if isinstance(entry, dict)]

        runs = records("runs")
        if runs:
            run = runs[0]
            calls = records("model_calls")
            reserved = sum(
                integer(call, "reserved")
                for call in calls
                if call["state"] in {"RESERVED", "DISPATCH_INTENT"}
            )
            unknown = sum(integer(call, "reserved") for call in calls if call["state"] == "UNKNOWN")
            confirmed = sum(
                integer(usage, "input_tokens") + integer(usage, "output_tokens")
                for usage in records("usage_ledger")
            )
            require(
                confirmed == run["confirmed"]
                and reserved + unknown == run["held"]
                and sum(integer(scope, "confirmed") for scope in records("budget_scopes"))
                == confirmed
                and sum(integer(scope, "held") for scope in records("budget_scopes"))
                == reserved + unknown,
                "ACCOUNTING_CORRUPT",
                "Run, scopes and call ledger disagree",
            )
            result["accounting"] = {
                "confirmed": confirmed,
                "held_reserved": reserved,
                "held_unknown": unknown,
                "available": max(0, integer(run, "budget_limit") - confirmed - reserved - unknown),
                "state": "OPEN" if reserved + unknown else "CLOSED",
            }
        return result

    def execute(self, command: Command, who: Principal) -> Object:
        handlers: dict[str, tuple[Role, Callable[[Object, Principal], Object]]] = {
            "CreateRun": (Role.CONTROLLER, self._create_run),
            "InitializeBaseline": (Role.CONTROLLER, self._initialize_baseline),
            "OpenEpoch": (Role.CONTROLLER, self._open_epoch),
            "ClaimAdvisor": (Role.CONTROLLER, self._claim_advisor),
            "RecordAdvisorResponse": (Role.CONTROLLER, self._record_response),
            "RetryAdvisor": (Role.CONTROLLER, self._retry_advisor),
            "CommitPlan": (Role.CONTROLLER, self._commit_plan),
            "CreateTrial": (Role.CONTROLLER, self._create_trial),
            "ClaimTrial": (Role.CONTROLLER, self._claim_trial),
            "RenewLease": (Role.CONTROLLER, self._renew),
            "SubmitCandidate": (Role.WORKER, self._submit),
            "ClaimEvaluation": (Role.CONTROLLER, self._claim_evaluation),
            "RecordEvaluation": (Role.EVALUATOR, self._record_evaluation),
            "FinalizeTrial": (Role.CONTROLLER, self._finalize),
            "ReserveCall": (Role.GATEWAY, self._reserve),
            "DispatchCall": (Role.GATEWAY, self._dispatch),
            "UnknownCall": (Role.GATEWAY, self._unknown),
            "ReleaseCall": (Role.GATEWAY, self._release),
            "SettleCall": (Role.GATEWAY, self._settle),
            "Pause": (Role.CONTROLLER, self._pause),
            "Resume": (Role.CONTROLLER, self._resume),
            "Stop": (Role.CONTROLLER, self._stop),
            "ForceStop": (Role.CONTROLLER, self._force),
        }
        require(command.run_id == self.run_id, "RUN_MISMATCH", command.run_id)
        command = Command(
            command.command_id,
            command.type,
            command.run_id,
            parse_object(canonical(command.payload)),
        )
        require(bool(command.command_id), "INVALID_COMMAND", "command_id required")
        entry = handlers.get(command.type)
        require(entry is not None, "INVALID_COMMAND", command.type)
        if entry is None:
            raise ProtocolError("INVALID_COMMAND", command.type)
        role, handler = entry
        require(who.role == role, "FORBIDDEN", command.type)
        digest = command.digest
        with self.mutex:
            receipt = self.connection.execute(
                "SELECT * FROM command_receipts WHERE id=?", (command.command_id,)
            ).fetchone()
            if receipt is not None:
                require(
                    receipt["request_hash"] == digest, "IDEMPOTENCY_CONFLICT", command.command_id
                )
                return outcome(parse_object(receipt["result_json"]))
            # Object IO finishes before entering the database write transaction.
            if command.type == "CreateRun":
                task = command.payload.get("task")
                require(isinstance(task, dict), "INVALID_TASK", "task required")
                if isinstance(task, dict):
                    self.artifacts.files(
                        text(command.payload, "artifact_hash"), TaskSpec.parse(task)
                    )
            elif command.type == "SubmitCandidate":
                task_spec = self._task()
                files = self.artifacts.files(text(command.payload, "artifact_hash"), task_spec)
                attempt = self._one("attempts", who.attempt_id)
                trial = self._one("trials", text(attempt, "object_id"))
                base = self._one("candidates", text(trial, "base"))
                original = self.artifacts.files(text(base, "artifact_hash"), task_spec)
                assignment = self._one("assignments", text(trial, "assignment_id"))
                allowed = parse_object(text(assignment, "spec_json"))["editable_files"]
                require(
                    isinstance(allowed, list)
                    and all(
                        name in allowed or data == original[name] for name, data in files.items()
                    ),
                    "ARTIFACT_INVALID",
                    "Candidate exceeds Assignment edit scope",
                )
            elif command.type in {"OpenEpoch", "RecordAdvisorResponse"}:
                prepared_object = parse_object(
                    self.artifacts.read(text(command.payload, "artifact_hash"))
                )
                if command.type == "OpenEpoch":
                    self.prepared_context = prepared_object
            elif command.type == "ClaimEvaluation":
                candidate = self._one(
                    "candidates",
                    text(
                        self._one("evaluations", text(command.payload, "evaluation_id")),
                        "candidate_id",
                    ),
                )
                self.artifacts.files(text(candidate, "artifact_hash"), self._task())
            elif command.type == "CommitPlan":
                invocation = self._one("invocations", text(command.payload, "invocation_id"))
                self.prepared_plan = parse_object(
                    self.artifacts.read(text(invocation, "response_hash"))
                )
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                prior = self.connection.execute(
                    "SELECT * FROM command_receipts WHERE id=?", (command.command_id,)
                ).fetchone()
                if prior is not None:
                    require(
                        prior["request_hash"] == digest, "IDEMPOTENCY_CONFLICT", command.command_id
                    )
                    result = parse_object(prior["result_json"])
                else:
                    if command.type != "SettleCall":
                        expected = (
                            self.generation
                            if command.type == "CreateRun"
                            else integer(self._run(), "controller_generation")
                        )
                        require(
                            who.controller_generation == expected,
                            "STALE_CLAIM",
                            "Controller generation",
                        )
                    self.changed = False
                    result = handler(command.payload, who)
                    if self.changed:
                        self.connection.execute(
                            (
                                "INSERT INTO events(run_id,command_id,type,result_json) VALUES "
                                "(?,?,?,?)"
                            ),
                            (
                                self.run_id,
                                command.command_id,
                                command.type,
                                canonical(result).decode(),
                            ),
                        )
                        self.connection.execute(
                            "UPDATE runs SET version=version+1 WHERE id=?", (self.run_id,)
                        )
                        if command.type in {
                            "InitializeBaseline",
                            "CommitPlan",
                            "CreateTrial",
                            "FinalizeTrial",
                        }:
                            self.connection.execute(
                                "UPDATE runs SET evidence_version=evidence_version+1 WHERE id=?",
                                (self.run_id,),
                            )
                    self.connection.execute(
                        "INSERT INTO command_receipts VALUES (?,?,?)",
                        (command.command_id, digest, canonical(result).decode()),
                    )
                self.connection.commit()
            except sqlite3.IntegrityError as error:
                self.connection.rollback()
                raise ProtocolError("STATE_CONFLICT", str(error)) from error
            except BaseException:
                self.connection.rollback()
                raise
            self.generation = int(
                self.connection.execute("SELECT generation FROM metadata").fetchone()[0]
            )
            return outcome(result)

    def _running(self) -> Object:
        run = self._run()
        require(
            run["status"] == "RUNNING" and run["stop_mode"] == "NONE",
            "STATE_CONFLICT",
            "Run not running",
        )
        return run

    def _create_run(self, p: Object, who: Principal) -> Object:
        require(not self._rows("SELECT id FROM runs"), "RESULT_CONFLICT", "Run already exists")
        raw = p.get("task")
        require(isinstance(raw, dict), "INVALID_TASK", "task required")
        if not isinstance(raw, dict):
            raise ProtocolError("INVALID_TASK", "task required")
        task = TaskSpec.parse(raw)
        limit = integer(p, "budget_limit")
        baseline, job = "baseline", "baseline-evaluation"
        self._write(
            (
                "INSERT INTO runs(id,status,resume_phase,task_json,task_spec_hash,"
                "evaluation_spec_hash,audit_spec_hash,bps,controller_generation,bu"
                "dget_limit,baseline_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                self.run_id,
                "CREATED",
                "INITIALIZING",
                canonical(task.value).decode(),
                task.digest,
                text(task.value, "evaluation_spec_hash"),
                text(task.value, "audit_spec_hash"),
                integer(task.value, "min_improvement_bps", 0, 10000),
                who.controller_generation,
                limit,
                job,
            ),
        )
        self._write(
            "INSERT INTO candidates VALUES (?,?,NULL,NULL,NULL,?)",
            (baseline, self.run_id, text(p, "artifact_hash")),
        )
        self._write(
            (
                "INSERT INTO "
                "evaluations(id,run_id,candidate_id,purpose,spec_hash,request_key)"
                " VALUES (?,?,?,?,?,?)"
            ),
            (
                job,
                self.run_id,
                baseline,
                "BASELINE",
                text(task.value, "evaluation_spec_hash"),
                f"baseline:{self.run_id}:{task.digest}",
            ),
        )
        return {"baseline_id": job, "candidate_id": baseline}

    def _initialize_baseline(self, p: Object, who: Principal) -> Object:
        run = self._run()
        require(run["stop_mode"] != "FORCE", "RUN_FORCE_STOPPED", self.run_id)
        if run["best_candidate"] is not None:
            return {"candidate_id": run["best_candidate"]}
        job = self._one("evaluations", text(run, "baseline_id"))
        require(
            job["state"] == "DONE" and job["purpose"] == "BASELINE",
            "STATE_CONFLICT",
            "Baseline not done",
        )
        if job["verdict"] != "VALID_SCORED":
            self._write("UPDATE runs SET status='FAILED',completion_reason='BASELINE_INVALID'")
            return {"status": "FAILED"}
        status = "RUNNING"
        if run["status"] == "PAUSING":
            status = "PAUSED"
        elif run["stop_mode"] == "DRAIN":
            status = "COMPLETED"
        self._write(
            (
                "UPDATE runs SET status=?,resume_phase='READY_TO_RUN',best_candida"
                "te=?,best_evaluation=?,best_score=?"
            ),
            (status, job["candidate_id"], job["id"], job["score"]),
        )
        return {"candidate_id": job["candidate_id"], "status": status}

    def _open_epoch(self, p: Object, who: Principal) -> Object:
        run = self._running()
        require(run["best_candidate"] is not None, "STATE_CONFLICT", "Baseline required")
        require(
            not self._rows(
                "SELECT id FROM epochs WHERE state NOT IN ('CLOSED','CANCELLED','FAILED')"
            ),
            "STATE_CONFLICT",
            "Epoch already active",
        )
        identifier = text(p, "epoch_id")
        invocation = f"advisor:{identifier}"
        version = integer(run, "evidence_version")
        require(
            integer(p, "expected_version") == version, "STALE_SNAPSHOT", "Context snapshot changed"
        )
        require(
            self.prepared_context.get("snapshot_version") == version
            and self.prepared_context.get("task_spec_hash") == run["task_spec_hash"],
            "STALE_SNAPSHOT",
            "Context identity does not match the Run",
        )
        self._write(
            (
                "INSERT INTO "
                "epochs(id,run_id,epoch_no,snapshot_version,context_hash) VALUES "
                "(?,?,?,?,?)"
            ),
            (identifier, self.run_id, integer(p, "epoch_no", 1), version, text(p, "artifact_hash")),
        )
        self._write(
            "INSERT INTO invocations(id,run_id,epoch_id) VALUES (?,?,?)",
            (invocation, self.run_id, identifier),
        )
        self._scope(invocation, "ADVISOR", invocation, integer(p, "budget_limit"))
        return {"invocation_id": invocation, "snapshot_version": version}

    def _scope(self, identifier: str, kind: str, owner: str, limit: int) -> None:
        self._write(
            "INSERT INTO budget_scopes(id,run_id,kind,owner_id,limit_tokens) VALUES (?,?,?,?,?)",
            (identifier, self.run_id, kind, owner, limit),
        )

    def _claim(self, kind: str, identifier: str, p: Object, who: Principal) -> Object:
        previous = self._rows(
            "SELECT * FROM attempts WHERE kind=? AND object_id=? ORDER BY generation DESC",
            (kind, identifier),
        )
        if previous and previous[0]["state"] == "ACTIVE":
            require(
                integer(previous[0], "lease_deadline") <= self.clock(),
                "STATE_CONFLICT",
                "Attempt still active",
            )
            self._write("UPDATE attempts SET state='EXPIRED' WHERE id=?", (previous[0]["id"],))
        generation = integer(previous[0], "generation") + 1 if previous else 1
        if generation > 3:
            if kind == "EVALUATION":
                job = self._one("evaluations", identifier)
                self._write("UPDATE evaluations SET state='FAILED' WHERE id=?", (identifier,))
                self._write("UPDATE trials SET state='FAILED' WHERE evaluation_id=?", (identifier,))
                if job["purpose"] == "BASELINE":
                    self._write(
                        "UPDATE runs SET status='FAILED',"
                        "completion_reason='BASELINE_INFRA_EXHAUSTED'"
                    )
            else:
                self._fail_scope(self._one("budget_scopes", identifier), "RETRY_EXHAUSTED")
            return {"error_code": "RETRY_EXHAUSTED", "message": identifier}
        attempt = text(p, "attempt_id")
        owner = text(p, "owner")
        deadline = self.clock() + integer(p, "lease_ns", 1, 3600 * 10**9)
        self._write(
            "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                attempt,
                self.run_id,
                kind,
                identifier,
                generation,
                who.controller_generation,
                owner,
                deadline,
                "ACTIVE",
            ),
        )
        return {
            "attempt_id": attempt,
            "generation": generation,
            "owner": owner,
            "lease_deadline": deadline,
        }

    def _valid_attempt(self, who: Principal, kind: str | None = None) -> Object:
        attempt = self._one("attempts", who.attempt_id)
        require(
            attempt["state"] == "ACTIVE"
            and attempt["owner"] == who.owner
            and attempt["controller_generation"] == who.controller_generation
            and (kind is None or attempt["kind"] == kind)
            and integer(attempt, "lease_deadline") > self.clock(),
            "STALE_CLAIM",
            who.attempt_id,
        )
        return attempt

    def _claim_advisor(self, p: Object, who: Principal) -> Object:
        self._running()
        invocation = self._one("invocations", text(p, "invocation_id"))
        require(
            invocation["state"] in {"PLANNED", "REQUESTING"},
            "STATE_CONFLICT",
            "Advisor not claimable",
        )
        result = self._claim("ADVISOR", text(invocation, "id"), p, who)
        if "error_code" in result:
            return result
        self._write("UPDATE invocations SET state='REQUESTING' WHERE id=?", (invocation["id"],))
        return result

    def _record_response(self, p: Object, who: Principal) -> Object:
        attempt = self._valid_attempt(who, "ADVISOR")
        invocation = self._one("invocations", text(attempt, "object_id"))
        require(
            self._run()["status"] in {"RUNNING", "PAUSING"} and invocation["state"] == "REQUESTING",
            "STATE_CONFLICT",
            "Advisor response rejected",
        )
        self._write(
            "UPDATE invocations SET state='PLAN_RECEIVED',response_hash=? WHERE id=?",
            (text(p, "artifact_hash"), invocation["id"]),
        )
        self._write("UPDATE attempts SET state='SUCCEEDED' WHERE id=?", (attempt["id"],))
        self._pause_barrier()
        return {"invocation_id": invocation["id"], "response_hash": text(p, "artifact_hash")}

    def _retry_advisor(self, p: Object, who: Principal) -> Object:
        self._running()
        invocation = self._one("invocations", text(p, "invocation_id"))
        require(invocation["state"] == "PLAN_RECEIVED", "STATE_CONFLICT", "No response to revise")
        mode = text(p, "reason")
        require(mode in {"repairs", "replans"}, "INVALID_INPUT", "Expected repairs or replans")
        if integer(invocation, mode) >= 1:
            self._fail_scope(
                self._one("budget_scopes", text(invocation, "id")), "ADVISOR_PLAN_EXHAUSTED"
            )
            return {"error_code": "ADVISOR_PLAN_EXHAUSTED", "message": mode}
        self._write(
            f"UPDATE invocations SET {mode}={mode}+1,state='PLANNED' WHERE id=?",
            (invocation["id"],),
        )
        if mode == "replans":
            self._write(
                "UPDATE epochs SET snapshot_version=? WHERE id=?",
                (integer(self._run(), "evidence_version"), invocation["epoch_id"]),
            )
        return {"invocation_id": invocation["id"]}

    def _commit_plan(self, p: Object, who: Principal) -> Object:
        run = self._running()
        invocation = self._one("invocations", text(p, "invocation_id"))
        epoch = self._one("epochs", text(invocation, "epoch_id"))
        response = text(invocation, "response_hash")
        if invocation["state"] == "COMMITTED":
            return {"epoch_id": epoch["id"], "plan_hash": response}
        require(invocation["state"] == "PLAN_RECEIVED", "STATE_CONFLICT", "No accepted response")
        require(
            epoch["snapshot_version"] == run["evidence_version"],
            "STALE_SNAPSHOT",
            "Research evidence changed",
        )
        plan = self.prepared_plan
        entries = plan.get("assignments")
        require(
            isinstance(entries, list) and len(entries) <= 3,
            "PLAN_INVALID",
            "Expected up to 3 assignments",
        )
        if not isinstance(entries, list):
            raise ProtocolError("PLAN_INVALID", "assignments required")
        for item in entries:
            require(isinstance(item, dict), "PLAN_INVALID", "Invalid assignment")
            if not isinstance(item, dict):
                continue
            item = assignment_spec(item, self._task())
            branch = text(item, "branch_id")
            mode = text(item, "mode")
            require(mode in {"NEW", "CONTINUE"}, "PLAN_INVALID", "Invalid branch mode")
            if mode == "NEW":
                self._write(
                    "INSERT INTO branches(id,run_id,base) VALUES (?,?,?)",
                    (branch, self.run_id, run["best_candidate"]),
                )
            else:
                self._one("branches", branch)
                require(
                    not self._rows(
                        (
                            "SELECT id FROM trials WHERE branch_id=? AND state NOT IN "
                            "('COMPLETED','FAILED','CANCELLED')"
                        ),
                        (branch,),
                    ),
                    "STATE_CONFLICT",
                    "Branch active",
                )
            self._write(
                (
                    "INSERT INTO "
                    "assignments(id,run_id,epoch_id,branch_id,worker_slot,max_trials,spec_json,"
                    "spec_hash) VALUES (?,?,?,?,?,?,?,?)"
                ),
                (
                    text(item, "assignment_id"),
                    self.run_id,
                    epoch["id"],
                    branch,
                    integer(item, "worker_slot", 0, 2),
                    integer(item, "max_trials", 1, 3),
                    canonical(item).decode(),
                    fingerprint(item),
                ),
            )
        self._write("UPDATE invocations SET state='COMMITTED' WHERE id=?", (invocation["id"],))
        self._write(
            "UPDATE epochs SET state=?,plan_hash=? WHERE id=?",
            ("READY" if entries else "CLOSED", response, epoch["id"]),
        )
        return {"epoch_id": epoch["id"], "plan_hash": response}

    def _create_trial(self, p: Object, who: Principal) -> Object:
        self._running()
        assignment = self._one("assignments", text(p, "assignment_id"))
        require(
            assignment["state"] in {"READY", "RUNNING"}
            and integer(assignment, "trials_created") < integer(assignment, "max_trials"),
            "STATE_CONFLICT",
            "Assignment quota exhausted",
        )
        branch = self._one("branches", text(assignment, "branch_id"))
        trial = text(p, "trial_id")
        number = integer(assignment, "trials_created") + 1
        base = branch["head_candidate"] or branch["base"]
        self._write(
            (
                "INSERT INTO "
                "trials(id,run_id,assignment_id,branch_id,trial_no,base,state) "
                "VALUES (?,?,?,?,?,?,'PENDING')"
            ),
            (trial, self.run_id, assignment["id"], branch["id"], number, base),
        )
        self._scope(trial, "TRIAL", trial, integer(p, "budget_limit"))
        self._write(
            "UPDATE assignments SET trials_created=?,state='RUNNING' WHERE id=?",
            (number, assignment["id"]),
        )
        self._write("UPDATE epochs SET state='EXECUTING' WHERE id=?", (assignment["epoch_id"],))
        return {"trial_id": trial, "base_candidate_id": base}

    def _claim_trial(self, p: Object, who: Principal) -> Object:
        trial = self._one("trials", text(p, "trial_id"))
        run = self._run()
        started = self._rows(
            "SELECT id FROM attempts WHERE kind='TRIAL' AND object_id=?", (trial["id"],)
        )
        require(
            (run["status"] == "RUNNING" and run["stop_mode"] == "NONE")
            or (run["status"] == "STOPPING" and run["stop_mode"] == "DRAIN" and bool(started)),
            "STATE_CONFLICT",
            "Only an already-started Trial may be reclaimed while draining",
        )
        require(trial["state"] in {"PENDING", "RUNNING"}, "STATE_CONFLICT", "Trial not claimable")
        result = self._claim("TRIAL", text(trial, "id"), p, who)
        if "error_code" in result:
            return result
        self._write("UPDATE trials SET state='RUNNING' WHERE id=?", (trial["id"],))
        return result

    def _renew(self, p: Object, who: Principal) -> Object:
        attempt = self._valid_attempt(who)
        deadline = self.clock() + integer(p, "lease_ns", 1, 3600 * 10**9)
        require(deadline > integer(attempt, "lease_deadline"), "INVALID_INPUT", "Lease must extend")
        self._write("UPDATE attempts SET lease_deadline=? WHERE id=?", (deadline, attempt["id"]))
        return {"lease_deadline": deadline}

    def _submit(self, p: Object, who: Principal) -> Object:
        attempt = self._valid_attempt(who, "TRIAL")
        trial = self._one("trials", text(attempt, "object_id"))
        run = self._run()
        require(
            trial["state"] == "RUNNING"
            and run["status"] in {"RUNNING", "PAUSING", "STOPPING"}
            and run["stop_mode"] != "FORCE",
            "STATE_CONFLICT",
            "Candidate rejected",
        )
        candidate = f"candidate:{trial['id']}"
        job = f"evaluation:{trial['id']}"
        self._write(
            "INSERT INTO candidates VALUES (?,?,?,?,?,?)",
            (
                candidate,
                self.run_id,
                trial["base"],
                trial["id"],
                attempt["id"],
                text(p, "artifact_hash"),
            ),
        )
        self._write(
            (
                "INSERT INTO "
                "evaluations(id,run_id,candidate_id,purpose,spec_hash,request_key)"
                " VALUES (?,?,?,?,?,?)"
            ),
            (
                job,
                self.run_id,
                candidate,
                "SEARCH",
                run["evaluation_spec_hash"],
                f"search:{trial['id']}:{candidate}:{run['evaluation_spec_hash']}",
            ),
        )
        self._write(
            (
                "UPDATE trials SET state='CANDIDATE_READY',accepted_attempt=?,cand"
                "idate_id=?,evaluation_id=? WHERE id=?"
            ),
            (attempt["id"], candidate, job, trial["id"]),
        )
        self._write("UPDATE attempts SET state='SUCCEEDED' WHERE id=?", (attempt["id"],))
        return {"candidate_id": candidate, "evaluation_id": job}

    def _claim_evaluation(self, p: Object, who: Principal) -> Object:
        job = self._one("evaluations", text(p, "evaluation_id"))
        run = self._run()
        require(
            job["state"] in {"QUEUED", "RUNNING"}
            and run["stop_mode"] != "FORCE"
            and run["status"] not in TERMINAL | {"PAUSED"},
            "STATE_CONFLICT",
            "Evaluation not claimable",
        )
        require(
            job["purpose"] in {"BASELINE", "SEARCH"}, "FORBIDDEN", "Audit not implemented in M0"
        )
        if job["purpose"] == "BASELINE" and not job["started"]:
            require(run["status"] == "CREATED", "STATE_CONFLICT", "Baseline cannot start now")
        result = self._claim("EVALUATION", text(job, "id"), p, who)
        if "error_code" in result:
            return result
        self._write("UPDATE evaluations SET state='RUNNING',started=1 WHERE id=?", (job["id"],))
        self._write("UPDATE trials SET state='EVALUATING' WHERE evaluation_id=?", (job["id"],))
        return result

    def _record_evaluation(self, p: Object, who: Principal) -> Object:
        attempt = self._valid_attempt(who, "EVALUATION")
        job = self._one("evaluations", text(attempt, "object_id"))
        require(
            job["state"] == "RUNNING" and self._run()["stop_mode"] != "FORCE",
            "STATE_CONFLICT",
            "Evaluation rejected",
        )
        verdict = text(p, "verdict")
        if verdict == "INFRA_ERROR":
            exhausted = integer(attempt, "generation") >= 3
            self._write("UPDATE attempts SET state='FAILED' WHERE id=?", (attempt["id"],))
            self._write(
                "UPDATE evaluations SET state=? WHERE id=?",
                ("FAILED" if exhausted else "QUEUED", job["id"]),
            )
            if exhausted:
                self._write("UPDATE trials SET state='FAILED' WHERE evaluation_id=?", (job["id"],))
                if job["purpose"] == "BASELINE":
                    self._write(
                        "UPDATE runs SET "
                        "status='FAILED',completion_reason='BASELINE_INFRA_EXHAUSTED'"
                    )
            return {"evaluation_id": job["id"], "state": "FAILED" if exhausted else "QUEUED"}
        require(
            verdict
            in {
                "VALID_SCORED",
                "BUILD_FAIL",
                "INCORRECT",
                "CANDIDATE_TIMEOUT",
                "CANDIDATE_RESOURCE_LIMIT",
            },
            "INVALID_INPUT",
            "Unknown verdict",
        )
        score: Json = integer(p, "score_i") if verdict == "VALID_SCORED" else None
        require(
            verdict == "VALID_SCORED" or p.get("score_i") is None,
            "INVALID_INPUT",
            "Invalid candidate cannot have score",
        )
        self._write(
            "UPDATE evaluations SET state='DONE',verdict=?,score=?,result_hash=? WHERE id=?",
            (verdict, score, fingerprint(p), job["id"]),
        )
        self._write("UPDATE attempts SET state='SUCCEEDED' WHERE id=?", (attempt["id"],))
        return {"evaluation_id": job["id"], "verdict": verdict, "score_i": score}

    def _finalize(self, p: Object, who: Principal) -> Object:
        trial = self._one("trials", text(p, "trial_id"))
        job = self._one("evaluations", text(p, "evaluation_id"))
        require(
            job["id"] == trial["evaluation_id"]
            and job["candidate_id"] == trial["candidate_id"]
            and job["purpose"] == "SEARCH"
            and job["spec_hash"] == self._run()["evaluation_spec_hash"],
            "EVALUATION_MISMATCH",
            "Candidate/job/spec binding",
        )
        digest = fingerprint(
            {
                "candidate": trial["candidate_id"],
                "evaluation": job["id"],
                "result": job["result_hash"],
            }
        )
        if trial["state"] == "COMPLETED":
            require(trial["finalization_hash"] == digest, "RESULT_CONFLICT", "Finalization changed")
            return {"trial_id": trial["id"], "candidate_id": trial["candidate_id"]}
        run = self._run()
        require(run["stop_mode"] != "FORCE", "RUN_FORCE_STOPPED", self.run_id)
        require(
            trial["state"] == "EVALUATING"
            and job["state"] == "DONE"
            and run["status"] in {"RUNNING", "PAUSING", "STOPPING"},
            "STATE_CONFLICT",
            "Not finalizable",
        )
        if job["verdict"] == "VALID_SCORED":
            branch = self._one("branches", text(trial, "branch_id"))
            score = integer(job, "score")
            bps = integer(run, "bps")
            old = branch["head_score"]
            if old is None or improves(score, integer(branch, "head_score"), bps):
                self._write(
                    (
                        "UPDATE branches SET "
                        "head_candidate=?,head_evaluation=?,head_score=? WHERE id=?"
                    ),
                    (trial["candidate_id"], job["id"], score, branch["id"]),
                )
            if improves(score, integer(run, "best_score"), bps):
                self._write(
                    "UPDATE runs SET best_candidate=?,best_evaluation=?,best_score=?",
                    (trial["candidate_id"], job["id"], score),
                )
        self._write(
            "UPDATE trials SET state='COMPLETED',finalization_hash=? WHERE id=?",
            (digest, trial["id"]),
        )
        self._finish_assignment(text(trial, "assignment_id"))
        self._pause_barrier()
        return {"trial_id": trial["id"], "candidate_id": trial["candidate_id"]}

    def _finish_assignment(self, identifier: str) -> None:
        assignment = self._one("assignments", identifier)
        active = self._rows(
            (
                "SELECT id FROM trials WHERE assignment_id=? AND state NOT IN "
                "('COMPLETED','FAILED','CANCELLED')"
            ),
            (identifier,),
        )
        if not active and (
            assignment["trials_created"] == assignment["max_trials"]
            or self._run()["stop_mode"] != "NONE"
        ):
            self._write(
                "UPDATE assignments SET state='DONE',end_reason=? WHERE id=?",
                ("MAX_TRIALS" if self._run()["stop_mode"] == "NONE" else "STOPPED", identifier),
            )
        epoch_id = text(assignment, "epoch_id")
        if not self._rows(
            (
                "SELECT id FROM assignments WHERE epoch_id=? AND state NOT IN "
                "('DONE','CANCELLED','FAILED')"
            ),
            (epoch_id,),
        ):
            self._write("UPDATE epochs SET state='CLOSED' WHERE id=?", (epoch_id,))

    def _authorize_call(self, p: Object, who: Principal) -> Object:
        scope = self._one("budget_scopes", text(p, "scope_id"))
        attempt = self._valid_attempt(who, text(scope, "kind"))
        require(attempt["object_id"] == scope["owner_id"], "FORBIDDEN", "Budget scope owner")
        owner = self._one(
            "trials" if scope["kind"] == "TRIAL" else "invocations", text(scope, "owner_id")
        )
        require(
            owner["state"] == ("RUNNING" if scope["kind"] == "TRIAL" else "REQUESTING"),
            "STATE_CONFLICT",
            "Budget owner not executing",
        )
        run = self._run()
        allowed = {"RUNNING", "PAUSING", "STOPPING"} if scope["kind"] == "TRIAL" else {"RUNNING"}
        require(
            run["status"] in allowed and run["stop_mode"] != "FORCE" and run["budget_breach"] == 0,
            "STATE_CONFLICT",
            "New model call disallowed",
        )
        return scope

    def _reserve(self, p: Object, who: Principal) -> Object:
        scope = self._authorize_call(p, who)
        identifier = text(p, "call_id")
        amount = integer(p, "input_upper_bound") + integer(p, "output_cap")
        require(amount <= MAX_INT, "INVALID_INPUT", "Reservation overflow")
        request = text(p, "request_hash")
        existing = self._rows("SELECT * FROM model_calls WHERE id=?", (identifier,))
        if existing:
            require(
                existing[0]["scope_id"] == scope["id"]
                and existing[0]["request_hash"] == request
                and existing[0]["reserved"] == amount
                and existing[0]["attempt_id"] == who.attempt_id,
                "RESULT_CONFLICT",
                "call_id reused",
            )
            return {"call_id": identifier, "reserved": amount}
        run = self._run()
        if integer(run, "confirmed") + integer(run, "held") + amount > integer(run, "budget_limit"):
            self._drain("BUDGET_EXHAUSTED")
            self._fail_scope(scope, "BUDGET_EXHAUSTED")
            self._pause_barrier()
            return {"error_code": "BUDGET_EXHAUSTED", "message": self.run_id}
        if integer(scope, "confirmed") + integer(scope, "held") + amount > integer(
            scope, "limit_tokens"
        ):
            self._fail_scope(scope, "SCOPE_BUDGET_EXHAUSTED")
            return {"error_code": "SCOPE_BUDGET_EXHAUSTED", "message": scope["id"]}
        self._write(
            "INSERT INTO model_calls VALUES (?,?,?,?,?,?,?)",
            (identifier, self.run_id, scope["id"], who.attempt_id, request, amount, "RESERVED"),
        )
        self._balance(text(scope, "id"), 0, amount)
        return {"call_id": identifier, "reserved": amount}

    def _balance(self, scope: str, confirmed: int, held: int) -> None:
        self._write(
            "UPDATE budget_scopes SET confirmed=confirmed+?,held=held+? WHERE id=?",
            (confirmed, held, scope),
        )
        self._write("UPDATE runs SET confirmed=confirmed+?,held=held+?", (confirmed, held))

    def _fail_scope(self, scope: Object, reason: str) -> None:
        owner = text(scope, "owner_id")
        self._write(
            "UPDATE attempts SET state='REVOKED' WHERE object_id=? AND kind=? AND state='ACTIVE'",
            (owner, scope["kind"]),
        )
        for call in self._rows(
            "SELECT * FROM model_calls WHERE scope_id=? AND state='RESERVED'", (scope["id"],)
        ):
            self._balance(text(scope, "id"), 0, -integer(call, "reserved"))
            self._write("UPDATE model_calls SET state='RELEASED_UNSENT' WHERE id=?", (call["id"],))
        if scope["kind"] == "TRIAL":
            trial = self._one("trials", owner)
            self._write(
                "UPDATE trials SET state='FAILED' WHERE id=? AND state IN ('PENDING','RUNNING')",
                (owner,),
            )
            self._finish_assignment(text(trial, "assignment_id"))
        else:
            invocation = self._one("invocations", owner)
            self._write("UPDATE invocations SET state='FAILED' WHERE id=?", (owner,))
            budget_end = reason.endswith("BUDGET_EXHAUSTED")
            self._write(
                "UPDATE epochs SET state=? WHERE id=?",
                (
                    "CANCELLED" if budget_end else "FAILED",
                    invocation["epoch_id"],
                ),
            )
            self._write(
                "UPDATE runs SET status=?,completion_reason=?",
                (
                    "COMPLETED" if budget_end else "FAILED",
                    reason,
                ),
            )

    def _dispatch(self, p: Object, who: Principal) -> Object:
        call = self._one("model_calls", text(p, "call_id"))
        self._authorize_call({"scope_id": call["scope_id"]}, who)
        require(
            call["attempt_id"] == who.attempt_id and call["state"] == "RESERVED",
            "STATE_CONFLICT",
            "Call not reserved for this attempt",
        )
        self._write("UPDATE model_calls SET state='DISPATCH_INTENT' WHERE id=?", (call["id"],))
        return {"call_id": call["id"], "state": "DISPATCH_INTENT"}

    def _unknown(self, p: Object, who: Principal) -> Object:
        call = self._one("model_calls", text(p, "call_id"))
        require(
            call["state"] in {"DISPATCH_INTENT", "UNKNOWN"},
            "STATE_CONFLICT",
            "Unsent call cannot be unknown",
        )
        if call["state"] != "UNKNOWN":
            self._write("UPDATE model_calls SET state='UNKNOWN' WHERE id=?", (call["id"],))
        return {"call_id": call["id"], "state": "UNKNOWN"}

    def _release(self, p: Object, who: Principal) -> Object:
        call = self._one("model_calls", text(p, "call_id"))
        require(
            call["state"] in {"RESERVED", "RELEASED_UNSENT"},
            "STATE_CONFLICT",
            "Dispatch intent prevents release",
        )
        if call["state"] == "RESERVED":
            self._balance(text(call, "scope_id"), 0, -integer(call, "reserved"))
            self._write("UPDATE model_calls SET state='RELEASED_UNSENT' WHERE id=?", (call["id"],))
        return {"call_id": call["id"], "state": "RELEASED_UNSENT"}

    def _settle(self, p: Object, who: Principal) -> Object:
        call = self._one("model_calls", text(p, "call_id"))
        usage = p.get("usage")
        require(isinstance(usage, dict), "INVALID_INPUT", "usage required")
        if not isinstance(usage, dict):
            raise ProtocolError("INVALID_INPUT", "usage required")
        input_tokens = integer(usage, "input_tokens")
        output_tokens = integer(usage, "output_tokens")
        cached = integer(usage, "cached_input", 0, input_tokens)
        total = input_tokens + output_tokens
        require(total <= MAX_INT, "INVALID_INPUT", "Usage overflow")
        receipt = fingerprint(usage)
        rows = self._rows("SELECT * FROM usage_ledger WHERE call_id=?", (call["id"],))
        if rows:
            require(
                rows[0]["receipt_hash"] == receipt, "USAGE_CONFLICT", "Conflicting usage receipt"
            )
            return {"call_id": call["id"], "total_tokens": total}
        require(
            call["state"] in {"DISPATCH_INTENT", "UNKNOWN"}, "STATE_CONFLICT", "No started request"
        )
        self._write(
            "INSERT INTO usage_ledger VALUES (?,?,?,?,?,?)",
            (call["id"], receipt, input_tokens, output_tokens, cached, canonical(usage).decode()),
        )
        self._balance(text(call, "scope_id"), total, -integer(call, "reserved"))
        self._write("UPDATE model_calls SET state='SETTLED' WHERE id=?", (call["id"],))
        if total > integer(call, "reserved"):
            self._write("UPDATE runs SET budget_breach=1")
            if self._run()["status"] not in TERMINAL:
                self._drain("BUDGET_BOUND_BREACH")
        return {"call_id": call["id"], "total_tokens": total}

    def _pause(self, p: Object, who: Principal) -> Object:
        run = self._run()
        require(
            run["status"] in {"CREATED", "RUNNING", "PAUSING", "PAUSED"},
            "STATE_CONFLICT",
            "Cannot pause",
        )
        if run["status"] not in {"PAUSING", "PAUSED"}:
            phase = (
                "INITIALIZING"
                if run["best_candidate"] is None
                else "EXECUTING"
                if self._rows("SELECT id FROM trials")
                else "PLANNING"
                if self._rows("SELECT id FROM epochs WHERE state='PLANNING'")
                else "READY_TO_RUN"
            )
            self._write("UPDATE runs SET status='PAUSING',resume_phase=?", (phase,))
            self._release_reserved(advisor_only=True)
        self._pause_barrier()
        return {"status": self._run()["status"]}

    def _pause_barrier(self) -> None:
        run = self._run()
        if run["status"] not in {"PAUSING", "STOPPING"}:
            return
        active = self._rows(
            "SELECT id FROM trials WHERE state IN ('RUNNING','CANDIDATE_READY','EVALUATING')"
        )
        if run["stop_mode"] == "DRAIN":
            active += self._rows(
                "SELECT t.id FROM trials t WHERE t.state='PENDING' AND EXISTS "
                "(SELECT 1 FROM attempts a WHERE a.kind='TRIAL' AND a.object_id=t.id)"
            )
        active += self._rows(
            "SELECT id FROM evaluations WHERE state='RUNNING' OR "
            "(purpose='BASELINE' AND started=1 AND state='QUEUED')"
        )
        active += self._rows("SELECT id FROM invocations WHERE state='REQUESTING'")
        baseline = self._one("evaluations", text(run, "baseline_id"))
        if run["best_candidate"] is None and baseline["state"] == "DONE":
            return
        if not active:
            self._write(
                "UPDATE runs SET status=?",
                ("PAUSED" if run["status"] == "PAUSING" else "COMPLETED",),
            )

    def _resume(self, p: Object, who: Principal) -> Object:
        run = self._run()
        require(run["status"] == "PAUSED", "STATE_CONFLICT", "Only PAUSED Run can resume")
        status = "CREATED" if run["resume_phase"] == "INITIALIZING" else "RUNNING"
        self._write("UPDATE runs SET status=?", (status,))
        return {"status": status, "resume_phase": run["resume_phase"]}

    def _stop(self, p: Object, who: Principal) -> Object:
        if self._run()["status"] not in TERMINAL:
            self._drain("USER_STOP")
        return {"status": self._run()["status"]}

    def _release_reserved(self, advisor_only: bool = False) -> None:
        query = (
            "SELECT c.* FROM model_calls c JOIN budget_scopes s ON "
            "c.scope_id=s.id WHERE c.state='RESERVED'"
        )
        if advisor_only:
            query += " AND s.kind='ADVISOR'"
        for call in self._rows(query):
            self._balance(text(call, "scope_id"), 0, -integer(call, "reserved"))
            self._write("UPDATE model_calls SET state='RELEASED_UNSENT' WHERE id=?", (call["id"],))
        if advisor_only:
            # A claim alone is not an in-flight request. Sent calls may drain to PLAN_RECEIVED.
            for invocation in self._rows("SELECT * FROM invocations WHERE state='REQUESTING'"):
                sent = self._rows(
                    (
                        "SELECT c.id FROM model_calls c JOIN attempts a ON "
                        "c.attempt_id=a.id WHERE a.object_id=? AND c.state IN "
                        "('DISPATCH_INTENT','UNKNOWN')"
                    ),
                    (invocation["id"],),
                )
                if not sent:
                    self._write(
                        "UPDATE invocations SET state='PLANNED' WHERE id=?", (invocation["id"],)
                    )
                    self._write(
                        (
                            "UPDATE attempts SET state='REVOKED' WHERE object_id=? AND "
                            "kind='ADVISOR' AND state='ACTIVE'"
                        ),
                        (invocation["id"],),
                    )

    def _drain(self, reason: str) -> None:
        self._write(
            "UPDATE runs SET status='STOPPING',stop_mode='DRAIN',completion_reason=?", (reason,)
        )
        self._write(
            "UPDATE trials SET state='CANCELLED' WHERE state='PENDING' AND NOT EXISTS "
            "(SELECT 1 FROM attempts a WHERE a.kind='TRIAL' AND a.object_id=trials.id)"
        )
        self._write(
            "UPDATE invocations SET state='CANCELLED' WHERE state IN "
            "('PLANNED','REQUESTING','PLAN_RECEIVED')"
        )
        self._write("UPDATE attempts SET state='REVOKED' WHERE kind='ADVISOR' AND state='ACTIVE'")
        self._release_reserved(advisor_only=True)
        self._write("UPDATE epochs SET state='CANCELLED' WHERE state='PLANNING'")
        self._write(
            "UPDATE evaluations SET state='CANCELLED' WHERE purpose='BASELINE'"
            " AND state='QUEUED' AND started=0"
        )
        for assignment in self._rows(
            "SELECT * FROM assignments WHERE state IN ('READY','RUNNING')"
        ):
            self._skip_remaining(text(assignment, "id"))
            self._finish_assignment(text(assignment, "id"))
        self._pause_barrier()

    def _skip_remaining(self, identifier: str) -> None:
        assignment = self._one("assignments", identifier)
        never_started = self._rows(
            "SELECT count(*) AS amount FROM trials t WHERE t.assignment_id=? "
            "AND t.state='CANCELLED' AND NOT EXISTS (SELECT 1 FROM attempts a "
            "WHERE a.kind='TRIAL' AND a.object_id=t.id)",
            (identifier,),
        )
        skipped = (
            integer(assignment, "max_trials")
            - integer(assignment, "trials_created")
            + integer(never_started[0], "amount")
        )
        self._write("UPDATE assignments SET skipped=? WHERE id=?", (skipped, identifier))

    def _force(self, p: Object, who: Principal) -> Object:
        run = self._run()
        if run["stop_mode"] == "FORCE" or run["status"] in TERMINAL:
            return {"status": run["status"]}
        self._write("UPDATE metadata SET generation=generation+1")
        generation = int(self.connection.execute("SELECT generation FROM metadata").fetchone()[0])
        self._write(
            (
                "UPDATE runs SET status='COMPLETED',stop_mode='FORCE',completion_r"
                "eason='USER_FORCE_STOP',controller_generation=?"
            ),
            (generation,),
        )
        self._write(
            "UPDATE trials SET state='CANCELLED' WHERE state NOT IN "
            "('COMPLETED','FAILED','CANCELLED')"
        )
        self._write("UPDATE evaluations SET state='CANCELLED' WHERE state IN ('QUEUED','RUNNING')")
        self._write("UPDATE attempts SET state='REVOKED' WHERE state='ACTIVE'")
        self._write(
            "UPDATE invocations SET state='CANCELLED' WHERE state IN "
            "('PLANNED','REQUESTING','PLAN_RECEIVED')"
        )
        self._write(
            "UPDATE assignments SET state='CANCELLED',skipped=max_trials-"
            "trials_created,end_reason='STOPPED' WHERE state IN "
            "('READY','RUNNING')"
        )
        for assignment in self._rows("SELECT * FROM assignments WHERE state='CANCELLED'"):
            self._skip_remaining(text(assignment, "id"))
        self._write(
            "UPDATE epochs SET state='CANCELLED' WHERE state NOT IN ('CLOSED','CANCELLED','FAILED')"
        )
        self._release_reserved()
        self._write("UPDATE model_calls SET state='UNKNOWN' WHERE state='DISPATCH_INTENT'")
        return {"status": "COMPLETED"}

    def _recover(self, artifacts_valid: bool) -> None:
        run = self._run()
        self.connection.execute(
            "UPDATE runs SET controller_generation=?,version=version+1", (self.generation,)
        )
        self.connection.execute("UPDATE attempts SET state='REVOKED' WHERE state='ACTIVE'")
        self.connection.execute(
            "UPDATE model_calls SET state='UNKNOWN' WHERE state='DISPATCH_INTENT'"
        )
        self.changed = False
        self._release_reserved()
        if not artifacts_valid:
            self.connection.execute(
                "UPDATE runs SET status='FAILED',completion_reason='ARTIFACT_CORRUPT'"
            )
            return
        if run["status"] in TERMINAL:
            return
        self.connection.execute("UPDATE trials SET state='PENDING' WHERE state='RUNNING'")
        self.connection.execute("UPDATE evaluations SET state='QUEUED' WHERE state='RUNNING'")
        self.connection.execute("UPDATE invocations SET state='PLANNED' WHERE state='REQUESTING'")
        self._pause_barrier()


def improves(new: int, old: int, bps: int) -> bool:
    return new - old >= max(1, (abs(old) * bps + 9999) // 10000)


def outcome(result: Object) -> Object:
    """Terminal errors commit their effects and receipt, then replay as the same error."""
    code = result.get("error_code")
    if isinstance(code, str):
        raise ProtocolError(code, text(result, "message"))
    return result
