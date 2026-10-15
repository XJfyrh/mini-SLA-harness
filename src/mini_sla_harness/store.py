"""Demo-only SQLite persistence. This is not the future authoritative StateStore."""

import sqlite3
from contextlib import closing
from pathlib import Path

from mini_sla_harness.fake import DemoRecord


def save_records(path: Path, records: tuple[DemoRecord, ...]) -> None:
    """Keep identical replays and reject conflicting fixture rows without replacing them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS demo_records ("
                "case_id TEXT PRIMARY KEY, prompt TEXT NOT NULL, "
                "response TEXT NOT NULL, provider TEXT NOT NULL)"
            )
            for record in records:
                values = (record.case_id, record.prompt, record.response, record.provider)
                connection.execute(
                    "INSERT INTO demo_records VALUES (?, ?, ?, ?) ON CONFLICT(case_id) DO NOTHING",
                    values,
                )
                row = connection.execute(
                    "SELECT case_id, prompt, response, provider "
                    "FROM demo_records WHERE case_id = ?",
                    (record.case_id,),
                ).fetchone()
                if row != values:
                    raise ValueError(f"Conflicting demo record: {record.case_id}")


def load_records(path: Path) -> tuple[DemoRecord, ...]:
    """Read persisted records from a new connection in stable order."""
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT case_id, prompt, response, provider FROM demo_records ORDER BY case_id"
        ).fetchall()
    return tuple(DemoRecord(*row) for row in rows)
