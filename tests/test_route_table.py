"""Behaviour of ``api.route_table`` -- the dispatcher behind ``api/routes.py``.

A ``RouteTable`` must behave exactly like the ``if parsed.path ...`` chain it
replaces: entries are tried in declaration order, a route that does not
handle the request (returns ``NOT_HANDLED``) lets later matching routes run,
and any other return value -- including ``False`` and ``None`` -- is final.
"""

from __future__ import annotations

import pytest

from api.route_table import (
    NOT_HANDLED,
    Exact,
    Param,
    Prefix,
    PrefixSuffix,
    RouteTable,
)


def _recorder(log, name, result=True):
    def route(*args):
        log.append((name, args))
        return result

    return route


def test_exact_route_receives_the_dispatch_arguments():
    log = []
    table = RouteTable(((Exact("/api/a"), _recorder(log, "a")),))
    assert table.dispatch("/api/a", "handler", "parsed") is True
    assert log == [("a", ("handler", "parsed"))]


def test_unmatched_path_is_not_handled():
    table = RouteTable(((Exact("/api/a"), _recorder([], "a")),))
    assert table.dispatch("/api/b", "handler") is NOT_HANDLED


def test_exact_matches_whole_path_only():
    table = RouteTable(((Exact("/api/a"), _recorder([], "a")),))
    assert table.dispatch("/api/a/", "h") is NOT_HANDLED
    assert table.dispatch("/api/ab", "h") is NOT_HANDLED


def test_exact_accepts_several_paths():
    log = []
    table = RouteTable(((Exact("/", "/index.html"), _recorder(log, "shell")),))
    table.dispatch("/", "h")
    table.dispatch("/index.html", "h")
    assert [name for name, _ in log] == ["shell", "shell"]


def test_prefix_suffix_and_param_matchers():
    log = []
    table = RouteTable(
        (
            (Prefix("/api/kanban/"), _recorder(log, "kanban")),
            (PrefixSuffix("/api/crews/", "/pause", "/resume"), _recorder(log, "crew")),
            (Param(lambda path: path.rsplit("/", 1)[-1] if path.startswith("/s/") else None), _recorder(log, "param")),
        )
    )
    table.dispatch("/api/kanban/tasks", "h")
    table.dispatch("/api/crews/c1/resume", "h")
    assert table.dispatch("/api/crews/c1/delete", "h") is NOT_HANDLED
    table.dispatch("/s/abc", "h")
    assert table.dispatch("/t/abc", "h") is NOT_HANDLED
    assert [name for name, _ in log] == ["kanban", "crew", "param"]


def test_declaration_order_wins_over_matcher_kind():
    """A prefix declared before an exact path is tried first, as in the chain."""
    log = []
    table = RouteTable(
        (
            (Prefix("/api/"), _recorder(log, "prefix")),
            (Exact("/api/a"), _recorder(log, "exact")),
        )
    )
    table.dispatch("/api/a", "h")
    assert [name for name, _ in log] == ["prefix"]


def test_not_handled_falls_through_to_the_next_match_in_order():
    log = []
    table = RouteTable(
        (
            (Prefix("/plugins/"), _recorder(log, "assets", NOT_HANDLED)),
            (Exact("/plugins/x"), _recorder(log, "page")),
        )
    )
    assert table.dispatch("/plugins/x", "h") is True
    assert [name for name, _ in log] == ["assets", "page"]


def test_all_matches_not_handled_returns_not_handled():
    table = RouteTable(((Prefix("/p/"), _recorder([], "a", NOT_HANDLED)),))
    assert table.dispatch("/p/x", "h") is NOT_HANDLED


@pytest.mark.parametrize("final", [False, None, 0, ""])
def test_falsy_results_are_final_not_fallthrough(final):
    """``return False`` from a route means 404 now, exactly as in the chain."""
    log = []
    table = RouteTable(
        (
            (Prefix("/p/"), _recorder(log, "first", final)),
            (Exact("/p/x"), _recorder(log, "second")),
        )
    )
    assert table.dispatch("/p/x", "h") is final
    assert [name for name, _ in log] == ["first"]


def test_entry_with_several_matching_matchers_runs_once():
    log = []
    table = RouteTable((((Exact("/share"), Prefix("/share")), _recorder(log, "share")),))
    table.dispatch("/share", "h")
    assert len(log) == 1


def test_exceptions_propagate():
    def boom(*_args):
        raise RuntimeError("route failed")

    table = RouteTable(((Exact("/x"), boom),))
    with pytest.raises(RuntimeError, match="route failed"):
        table.dispatch("/x", "h")


def test_not_handled_has_no_truth_value():
    """Leaking the sentinel into an ``if result:`` check must fail loudly."""
    with pytest.raises(TypeError):
        bool(NOT_HANDLED)


def test_not_handled_is_a_singleton_with_a_readable_repr():
    assert repr(NOT_HANDLED) == "NOT_HANDLED"
    assert NOT_HANDLED is NOT_HANDLED


def _ok(*_args):
    return True


@pytest.mark.parametrize(
    "build, error",
    [
        (lambda: RouteTable(((Exact("/x"), "not callable"),)), TypeError),
        (lambda: RouteTable((("/x", _ok),)), TypeError),
        (lambda: RouteTable(((Exact("/x"), _ok, "extra"),)), TypeError),
        (lambda: Exact(), ValueError),
        (lambda: Exact("x"), ValueError),
        (lambda: Prefix(""), ValueError),
        (lambda: PrefixSuffix("/p/"), ValueError),
        (lambda: Param("not callable"), TypeError),
    ],
)
def test_construction_rejects_malformed_entries(build, error):
    with pytest.raises(error):
        build()
