"""Shared secrets file layered under every profile's .env."""

from __future__ import annotations

import stat

import pytest

from api import profiles, shared_env


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    (tmp_path / "profiles" / "work").mkdir(parents=True)
    return tmp_path


def test_profile_sees_shared_values_and_its_own_override(base):
    (base / "shared").mkdir()
    (base / "shared" / "secrets.env").write_text("GROQ_API_KEY=shared-groq\nBRAVE_SEARCH_API_KEY=shared-brave\n")
    (base / "profiles" / "work" / ".env").write_text('GROQ_API_KEY="work-groq"\nBRAVE_SEARCH_API_KEY=\n')
    env = shared_env.load_layered_env(base / "profiles" / "work")
    assert env["GROQ_API_KEY"] == "work-groq", "a profile value overrides the shared one"
    assert env["BRAVE_SEARCH_API_KEY"] == "shared-brave", "an empty profile line does not blank a shared key"
    root = shared_env.load_layered_env(base)
    assert root["GROQ_API_KEY"] == "shared-groq"


def test_new_keys_are_written_to_the_shared_file_with_private_permissions(base):
    (base / "shared").mkdir(mode=0o700)
    (base / "shared" / "secrets.env").write_text("")
    shared_env.write_env_values(base / "profiles" / "work", {"JOB_OS_GMAIL_ADDRESS": "me@gmail.com"})
    shared = base / "shared" / "secrets.env"
    assert shared_env.parse_env_file(shared)["JOB_OS_GMAIL_ADDRESS"] == "me@gmail.com"
    assert not (base / "profiles" / "work" / ".env").exists() or "JOB_OS" not in (base / "profiles" / "work" / ".env").read_text()
    assert stat.S_IMODE(shared.stat().st_mode) == 0o600
    assert stat.S_IMODE(shared.parent.stat().st_mode) == 0o700
    # Every profile now sees it.
    assert shared_env.load_layered_env(base)["JOB_OS_GMAIL_ADDRESS"] == "me@gmail.com"


def test_a_profile_override_is_updated_in_place(base):
    (base / "profiles" / "work" / ".env").write_text("GROQ_API_KEY=work-groq\n")
    shared_env.write_env_values(base / "profiles" / "work", {"GROQ_API_KEY": "work-groq-2"})
    assert shared_env.parse_env_file(base / "profiles" / "work" / ".env")["GROQ_API_KEY"] == "work-groq-2"
    assert "GROQ_API_KEY" not in shared_env.parse_env_file(base / "shared" / "secrets.env")


def test_removal_clears_both_layers(base):
    (base / "shared").mkdir()
    (base / "shared" / "secrets.env").write_text("GROQ_API_KEY=shared\nKEEP=1\n")
    (base / "profiles" / "work" / ".env").write_text("GROQ_API_KEY=work\n")
    shared_env.write_env_values(base / "profiles" / "work", {"GROQ_API_KEY": None})
    assert "GROQ_API_KEY" not in shared_env.load_layered_env(base / "profiles" / "work")
    assert shared_env.load_layered_env(base)["KEEP"] == "1"


def test_without_a_shared_file_nothing_changes(base):
    shared_env.write_env_values(base / "profiles" / "work", {"GROQ_API_KEY": "x"})
    assert shared_env.parse_env_file(base / "profiles" / "work" / ".env")["GROQ_API_KEY"] == "x"
    assert not (base / "shared").exists(), "the layer is never created implicitly"


def test_isolated_profiles_never_see_or_write_shared_secrets(base, monkeypatch):
    (base / "shared").mkdir()
    (base / "shared" / "secrets.env").write_text("GROQ_API_KEY=operator\n")
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: True)
    assert "GROQ_API_KEY" not in shared_env.load_layered_env(base / "profiles" / "work")
    shared_env.write_env_values(base / "profiles" / "work", {"NEW_KEY": "x"})
    assert "NEW_KEY" in shared_env.parse_env_file(base / "profiles" / "work" / ".env")
    assert "NEW_KEY" not in shared_env.parse_env_file(base / "shared" / "secrets.env")
