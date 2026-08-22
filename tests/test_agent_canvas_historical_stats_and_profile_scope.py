"""Regression tests for two Agent Canvas bugs:

1. Subagent detail (model, tokens, api calls, cost) shown while live tracking
   is active disappeared down to a bare status dot after a page reload or
   once the live view aged out, because list_parents_with_subagent_children()
   only ever SELECTed id/source/parent_session_id/title/started_at/ended_at
   from state.db — the historical reconstruction in agent-canvas.js then had
   nothing to work with and hardcoded model/tokens/cost to empty/zero.

2. In the two-container gateway-bridged deployment (HERMES_WEBUI_CHAT_BACKEND
   =gateway), Agent Canvas showed no delegated chats at all on any non-default
   profile, but showed every profile's chats mixed together on the default
   profile. resolve_agent_state_db_path() was profile-scoping the state.db
   lookup, but the single shared gateway process never writes subagent rows
   to a profile-scoped state.db for its API-server-origin sessions — they
   always land in the base state.db regardless of which profile the WebUI
   happened to have selected.

   Fixed by resolve_agent_state_db_paths() (plural) returning BOTH the base
   db and a genuinely-populated profile-scoped one (from a native `hermes`
   CLI session run with --profile <name>, a real separate origin) when
   gateway-bridged, so a route can union results from both without losing
   real CLI-origin delegation history that lives only in the profile-scoped
   file.
"""
import sqlite3

import pytest

from api.agent_sessions import list_parents_with_subagent_children, resolve_agent_state_db_paths


def _make_state_db(path, *, with_stat_columns=True):
    conn = sqlite3.Connection(str(path))
    stat_cols = (
        """
        , model TEXT
        , input_tokens INTEGER
        , output_tokens INTEGER
        , reasoning_tokens INTEGER
        , api_call_count INTEGER
        , tool_call_count INTEGER
        , estimated_cost_usd REAL
        , actual_cost_usd REAL
        """
        if with_stat_columns
        else ""
    )
    conn.executescript(
        f"""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            parent_session_id TEXT,
            started_at REAL,
            ended_at REAL
            {stat_cols}
        );
        """
    )
    conn.commit()
    conn.close()


class TestHistoricalStatsSurfaced:
    """list_parents_with_subagent_children must carry model/token/cost stats."""

    def test_child_rows_include_model_tokens_and_cost(self, tmp_path):
        db_path = tmp_path / "state.db"
        _make_state_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO sessions (id, source, title, parent_session_id, started_at, "
            "ended_at, model, input_tokens, output_tokens, reasoning_tokens, "
            "api_call_count, tool_call_count, estimated_cost_usd, actual_cost_usd) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "child-1", "subagent", "Subagent: reply ALPHA", "parent-1",
                100.0, 105.0, "gpt-5.5", 3229, 42, 18, 1, 0, None, 0.0012,
            ),
        )
        conn.commit()
        conn.close()

        parents = list_parents_with_subagent_children(db_path)
        assert len(parents) == 1
        [child] = parents[0]["children"]
        assert child["model"] == "gpt-5.5"
        assert child["input_tokens"] == 3229
        assert child["output_tokens"] == 42
        assert child["reasoning_tokens"] == 18
        assert child["api_call_count"] == 1
        assert child["cost_usd"] == pytest.approx(0.0012)

    def test_actual_cost_preferred_over_estimated(self, tmp_path):
        db_path = tmp_path / "state.db"
        _make_state_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO sessions (id, source, title, parent_session_id, started_at, "
            "ended_at, estimated_cost_usd, actual_cost_usd) VALUES (?,?,?,?,?,?,?,?)",
            ("child-1", "subagent", "t", "parent-1", 1.0, 2.0, 0.05, 0.03),
        )
        conn.commit()
        conn.close()

        [entry] = list_parents_with_subagent_children(db_path)
        assert entry["children"][0]["cost_usd"] == pytest.approx(0.03)

    def test_degrades_gracefully_on_schema_missing_stat_columns(self, tmp_path):
        """An older state.db without the newer stat columns must still work,
        not raise/return [] just because the expanded SELECT can't ask for
        columns that don't exist."""
        db_path = tmp_path / "state.db"
        _make_state_db(db_path, with_stat_columns=False)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO sessions (id, source, title, parent_session_id, started_at, ended_at) "
            "VALUES (?,?,?,?,?,?)",
            ("child-1", "subagent", "t", "parent-1", 1.0, 2.0),
        )
        conn.commit()
        conn.close()

        parents = list_parents_with_subagent_children(db_path)
        assert len(parents) == 1
        child = parents[0]["children"][0]
        assert child["session_id"] == "child-1"
        assert child["model"] is None
        assert child["cost_usd"] is None


class TestGatewayBridgedProfileScope:
    """resolve_agent_state_db_paths must return BOTH the base db and a real
    profile-scoped one when gateway-bridged, and ONLY the profile-scoped-or-
    base one (never unioned with base) when not.
    """

    def test_unions_base_and_profile_db_when_gateway_chat_enabled(self, monkeypatch, tmp_path):
        base = tmp_path / "hermes"
        base.mkdir()
        (base / "state.db").write_bytes(b"")
        profile_dir = base / "profiles" / "coding-opencode"
        profile_dir.mkdir(parents=True)
        (profile_dir / "state.db").write_bytes(b"")

        import api.config as config_mod
        monkeypatch.setattr(config_mod, "STATE_DIR", base / "webui")

        import api.gateway_chat as gateway_chat_mod
        monkeypatch.setattr(gateway_chat_mod, "webui_gateway_chat_enabled", lambda *a, **k: True)

        import api.profiles as profiles_mod
        monkeypatch.setattr(profiles_mod, "get_active_profile_name", lambda: "coding-opencode")
        monkeypatch.setattr(profiles_mod, "_is_root_profile", lambda name: False)

        resolved = resolve_agent_state_db_paths()
        assert set(resolved) == {base / "state.db", profile_dir / "state.db"}

    def test_only_base_when_gateway_chat_enabled_and_no_profile_db_exists(self, monkeypatch, tmp_path):
        """No native CLI session ever ran under this profile -> no
        profile-scoped state.db was ever created -> just the base db,
        not a nonexistent path."""
        base = tmp_path / "hermes"
        base.mkdir()
        (base / "state.db").write_bytes(b"")

        import api.config as config_mod
        monkeypatch.setattr(config_mod, "STATE_DIR", base / "webui")

        import api.gateway_chat as gateway_chat_mod
        monkeypatch.setattr(gateway_chat_mod, "webui_gateway_chat_enabled", lambda *a, **k: True)

        import api.profiles as profiles_mod
        monkeypatch.setattr(profiles_mod, "get_active_profile_name", lambda: "quick-task")
        monkeypatch.setattr(profiles_mod, "_is_root_profile", lambda name: False)

        resolved = resolve_agent_state_db_paths()
        assert resolved == [base / "state.db"]

    def test_profile_scoped_only_when_gateway_chat_disabled(self, monkeypatch, tmp_path):
        """Single-container deployment: profile-scoping stays exclusive
        there (never unioned with base) since WebUI runs its own in-process
        agent per profile and HERMES_HOME switches wholesale per profile —
        base and profile-scoped are genuinely unrelated homes."""
        base = tmp_path / "hermes"
        base.mkdir()
        (base / "state.db").write_bytes(b"")
        profile_dir = base / "profiles" / "coding-opencode"
        profile_dir.mkdir(parents=True)
        (profile_dir / "state.db").write_bytes(b"")

        import api.config as config_mod
        monkeypatch.setattr(config_mod, "STATE_DIR", base / "webui")

        import api.gateway_chat as gateway_chat_mod
        monkeypatch.setattr(gateway_chat_mod, "webui_gateway_chat_enabled", lambda *a, **k: False)

        import api.profiles as profiles_mod
        monkeypatch.setattr(profiles_mod, "get_active_profile_name", lambda: "coding-opencode")
        monkeypatch.setattr(profiles_mod, "_is_root_profile", lambda name: False)

        resolved = resolve_agent_state_db_paths()
        assert resolved == [profile_dir / "state.db"]


class TestListParentsUnionsMultipleDatabases:
    def test_concatenates_and_sorts_results_from_multiple_dbs(self, tmp_path):
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _make_state_db(db_a)
        _make_state_db(db_b)

        conn_a = sqlite3.connect(str(db_a))
        conn_a.execute(
            "INSERT INTO sessions (id, source, title, parent_session_id, started_at, ended_at) "
            "VALUES (?,?,?,?,?,?)",
            ("child-a", "subagent", "t", "parent-a", 100.0, 105.0),
        )
        conn_a.commit()
        conn_a.close()

        conn_b = sqlite3.connect(str(db_b))
        conn_b.execute(
            "INSERT INTO sessions (id, source, title, parent_session_id, started_at, ended_at) "
            "VALUES (?,?,?,?,?,?)",
            ("child-b", "cli", "t", "parent-b", 200.0, 205.0),
        )
        conn_b.commit()
        conn_b.close()

        parents = list_parents_with_subagent_children([db_a, db_b])
        pids = {p["parent_session_id"] for p in parents}
        assert pids == {"parent-a", "parent-b"}
        # Most recently active first, across both databases.
        assert parents[0]["parent_session_id"] == "parent-b"
