"""Versioned schema migrations for the Job OS SQLite store."""

from __future__ import annotations

import sqlite3
import time


def _migration_1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            canonical_url TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'manual',
            source_id TEXT,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'saved',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_source_id_unique
        ON jobs (source, source_id)
        WHERE source_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS job_events_job_created_index
        ON job_events (job_id, created_at, id)
        """
    )


def _migration_2(connection: sqlite3.Connection) -> None:
    connection.execute("ALTER TABLE jobs ADD COLUMN revision INTEGER NOT NULL DEFAULT 0")
    connection.execute("ALTER TABLE jobs ADD COLUMN idempotency_key TEXT")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency_key_unique
        ON jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )


def _migration_3(connection: sqlite3.Connection) -> None:
    """Scout: posting details on jobs, saved searches and discovery runs."""
    for column in (
        "description TEXT NOT NULL DEFAULT ''",
        "salary_text TEXT NOT NULL DEFAULT ''",
        "employment_type TEXT NOT NULL DEFAULT ''",
        "workplace TEXT NOT NULL DEFAULT ''",
        "posted_at TEXT NOT NULL DEFAULT ''",
        "search_id TEXT",
        "run_id TEXT",
    ):
        connection.execute(f"ALTER TABLE jobs ADD COLUMN {column}")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            keywords TEXT NOT NULL,
            locations TEXT NOT NULL DEFAULT '',
            sites TEXT NOT NULL DEFAULT '',
            remote_only INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            revision INTEGER NOT NULL DEFAULT 0,
            last_run_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id TEXT PRIMARY KEY,
            search_id TEXT NOT NULL,
            status TEXT NOT NULL,
            stage_detail TEXT NOT NULL DEFAULT '',
            trigger TEXT NOT NULL DEFAULT 'manual',
            revision INTEGER NOT NULL DEFAULT 0,
            counts_json TEXT NOT NULL DEFAULT '{}',
            errors_json TEXT NOT NULL DEFAULT '[]',
            new_job_ids_json TEXT NOT NULL DEFAULT '[]',
            idempotency_key TEXT,
            owner_pid INTEGER,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            started_at INTEGER,
            finished_at INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS discovery_runs_idempotency_unique
        ON discovery_runs (idempotency_key) WHERE idempotency_key IS NOT NULL
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS discovery_runs_search_created ON discovery_runs (search_id, created_at)"
    )


MIGRATIONS = ((1, _migration_1), (2, _migration_2), (3, _migration_3))


def migrate_job_os(connection: sqlite3.Connection) -> None:
    """Apply every pending Job OS schema migration in one transaction."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            )
            """
        )
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_meta").fetchall()
        }
        for version, migration in MIGRATIONS:
            if version in applied:
                continue
            migration(connection)
            connection.execute(
                "INSERT INTO schema_meta (version, applied_at) VALUES (?, ?)",
                (version, int(time.time())),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
