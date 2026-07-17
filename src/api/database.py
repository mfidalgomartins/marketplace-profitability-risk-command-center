from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class CaseDatabase:
    def __init__(self, database_path: Path, migrations_dir: Path) -> None:
        self.database_path = database_path
        self.migrations_dir = migrations_dir

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def migrate(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_name TEXT PRIMARY KEY,
                    migration_sha256 TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                str(row[0]): str(row[1])
                for row in connection.execute(
                    "SELECT migration_name, migration_sha256 FROM schema_migrations"
                ).fetchall()
            }
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                sql = migration.read_text(encoding="utf-8")
                migration_sha256 = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                if migration.name in applied:
                    if applied[migration.name] != migration_sha256:
                        raise ValueError(f"Applied migration was modified: {migration.name}")
                    continue
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (migration_name, migration_sha256, applied_at) "
                    "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                    (migration.name, migration_sha256),
                )
            connection.commit()

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
