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


MIGRATIONS: tuple[tuple[int, object], ...] = ((1, _migration_1),)


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

