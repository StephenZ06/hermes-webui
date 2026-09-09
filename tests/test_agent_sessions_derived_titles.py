"""Subagent rows recover their goal from their first user message.

hermes-agent creates subagent sessions without a title — every one of them
stores `title = NULL` — so a delegation tree rebuilt from state.db labelled
every desk "Subagent" and every conversation "Untitled chat". Reported from
the office, where a run showed real goals while it was live and reverted to
"Subagent" once it was being read back from storage.

The goal was never lost: it is the child's *first user message*, which is
exactly the text delegate_task handed it. Recovering it there repairs runs
that finished long before this code existed, not only new ones.
"""
import json
import sqlite3

import pytest

from api.agent_sessions import list_parents_with_subagent_children


def _make_state_db(path, sessions, messages):
    conn = sqlite3.Connection(str(path))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            parent_session_id TEXT,
            started_at REAL,
            ended_at REAL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO sessions(id, source, title, parent_session_id, started_at, ended_at)"
        " VALUES (?,?,?,?,?,?)", sessions)
    conn.executemany(
        "INSERT INTO messages(session_id, role, content) VALUES (?,?,?)", messages)
    conn.commit()
    conn.close()
    return path


def _children(path):
    parents = list_parents_with_subagent_children(path)
    assert parents, "expected the parent chat to be listed"
    return {c["session_id"]: c["title"] for c in parents[0]["children"]}


def test_a_titleless_subagent_is_named_by_its_first_user_message(tmp_path):
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[
            ("chat", "webui", "Untitled chat", None, 100.0, None),
            ("kid", "subagent", None, "chat", 101.0, 120.0),
        ],
        messages=[
            ("kid", "user", "Read pyproject.toml and list the dependencies."),
            ("kid", "assistant", "Here they are."),
        ],
    )
    assert _children(db)["kid"] == "Read pyproject.toml and list the dependencies."


def test_the_first_user_message_wins_not_a_later_one(tmp_path):
    # A steered subagent gets further user messages; the goal is the first.
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 120.0)],
        messages=[
            ("kid", "user", "the original goal"),
            ("kid", "assistant", "working"),
            ("kid", "user", "actually also do this"),
        ],
    )
    assert _children(db)["kid"] == "the original goal"


def test_a_real_title_is_never_overwritten(tmp_path):
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", "A proper title", "chat", 101.0, 120.0)],
        messages=[("kid", "user", "the first message")],
    )
    assert _children(db)["kid"] == "A proper title"


def test_a_subagent_with_no_messages_keeps_no_title(tmp_path):
    # Nothing to recover is not the same as inventing something.
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 120.0)],
        messages=[("kid", "assistant", "no user turn at all")],
    )
    assert not _children(db)["kid"]


def test_multimodal_content_yields_its_text(tmp_path):
    # Message bodies are sometimes stored as JSON parts rather than a string.
    body = json.dumps([
        {"type": "text", "text": "Count the Python files"},
        {"type": "image", "source": {"data": "..."}},
    ])
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 120.0)],
        messages=[("kid", "user", body)],
    )
    assert _children(db)["kid"] == "Count the Python files"


def test_a_long_goal_is_truncated_rather_than_carried_whole(tmp_path):
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 120.0)],
        messages=[("kid", "user", "x" * 500)],
    )
    title = _children(db)["kid"]
    assert len(title) == 160 and title.endswith("…")


def test_whitespace_is_collapsed(tmp_path):
    # A multi-line prompt would otherwise render with its newlines intact.
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 120.0)],
        messages=[("kid", "user", "read the file\n\n  and summarise it")],
    )
    assert _children(db)["kid"] == "read the file and summarise it"


def test_every_child_of_a_fan_out_is_named(tmp_path):
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None)]
        + [(f"kid{i}", "subagent", None, "chat", 101.0 + i, 120.0) for i in range(6)],
        messages=[(f"kid{i}", "user", f"task number {i}") for i in range(6)],
    )
    titles = _children(db)
    assert titles == {f"kid{i}": f"task number {i}" for i in range(6)}


def test_a_nested_grandchild_is_named_too(tmp_path):
    db = _make_state_db(
        tmp_path / "state.db",
        sessions=[("chat", "webui", None, None, 100.0, None),
                  ("kid", "subagent", None, "chat", 101.0, 130.0),
                  ("grandkid", "subagent", None, "kid", 102.0, 120.0)],
        messages=[("kid", "user", "the parent task"),
                  ("grandkid", "user", "the nested task")],
    )
    assert _children(db)["grandkid"] == "the nested task"


def test_a_database_without_message_session_ids_still_lists(tmp_path):
    # Older schemas exist; a missing column must degrade to no title rather
    # than losing the whole listing.
    path = tmp_path / "state.db"
    conn = sqlite3.Connection(str(path))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, source TEXT, title TEXT,
            parent_session_id TEXT, started_at REAL, ended_at REAL
        );
        CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT);
        INSERT INTO sessions VALUES ('chat','webui',NULL,NULL,100.0,NULL);
        INSERT INTO sessions VALUES ('kid','subagent',NULL,'chat',101.0,120.0);
        """
    )
    conn.commit()
    conn.close()
    parents = list_parents_with_subagent_children(path)
    assert parents and parents[0]["children"][0]["session_id"] == "kid"


def test_a_database_with_no_messages_table_still_lists(tmp_path):
    path = tmp_path / "state.db"
    conn = sqlite3.Connection(str(path))
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, source TEXT, title TEXT,
            parent_session_id TEXT, started_at REAL, ended_at REAL
        );
        INSERT INTO sessions VALUES ('chat','webui',NULL,NULL,100.0,NULL);
        INSERT INTO sessions VALUES ('kid','subagent',NULL,'chat',101.0,120.0);
        """
    )
    conn.commit()
    conn.close()
    parents = list_parents_with_subagent_children(path)
    assert parents and parents[0]["children"][0]["session_id"] == "kid"
