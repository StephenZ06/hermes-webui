"""state.db title sync survives, and reports, hermes-agent API drift.

The WebUI runs hermes-agent in-process out of a checkout that the update path
force-resets, so the agent's API can move underneath this repo between one
restart and the next. It did: `set_auto_title_if_empty` was removed in favour
of `set_auto_title(session_id, title, *, source=...)`, which expresses the same
"only fill an empty title" rule through title provenance instead of a dedicated
method.

`sync_session_title` called the removed method inside a bare `except
Exception:` that logged at debug, so the resulting AttributeError vanished. The
session row was still created by `ensure_session`, so nothing looked broken --
the titles simply stopped arriving, and `hermes sessions list` went blank for
every WebUI session, which is the exact regression #6892 had fixed.

Two things are pinned here. That the call site uses the provenance API with an
llm source -- llm ranks below user (derived 0, llm 1, user 2) and a stored NULL
source ranks as user, so an llm write cannot clobber a manual rename from the
CLI, the Gateway or the TUI, nor a pre-provenance row. And that a method going
missing is logged loudly enough to notice, because a silent debug line is what
turned a one-line breakage into an invisible one.
"""
import logging
import os
import pathlib
import sys

import pytest


@pytest.fixture
def hermes_state():
    """The agent's state module, imported order-independently.

    conftest snapshots sys.path before `api.state_sync` appends the agent
    checkout to it, and an autouse guard resets sys.path to that snapshot after
    every test. So the first test in a file loses the agent dir for all the
    ones after it, and a plain importorskip in the second test skips it — the
    sibling #6964 file only escapes this because its first test happens to pull
    hermes_state into sys.modules, where the rest then find it cached. Re-add
    the dir explicitly rather than depending on which test ran first.
    """
    from api import state_sync  # noqa: F401 — for its sys.path side effect

    agent = os.environ.get("HERMES_WEBUI_AGENT_DIR") or str(
        pathlib.Path.home() / ".hermes" / "hermes-agent"
    )
    if os.path.isdir(agent) and agent not in sys.path:
        sys.path.insert(0, agent)
    return pytest.importorskip("hermes_state")


class _DriftingDB:
    """A SessionDB whose title API has moved on, as the real one's did."""

    def __init__(self):
        self.closed = False

    def ensure_session(self, session_id, source=None):
        return True

    def __getattr__(self, name):
        raise AttributeError(f"'_DriftingDB' object has no attribute '{name}'")

    def close(self):
        self.closed = True


def test_missing_agent_method_is_reported_not_swallowed(monkeypatch, caplog):
    from api import state_sync

    db = _DriftingDB()
    monkeypatch.setattr(state_sync, "_get_state_db", lambda profile=None: db)

    with caplog.at_level(logging.DEBUG):
        state_sync.sync_session_title("sess-x", "Some Title", profile="default")

    assert db.closed, "the db handle must still be closed on the drift path"
    drift = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert drift, (
        "an agent method going missing must be logged at WARNING or above — a "
        "debug line is what let the title sync break silently. Records seen: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
    assert any("title" in r.getMessage().lower() for r in drift)


@pytest.mark.requires_agent_modules
def test_sync_uses_the_provenance_api_with_an_llm_source(tmp_path, monkeypatch, hermes_state):
    from api import state_sync

    db = hermes_state.SessionDB(db_path=tmp_path / "state.db")
    try:
        monkeypatch.setattr(
            state_sync,
            "_get_state_db",
            lambda profile=None: hermes_state.SessionDB(db_path=tmp_path / "state.db"),
        )
        state_sync.sync_session_title("sess-a", "Alpha Title", profile="default")

        assert db.get_session_title("sess-a") == "Alpha Title"
        assert db.get_session_title_source("sess-a") == db.TITLE_SOURCE_LLM, (
            "the auto-title must be written with llm provenance so a later "
            "manual rename outranks it"
        )
    finally:
        db.close()


@pytest.mark.requires_agent_modules
def test_a_user_rename_outranks_a_later_auto_title(tmp_path, monkeypatch):
    # The invariant the removed method used to give us for free.
    # api.state_sync is what puts the agent checkout on sys.path, so it has to
    # be imported before hermes_state can be probed for.
    from api import state_sync

    hermes_state = pytest.importorskip("hermes_state")

    db = hermes_state.SessionDB(db_path=tmp_path / "state.db")
    try:
        monkeypatch.setattr(
            state_sync,
            "_get_state_db",
            lambda profile=None: hermes_state.SessionDB(db_path=tmp_path / "state.db"),
        )
        db.ensure_session(session_id="sess-r", source="webui")
        db.set_session_title("sess-r", "Renamed By Hand")

        state_sync.sync_session_title("sess-r", "Generated Title", profile="default")

        assert db.get_session_title("sess-r") == "Renamed By Hand"
    finally:
        db.close()
