"""Dispatch-order parity for ``api/routes.py``.

The route inventory (``route_chain_inventory``) reduces both dispatch forms --
the legacy ``if parsed.path ...`` chain and ``RouteTable`` literals -- to one
ordered sequence of claims per HTTP method.  These tests hold that sequence
against ``route_inventory_snapshot.json`` so moving a route between forms, or
reorganising either form, cannot drop a route, reorder two routes, or move a
route across a guard without a deliberate snapshot update.

Adding a route needs no snapshot change (the snapshot must be a subsequence
of the live order).  Removing or reordering one does: regenerate with
``python tests/route_chain_inventory.py --write-snapshot`` and review the diff.
"""

from __future__ import annotations

import json
import textwrap

import pytest

from tests.route_chain_inventory import (
    HANDLER_FUNCTIONS,
    SNAPSHOT_PATH,
    build_inventory,
    route_order,
    route_source,
    snapshot_entries,
)

METHODS = list(HANDLER_FUNCTIONS.values())
VISIBILITY_GUARD = "middleware _guard_request_session_visibility:path_scoped"


@pytest.fixture(scope="module")
def snapshot() -> dict[str, list[str]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live() -> dict[str, list[str]]:
    return snapshot_entries(build_inventory())


def _first_subsequence_break(expected: list[str], actual: list[str]) -> str | None:
    """Describe where ``expected`` stops being a subsequence of ``actual``."""
    position = 0
    for index, entry in enumerate(expected):
        try:
            position = actual.index(entry, position) + 1
        except ValueError:
            if entry in actual:
                previous = expected[index - 1] if index else "<start>"
                return f"{entry!r} now dispatches before {previous!r}"
            return f"{entry!r} is no longer dispatched"
    return None


@pytest.mark.parametrize("method", METHODS)
def test_snapshot_routes_still_dispatch_in_order(method, snapshot, live):
    problem = _first_subsequence_break(snapshot[method], live[method])
    assert problem is None, (
        f"{method}: {problem}. If intentional, regenerate the snapshot with "
        "`python tests/route_chain_inventory.py --write-snapshot`."
    )


@pytest.mark.parametrize("method", METHODS)
def test_middleware_phases_unchanged(method, snapshot, live):
    """Guards are not routes: adding, removing or reordering one is a review event."""
    expected = [e for e in snapshot[method] if e.startswith("middleware ")]
    actual = [e for e in live[method] if e.startswith("middleware ")]
    assert actual == expected


def test_routes_ahead_of_get_visibility_guard_are_exactly_the_public_set(snapshot, live):
    """A GET route dispatched before the session-visibility guard is public.

    Share pages, login, OIDC and the PWA shell are deliberately there.  Any
    other route landing ahead of the guard would skip the per-profile session
    visibility check, so the set is pinned exactly.
    """

    def public(entries: list[str]) -> list[str]:
        return [e for e in entries[: entries.index(VISIBILITY_GUARD)] if not e.startswith("middleware ")]

    assert public(live["GET"]) == public(snapshot["GET"])


@pytest.mark.parametrize("method", METHODS)
def test_no_route_claimed_twice(method, live):
    routes = [e for e in live[method] if not e.startswith("middleware ")]
    duplicates = sorted({e for e in routes if routes.count(e) > 1})
    assert duplicates == []


# ── inventory extraction: both forms reduce to the same sequence ────────────

_CHAIN_SOURCE = textwrap.dedent(
    '''
    def handle_get(handler, parsed):
        proxy_result = _handle_extension_sidecar_proxy(handler, parsed, "GET")
        if proxy_result is not False:
            return proxy_result
        if parsed.path in ("/", "/index.html") or parsed.path.startswith("/session/"):
            return serve_shell(handler)
        if parsed.path.startswith("/api/") and not _guard_request_session_visibility(handler, parsed, method="GET"):
            return True
        if parsed.path == "/api/a":
            return _handle_a(handler, parsed)
        _LOCAL_PREFIX = "/api/b/"
        if parsed.path.startswith(_LOCAL_PREFIX):
            data = load()
            return emit(handler, data)
        sid = _session_id_from(parsed.path)
        if sid is not None:
            return _handle_session(handler, parsed, sid)
        for name in PLUGINS:
            pass
        return False

    def handle_post(handler, parsed):
        if parsed.path in {"/api/z", "/api/y"}:
            return _handle_zy(handler, body)
        if parsed.path.startswith(_CREWS) and parsed.path.endswith(("/pause", "/resume")):
            return _handle_crews(handler, body)
        return False

    _CREWS = "/api/crews/"
    '''
)

_TABLE_SOURCE = textwrap.dedent(
    '''
    _CREWS = "/api/crews/"
    _LOCAL_PREFIX = "/api/b/"

    def handle_get(handler, parsed):
        proxy_result = _handle_extension_sidecar_proxy(handler, parsed, "GET")
        if proxy_result is not False:
            return proxy_result
        if (result := _GET_PUBLIC.dispatch(parsed.path, handler, parsed)) is not NOT_HANDLED:
            return result
        if parsed.path.startswith("/api/") and not _guard_request_session_visibility(handler, parsed, method="GET"):
            return True
        if (result := _GET_ROUTES.dispatch(parsed.path, handler, parsed)) is not NOT_HANDLED:
            return result
        for name in PLUGINS:
            pass
        return False

    def _route_get_shell(handler, parsed):
        return serve_shell(handler)

    def _route_get_api_a(handler, parsed):
        return _handle_a(handler, parsed)

    def _route_get_api_b(handler, parsed):
        data = load()
        return emit(handler, data)

    def _route_get_session(handler, parsed):
        sid = _session_id_from(parsed.path)
        if sid is not None:
            return _handle_session(handler, parsed, sid)
        return NOT_HANDLED

    _GET_PUBLIC = RouteTable((
        ((Exact("/", "/index.html"), Prefix("/session/")), _route_get_shell),
    ))
    _GET_ROUTES = RouteTable((
        (Exact("/api/a"), _route_get_api_a),
        (Prefix(_LOCAL_PREFIX), _route_get_api_b),
        (Param(_session_id_from), _route_get_session),
    ))

    def handle_post(handler, parsed):
        if (result := _POST_ROUTES.dispatch(parsed.path, handler, parsed, body, diag)) is not NOT_HANDLED:
            return result
        return False

    def _route_post_zy(handler, parsed, body, diag):
        return _handle_zy(handler, body)

    def _route_post_crews(handler, parsed, body, diag):
        return _handle_crews(handler, body)

    _POST_ROUTES = RouteTable((
        (Exact("/api/y", "/api/z"), _route_post_zy),
        (PrefixSuffix(_CREWS, "/pause", "/resume"), _route_post_crews),
    ))
    '''
)


def test_chain_and_table_forms_reduce_to_the_same_sequence():
    chain = snapshot_entries(build_inventory(_CHAIN_SOURCE))
    table = snapshot_entries(build_inventory(_TABLE_SOURCE))
    assert chain == table
    assert chain["GET"] == [
        "middleware proxy_result is not False",
        "exact /",
        "exact /index.html",
        "prefix /session/",
        VISIBILITY_GUARD,
        "exact /api/a",
        "prefix /api/b/",
        "parametric _session_id_from",
        "middleware for PLUGINS",
    ]
    assert chain["POST"] == [
        "exact /api/y",
        "exact /api/z",
        "prefix_suffix /api/crews/|/pause",
        "prefix_suffix /api/crews/|/resume",
    ]


def test_chain_and_table_forms_classify_targets_the_same():
    def targets(source):
        return [(c.method, c.pattern, c.target) for c in build_inventory(source) if c.kind != "middleware"]

    assert targets(_CHAIN_SOURCE) == targets(_TABLE_SOURCE)


def test_route_source_is_the_same_text_in_either_form():
    chain_body = route_source("GET", "/api/b/thing", _CHAIN_SOURCE)
    table_body = route_source("GET", "/api/b/thing", _TABLE_SOURCE)
    assert chain_body == table_body == "data = load()\nreturn emit(handler, data)\n"


def test_route_source_follows_dispatch_order_for_overlapping_matchers():
    # "/session/x" is claimed by the shell's prefix; nothing earlier matches it.
    assert "serve_shell" in route_source("GET", "/session/x", _CHAIN_SOURCE)
    assert "serve_shell" in route_source("GET", "/session/x", _TABLE_SOURCE)


def test_route_order_lists_middleware_in_place():
    order = route_order("GET", _TABLE_SOURCE)
    assert order.index("prefix /session/") < order.index(VISIBILITY_GUARD) < order.index("exact /api/a")


def test_unknown_table_is_an_error_not_a_silent_gap():
    broken = _TABLE_SOURCE.replace("_GET_ROUTES = RouteTable", "_OTHER = RouteTable")
    with pytest.raises(ValueError, match="unknown table '_GET_ROUTES'"):
        build_inventory(broken)
