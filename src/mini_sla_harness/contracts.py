"""Validated, deterministic inputs for the offline protocol kernel."""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type Object = dict[str, Json]
MAX_INT = 2**63 - 1


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ProtocolError(code, message)


def canonical(value: Json) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


def fingerprint(value: Json) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_object(data: str | bytes) -> Object:
    def pairs(items: list[tuple[str, Json]]) -> Object:
        result: Object = {}
        for key, value in items:
            require(key not in result, "INVALID_INPUT", f"Duplicate field: {key}")
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise ProtocolError("INVALID_INPUT", f"Non-finite JSON: {value}")

    value: Json = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    require(isinstance(value, dict), "INVALID_INPUT", "Expected a JSON object")
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_INPUT", "Expected a JSON object")
    return value


def text(value: Object, key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ProtocolError("INVALID_INPUT", f"{key}: expected a nonempty string")
    return result


def integer(value: Object, key: str, minimum: int = 0, maximum: int = MAX_INT) -> int:
    result = value.get(key)
    if type(result) is not int or not minimum <= result <= maximum:
        raise ProtocolError("INVALID_INPUT", f"{key}: expected integer {minimum}..{maximum}")
    return result


def relative_path(name: str) -> str:
    parts = PurePosixPath(name).parts
    require(
        bool(parts) and "/".join(parts) == name and all(part not in {".", ".."} for part in parts),
        "ARTIFACT_INVALID",
        f"Not a canonical relative path: {name}",
    )
    for part in parts:
        require(
            not re.search(r'[\\/:<>"|?*\x00-\x1f]', part)
            and not part.endswith((".", " "))
            and not re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part),
            "ARTIFACT_INVALID",
            f"Unsupported Windows/Linux path: {name}",
        )
    return name


@dataclass(frozen=True)
class TaskSpec:
    value: Object

    @classmethod
    def parse(cls, value: Object) -> TaskSpec:
        require(integer(value, "schema_version") == 1, "INVALID_TASK", "Unsupported schema")
        text(value, "task_id")
        files = value.get("editable_files")
        require(isinstance(files, list) and bool(files), "INVALID_TASK", "editable_files required")
        if not isinstance(files, list):
            raise ProtocolError("INVALID_TASK", "editable_files required")
        names: list[str] = []
        for item in files:
            require(isinstance(item, str), "INVALID_TASK", "editable_files must contain strings")
            if isinstance(item, str):
                names.append(relative_path(item))
        require(
            len({name.casefold() for name in names}) == len(names),
            "INVALID_TASK",
            "editable_files collide on Windows",
        )
        require(
            text(value, "metric") == "end_to_end_records_per_second",
            "INVALID_TASK",
            "Unsupported metric",
        )
        integer(value, "min_improvement_bps", 0, 10000)
        require(
            text(value, "evaluation_spec_hash") != text(value, "audit_spec_hash"),
            "INVALID_TASK",
            "Search and audit identities must differ",
        )
        # Detach mutable caller data; no timestamp or machine path enters the fingerprint.
        return cls(parse_object(canonical(value)))

    @classmethod
    def load(cls, path: Path) -> TaskSpec:
        return cls.parse(parse_object(path.read_bytes()))

    @property
    def digest(self) -> str:
        return fingerprint(self.value)

    @property
    def editable_files(self) -> tuple[str, ...]:
        files = self.value.get("editable_files")
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise ProtocolError("INVALID_TASK", "editable_files changed after validation")
        return tuple(str(item) for item in files)


class Role(StrEnum):
    CONTROLLER = "CONTROLLER"
    WORKER = "WORKER"
    EVALUATOR = "EVALUATOR"
    GATEWAY = "GATEWAY"


def assignment_spec(value: Object, task: TaskSpec) -> Object:
    for field in ("assignment_id", "branch_id", "direction_key", "hypothesis", "objective"):
        text(value, field)
    require(text(value, "mode") in {"NEW", "CONTINUE"}, "PLAN_INVALID", "Invalid branch mode")
    integer(value, "worker_slot", 0, 2)
    integer(value, "max_trials", 1, 3)
    files = value.get("editable_files")
    require(isinstance(files, list) and bool(files), "PLAN_INVALID", "editable_files required")
    if not isinstance(files, list):
        raise ProtocolError("PLAN_INVALID", "editable_files required")
    require(
        all(isinstance(name, str) and name in task.editable_files for name in files)
        and len({str(name) for name in files}) == len(files),
        "PLAN_INVALID",
        "Assignment exceeds task edit scope",
    )
    return parse_object(canonical(value))


@dataclass(frozen=True)
class Principal:
    role: Role
    controller_generation: int
    attempt_id: str = ""
    owner: str = ""


@dataclass(frozen=True)
class Command:
    command_id: str
    type: str
    run_id: str
    payload: Object

    @property
    def digest(self) -> str:
        return fingerprint(
            {"schema_version": 1, "type": self.type, "run_id": self.run_id, "payload": self.payload}
        )
