"""The agent split ``hermes_cli.kanban_db`` into ``kanban_db_connect`` and
``kanban_db_dispatch``; ``connect``, ``connect_closing`` and ``dispatch_once``
are no longer re-exported from ``kanban_db``. The bridge must still find them,
or every Kanban read answers 500."""

import sqlite3
import sys
import types

import pytest


@pytest.fixture()
def split_agent(monkeypatch, tmp_path):
    db = tmp_path / "kanban.db"
    package = types.ModuleType("hermes_cli")
    package.__path__ = []
    main = types.ModuleType("hermes_cli.kanban_db")
    main.init_db = lambda *a, board=None, **k: db
    connect_mod = types.ModuleType("hermes_cli.kanban_db_connect")
    connect_mod.connect = lambda *a, board=None, **k: sqlite3.connect(db)
    connect_mod.connect_closing = lambda *a, board=None, **k: sqlite3.connect(db)
    dispatch_mod = types.ModuleType("hermes_cli.kanban_db_dispatch")
    dispatch_mod.dispatch_once = lambda conn, dry_run=False, max_spawn=None: {"spawned": 0, "dry_run": dry_run}
    package.kanban_db = main
    for name, module in (("hermes_cli", package), ("hermes_cli.kanban_db", main),
                         ("hermes_cli.kanban_db_connect", connect_mod),
                         ("hermes_cli.kanban_db_dispatch", dispatch_mod)):
        monkeypatch.setitem(sys.modules, name, module)
    return main


def test_connection_comes_from_the_split_connect_module(split_agent):
    from api import kanban_bridge

    with kanban_bridge._conn() as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)


def test_dispatcher_comes_from_the_split_dispatch_module(split_agent):
    from api import kanban_bridge

    kb = kanban_bridge._kb()
    assert kb.dispatch_once(None, dry_run=True) == {"spawned": 0, "dry_run": True}
