"""Run the development smoke workflow and export a deterministic JSON result."""

import json
from dataclasses import asdict
from pathlib import Path

from mini_sla_harness.fake import CASES, DemoRecord, FakeProvider
from mini_sla_harness.store import load_records, save_records


def run_demo(output_dir: Path) -> dict[str, object]:
    provider = FakeProvider()
    expected = tuple(
        sorted(
            (
                DemoRecord(case_id, prompt, provider.complete(prompt))
                for case_id, prompt, _ in CASES
            ),
            key=lambda record: record.case_id,
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "demo.sqlite3"
    save_records(database, expected)
    persisted = load_records(database)
    if persisted != expected:
        raise ValueError("SQLite round-trip did not match the expected fake records")
    report: dict[str, object] = {
        "schema_version": 1,
        "scope": "development-smoke",
        "status": "ok",
        "provider": "deterministic-fake-v1",
        "case_count": len(persisted),
        "sqlite_round_trip": "passed",
        "research_effect": "not_evaluated",
        "records": [asdict(record) for record in persisted],
    }
    (output_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report
