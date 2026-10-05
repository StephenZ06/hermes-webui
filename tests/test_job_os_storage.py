"""Behavioral coverage for the Job OS SQLite store: global across profiles,
per profile only in isolated-profile deployments."""

from pathlib import Path

from api import profiles
from api.job_os import db as job_db
from api.job_os.paths import job_os_db_path


def _activate_profile(monkeypatch, homes: dict[str, Path], active: dict[str, str], *, isolated: bool = True) -> None:
    """Point the profile boundary at a caller-selected profile home."""
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: active["name"])
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: homes[active["name"]])
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: homes["base"])
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: isolated)


def test_job_os_database_is_global_across_profiles(tmp_path, monkeypatch):
    """One store for the person using Hermes, whichever profile is active."""
    homes = {"base": tmp_path, "research": tmp_path / "profiles" / "research", "applications": tmp_path / "profiles" / "applications"}
    active = {"name": "research"}
    _activate_profile(monkeypatch, homes, active, isolated=False)
    conn = job_db.connect_job_os()
    conn.execute("INSERT INTO jobs (id, canonical_url, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("job-1", "https://example.test/one", "Role", "saved", 1, 1))
    conn.commit()
    conn.close()
    active["name"] = "applications"
    other = job_db.connect_job_os()
    try:
        assert [row[0] for row in other.execute("SELECT id FROM jobs").fetchall()] == ["job-1"]
    finally:
        other.close()
    assert job_os_db_path() == tmp_path / "webui_state" / "job_os" / "job_os.db"


def test_job_os_database_is_isolated_by_active_profile(tmp_path, monkeypatch):
    """In isolated-profile deployments a job stored for one profile cannot
    appear in another profile's store."""
    homes = {"base": tmp_path / "base", "research": tmp_path / "research", "applications": tmp_path / "applications"}
    active = {"name": "research"}
    _activate_profile(monkeypatch, homes, active)

    research_path = job_os_db_path()
    research = job_db.connect_job_os()
    research.execute(
        "INSERT INTO jobs (id, canonical_url, title, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("job-research", "https://example.test/research", "Research role", "saved", 1, 1),
    )
    research.commit()
    research.close()

    active["name"] = "applications"
    applications_path = job_os_db_path()
    applications = job_db.connect_job_os()
    try:
        assert applications.execute("SELECT id FROM jobs").fetchall() == []
    finally:
        applications.close()

    assert research_path == homes["research"] / "webui_state" / "job_os" / "job_os.db"
    assert applications_path == homes["applications"] / "webui_state" / "job_os" / "job_os.db"
    assert research_path != applications_path


def test_job_os_migrations_are_idempotent(tmp_path, monkeypatch):
    """Repeated bootstrap keeps one stable schema version and enables foreign keys."""
    active = {"name": "default"}
    _activate_profile(monkeypatch, {"base": tmp_path / "default", "default": tmp_path / "default"}, active)

    first = job_db.connect_job_os()
    try:
        first_version = first.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
        assert first.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        first.close()

    second = job_db.connect_job_os()
    try:
        second_version = second.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
        assert second_version == first_version
        assert second.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0] == second_version
    finally:
        second.close()


def test_job_os_capability_fails_closed_when_migration_fails(tmp_path, monkeypatch):
    """The UI capability response hides Job OS when its store cannot migrate."""
    active = {"name": "default"}
    _activate_profile(monkeypatch, {"base": tmp_path / "default", "default": tmp_path / "default"}, active)

    def broken_migration(_connection):
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(job_db, "migrate_job_os", broken_migration)

    capability = job_db.job_os_capability()

    assert capability["available"] is False
    assert capability["reason"] == "Job OS storage is unavailable"
