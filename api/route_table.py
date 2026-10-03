"""Ordered route tables for HTTP dispatch in ``api/routes.py``.

``handle_get`` / ``handle_post`` / ... used to dispatch with one long
``if parsed.path == ...`` chain per method.  A ``RouteTable`` replaces a run
of those branches without changing what the chain did:

* entries are tried in declaration order -- the chain's source order --
  whatever kind of matcher they use, so an earlier prefix still wins over a
  later exact path;
* a route returns ``NOT_HANDLED`` when it matched the path but did not
  handle the request (the chain's "branch body fell off the end"); later
  matching entries then run, and then whatever follows the table in the
  handler;
* any other return value -- including ``False`` (404) and ``None`` -- ends
  dispatch, exactly like ``return`` inside a chain branch.

Guards that sit between routes (CSRF, the extension sidecar proxy, the
session-visibility check) stay as plain code in the handler, between tables.
Which side of a guard a route is on is part of its contract.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

__all__ = ["NOT_HANDLED", "Exact", "Param", "Prefix", "PrefixSuffix", "RouteTable"]


class _NotHandled:
    """Type of ``NOT_HANDLED``.  Compare with ``is``; it has no truth value."""

    __slots__ = ()
    _instance: _NotHandled | None = None

    def __new__(cls) -> _NotHandled:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NOT_HANDLED"

    def __bool__(self) -> bool:
        # Handlers return True/False/None to the server; an `if result:` that
        # receives the sentinel would silently treat "not handled" as handled.
        raise TypeError("NOT_HANDLED has no truth value; compare with `is`")


NOT_HANDLED: Any = _NotHandled()


def _check_path(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError(f"{what} must be a string starting with '/': {value!r}")
    return value


class Exact:
    """Matches when the request path equals one of ``paths``."""

    __slots__ = ("paths",)

    def __init__(self, *paths: str) -> None:
        if not paths:
            raise ValueError("Exact() needs at least one path")
        self.paths = tuple(_check_path(p, "Exact path") for p in paths)

    def __repr__(self) -> str:
        return f"Exact{self.paths!r}"


class Prefix:
    """Matches when the request path starts with ``prefix``."""

    __slots__ = ("prefix",)

    def __init__(self, prefix: str) -> None:
        self.prefix = _check_path(prefix, "Prefix")

    def matches(self, path: str) -> bool:
        return path.startswith(self.prefix)

    def __repr__(self) -> str:
        return f"Prefix({self.prefix!r})"


class PrefixSuffix:
    """Matches when the path starts with ``prefix`` and ends with any of ``suffixes``."""

    __slots__ = ("prefix", "suffixes")

    def __init__(self, prefix: str, *suffixes: str) -> None:
        if not suffixes:
            raise ValueError("PrefixSuffix() needs at least one suffix")
        self.prefix = _check_path(prefix, "PrefixSuffix prefix")
        self.suffixes = tuple(suffixes)

    def matches(self, path: str) -> bool:
        return path.startswith(self.prefix) and path.endswith(self.suffixes)

    def __repr__(self) -> str:
        return f"PrefixSuffix({self.prefix!r}, *{self.suffixes!r})"


class Param:
    """Matches when ``parse(path)`` is not ``None``.

    For paths that carry a parameter (``/api/sessions/<id>/events``).  The
    route function parses the path again itself; ``parse`` must be pure.
    """

    __slots__ = ("parse",)

    def __init__(self, parse: Callable[[str], Any]) -> None:
        if not callable(parse):
            raise TypeError(f"Param() needs a callable, got {parse!r}")
        self.parse = parse

    def matches(self, path: str) -> bool:
        return self.parse(path) is not None

    def __repr__(self) -> str:
        return f"Param({getattr(self.parse, '__name__', self.parse)!r})"


Matcher = Exact | Prefix | PrefixSuffix | Param
Route = Callable[..., Any]


class RouteTable:
    """Routes in declaration order; see the module docstring for semantics.

    ``entries`` is a sequence of ``(matcher_or_matchers, route)`` pairs.  A
    route is called with the arguments given to :meth:`dispatch` after the
    path.
    """

    __slots__ = ("_exact", "_scanned")

    def __init__(self, entries: Iterable[tuple[Matcher | tuple[Matcher, ...], Route]]) -> None:
        self._exact: dict[str, list[tuple[int, Route]]] = {}
        self._scanned: list[tuple[int, Prefix | PrefixSuffix | Param, Route]] = []
        for order, entry in enumerate(entries):
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(f"route entry must be a (matchers, route) pair: {entry!r}")
            matchers, route = entry
            if not callable(route):
                raise TypeError(f"route must be callable: {route!r}")
            for matcher in matchers if isinstance(matchers, tuple) else (matchers,):
                if isinstance(matcher, Exact):
                    for path in matcher.paths:
                        self._exact.setdefault(path, []).append((order, route))
                elif isinstance(matcher, (Prefix, PrefixSuffix, Param)):
                    self._scanned.append((order, matcher, route))
                else:
                    raise TypeError(f"unknown matcher: {matcher!r}")

    def candidates(self, path: str) -> list[Route]:
        """Routes whose matchers accept ``path``, in declaration order, once each."""
        found = dict(self._exact.get(path, ()))
        for order, matcher, route in self._scanned:
            if order not in found and matcher.matches(path):
                found[order] = route
        return [found[order] for order in sorted(found)]

    def dispatch(self, path: str, *args: Any) -> Any:
        """Run matching routes in order until one returns something other than ``NOT_HANDLED``."""
        for route in self.candidates(path):
            result = route(*args)
            if result is not NOT_HANDLED:
                return result
        return NOT_HANDLED
