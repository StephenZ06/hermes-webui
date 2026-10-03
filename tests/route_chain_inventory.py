"""Static inventory of HTTP dispatch in ``api/routes.py``.

Verification tooling for the route-table migration, not production code.

``handle_get`` / ``handle_post`` / ``handle_patch`` / ``handle_delete`` /
``handle_put`` dispatch requests through two forms:

* the legacy form -- a sequence of top-level ``if parsed.path ...:``
  branches, evaluated in source order;
* the table form -- ``api.route_table.RouteTable`` literals, dispatched from
  the handler by an ``if (result := TABLE.dispatch(...)) is not NOT_HANDLED``
  statement.

Both forms are reduced here to the same ordered ``RouteClaim`` sequence, so a
handler can be migrated from one form to the other and the sequence compared
before and after.  The parity test (``test_route_table_parity.py``) holds that
sequence against a checked-in snapshot.

Claim kinds
-----------
``exact``
    ``parsed.path == "/a"`` / ``parsed.path in ("/a", "/b")`` / ``Exact(...)``.
``prefix``
    ``parsed.path.startswith(P)`` / ``Prefix(P)``.  ``P`` may be a module- or
    handler-level string constant; it is resolved.
``prefix_suffix``
    ``startswith(P) and endswith(S)`` / ``PrefixSuffix(P, *S)``; one claim per
    suffix, pattern ``"P|S"``.
``parametric``
    ``x = fn(parsed.path)`` followed by ``if x is not None:`` /
    ``Param(fn)``; pattern is ``fn``.
``middleware``
    Any other top-level ``if`` or ``for`` in a handler: the CSRF gate, the
    sidecar proxy, the session-visibility guard, request diagnostics, the
    plugin-page loop.  These are not routes, but their position relative to
    routes is a contract (a route ahead of the visibility guard is public),
    so they are part of the sequence.

Run ``python tests/route_chain_inventory.py`` for a summary, or
``--write-snapshot`` to regenerate the parity snapshot after an intentional
route removal or reordering.
"""

from __future__ import annotations

import ast
import json
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROUTES_PATH = Path(__file__).resolve().parent.parent / "api" / "routes.py"
SNAPSHOT_PATH = Path(__file__).resolve().parent / "route_inventory_snapshot.json"

HANDLER_FUNCTIONS = {
    "handle_get": "GET",
    "handle_post": "POST",
    "handle_patch": "PATCH",
    "handle_delete": "DELETE",
    "handle_put": "PUT",
}

# Phase-guard callables.  A branch test calling one of these is phase logic
# even when it also inspects the path (the GET visibility guard is scoped to
# ``/api/``), so it is middleware rather than a route.
_GUARD_CALLS = frozenset(
    {
        "_guard_request_session_visibility",
        "_check_csrf",
        "_csrf_exempt_path",
        "_handle_extension_sidecar_proxy",
    }
)

_MATCHER_CALLS = frozenset({"Exact", "Prefix", "PrefixSuffix", "Param"})
_NOT_HANDLED = "NOT_HANDLED"


@dataclass(frozen=True)
class RouteClaim:
    """One matcher claimed by one dispatch unit, in dispatch order."""

    method: str
    kind: str  # exact | prefix | prefix_suffix | parametric | middleware
    pattern: str  # path, prefix, "prefix|suffix", matcher fn, or middleware label
    target: str  # "delegating:<fn>" | "inline" | "middleware"
    start: int  # first source line of the dispatch unit (1-based)
    end: int  # last source line of the dispatch unit

    def entry(self) -> str:
        """Snapshot form: what the claim matches, not where it lives.

        Line numbers and targets change on every edit or extraction; the
        matcher and its position in the sequence are what dispatch depends on.
        """
        return f"{self.kind} {self.pattern}"


# ── expression helpers ──────────────────────────────────────────────────────


def _call_name(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _string_constants(body: list[ast.stmt]) -> dict[str, str]:
    """``NAME = "literal"`` assignments in a statement list.

    Some prefixes are named constants -- at module level, or assigned inside
    a handler just before the branch that uses them -- so both are resolved.
    """
    constants: dict[str, str] = {}
    for node in body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _literal(node: ast.expr, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _literals(node: ast.expr, constants: dict[str, str]) -> list[str]:
    """A string, or a tuple/list/set of strings; ``[]`` if unresolvable."""
    single = _literal(node, constants)
    if single is not None:
        return [single]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        elts = node.elts
        if isinstance(node, ast.Set):
            elts = sorted(elts, key=ast.unparse)  # sets have no source order
        out = [_literal(elt, constants) for elt in elts]
        if any(value is None for value in out):
            return []
        return [value for value in out if value is not None]
    return []


def _is_parsed_path(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "path"
        and isinstance(node.value, ast.Name)
        and node.value.id == "parsed"
    )


def _path_method_call(node: ast.expr) -> tuple[str, ast.expr] | None:
    """``parsed.path.<method>(arg)`` -> ``(method, arg)``."""
    if (
        isinstance(node, ast.Call)
        and len(node.args) == 1
        and isinstance(node.func, ast.Attribute)
        and _is_parsed_path(node.func.value)
    ):
        return node.func.attr, node.args[0]
    return None


def _mentions_guard(node: ast.expr) -> bool:
    return any(_call_name(sub) in _GUARD_CALLS for sub in ast.walk(node))


def _chain_matchers(test: ast.expr, constants: dict[str, str]) -> list[tuple[str, str]]:
    """Reduce a legacy branch test to ``(kind, pattern)`` pairs.

    ``[]`` means the test is not a pure path match (the branch is middleware).
    """
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and _is_parsed_path(test.left):
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, ast.Eq):
            value = _literal(right, constants)
            return [("exact", value)] if value is not None else []
        if isinstance(op, ast.In):
            return [("exact", value) for value in _literals(right, constants)]
        return []

    call = _path_method_call(test)
    if call is not None:
        method, arg = call
        if method == "startswith":
            return [("prefix", value) for value in _literals(arg, constants)]
        return []

    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and len(test.values) == 2:
        first = _path_method_call(test.values[0])
        second = _path_method_call(test.values[1])
        if first and second and first[0] == "startswith" and second[0] == "endswith":
            prefixes = _literals(first[1], constants)
            suffixes = _literals(second[1], constants)
            if len(prefixes) == 1 and suffixes:
                return [("prefix_suffix", f"{prefixes[0]}|{s}") for s in sorted(suffixes)]
        return []

    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        combined: list[tuple[str, str]] = []
        for value in test.values:
            part = _chain_matchers(value, constants)
            if not part:
                return []
            combined.extend(part)
        return combined

    return []


def _parametric_matcher(stmt: ast.If, previous: ast.stmt | None) -> str | None:
    """``x = fn(parsed.path)`` then ``if x is not None:`` -> ``fn``."""
    test = stmt.test
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and isinstance(test.left, ast.Name)
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is None
    ):
        return None
    if (
        isinstance(previous, ast.Assign)
        and len(previous.targets) == 1
        and isinstance(previous.targets[0], ast.Name)
        and previous.targets[0].id == test.left.id
        and isinstance(previous.value, ast.Call)
        and isinstance(previous.value.func, ast.Name)
        and any(_is_parsed_path(arg) for arg in previous.value.args)
    ):
        return previous.value.func.id
    return None


def _body_target(body: list[ast.stmt]) -> str:
    """``delegating:<fn>`` when a body is a single ``return fn(...)``.

    A trailing ``return NOT_HANDLED`` (added to extracted bodies that can fall
    through) is ignored, so a branch classifies the same before and after
    extraction.
    """
    stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    if (
        stmts
        and isinstance(stmts[-1], ast.Return)
        and isinstance(stmts[-1].value, ast.Name)
        and stmts[-1].value.id == _NOT_HANDLED
    ):
        stmts = stmts[:-1]
    if len(stmts) == 1 and isinstance(stmts[0], ast.Return):
        name = _call_name(stmts[0].value)
        if name:
            return f"delegating:{name}"
    return "inline"


def _middleware_label(test: ast.expr) -> str:
    """Stable label: the guard call name where there is one."""
    for sub in ast.walk(test):
        name = _call_name(sub)
        if name in _GUARD_CALLS:
            scope = "path_scoped" if any(_is_parsed_path(n) for n in ast.walk(test)) else "all"
            return f"{name}:{scope}"
    return ast.unparse(test)


# ── table form ──────────────────────────────────────────────────────────────


def _dispatched_table(stmt: ast.stmt) -> str | None:
    """Name of the table an ``if (r := TABLE.dispatch(...)) ...`` dispatches."""
    if not isinstance(stmt, ast.If):
        return None
    for sub in ast.walk(stmt.test):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "dispatch"
            and isinstance(sub.func.value, ast.Name)
        ):
            return sub.func.value.id
    return None


def _table_literals(tree: ast.Module) -> dict[str, ast.Call]:
    """Module-level ``NAME = RouteTable(...)`` assignments."""
    tables: dict[str, ast.Call] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and _call_name(node.value) == "RouteTable"
        ):
            tables[node.targets[0].id] = node.value
    return tables


def _table_matcher_claims(call: ast.Call, constants: dict[str, str]) -> list[tuple[str, str]]:
    name = _call_name(call)
    args = call.args
    if name == "Exact":
        values = [_literal(a, constants) for a in args]
        if not values or any(v is None for v in values):
            raise ValueError(f"unresolvable Exact() argument: {ast.unparse(call)}")
        return [("exact", v) for v in values if v is not None]
    if name == "Prefix":
        value = _literal(args[0], constants)
        if value is None:
            raise ValueError(f"unresolvable Prefix() argument: {ast.unparse(call)}")
        return [("prefix", value)]
    if name == "PrefixSuffix":
        prefix = _literal(args[0], constants)
        suffixes = [_literal(a, constants) for a in args[1:]]
        if prefix is None or not suffixes or any(s is None for s in suffixes):
            raise ValueError(f"unresolvable PrefixSuffix() argument: {ast.unparse(call)}")
        return [("prefix_suffix", f"{prefix}|{s}") for s in sorted(s for s in suffixes if s is not None)]
    if name == "Param":
        if len(args) != 1 or not isinstance(args[0], ast.Name):
            raise ValueError(f"Param() needs one named matcher function: {ast.unparse(call)}")
        return [("parametric", args[0].id)]
    raise ValueError(f"unknown matcher {name!r}")


def _route_fn_body(fn: ast.FunctionDef) -> list[ast.stmt]:
    """Body of an extracted route function, as the legacy branch body.

    A parametric route function is ``x = matcher(parsed.path)`` plus
    ``if x is not None: <body>`` plus ``return NOT_HANDLED``; it classifies by
    ``<body>`` so it matches the legacy branch.
    """
    body = fn.body
    if len(body) >= 2 and isinstance(body[1], ast.If) and _parametric_matcher(body[1], body[0]) is not None:
        return body[1].body
    return body


def _table_claims(
    method: str,
    table: ast.Call,
    functions: dict[str, ast.FunctionDef],
    constants: dict[str, str],
) -> list[RouteClaim]:
    """Claims of one ``RouteTable(((matchers), fn), ...)`` literal, in order."""
    if len(table.args) != 1 or not isinstance(table.args[0], (ast.Tuple, ast.List)):
        raise ValueError("RouteTable() takes one tuple/list of (matchers, fn) entries")
    claims: list[RouteClaim] = []
    for entry in table.args[0].elts:
        if not isinstance(entry, ast.Tuple) or len(entry.elts) != 2:
            raise ValueError(f"route entry must be (matchers, fn): {ast.unparse(entry)}")
        matchers, fn_node = entry.elts
        if not isinstance(fn_node, ast.Name) or fn_node.id not in functions:
            raise ValueError(f"route target must be a module-level function: {ast.unparse(fn_node)}")
        fn = functions[fn_node.id]
        target = _body_target(_route_fn_body(fn))
        calls = matchers.elts if isinstance(matchers, ast.Tuple) else [matchers]
        for call in calls:
            if not isinstance(call, ast.Call) or _call_name(call) not in _MATCHER_CALLS:
                raise ValueError(f"unknown matcher: {ast.unparse(call)}")
            for kind, pattern in _table_matcher_claims(call, constants):
                claims.append(RouteClaim(method, kind, pattern, target, fn.lineno, fn.end_lineno or fn.lineno))
    return claims


# ── inventory ───────────────────────────────────────────────────────────────


def build_inventory(source: str | None = None) -> list[RouteClaim]:
    """Every dispatch claim in ``api/routes.py``, per handler, in dispatch order."""
    text = source if source is not None else ROUTES_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    module_constants = _string_constants(tree.body)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    tables = _table_literals(tree)
    claims: list[RouteClaim] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in HANDLER_FUNCTIONS:
            continue
        method = HANDLER_FUNCTIONS[node.name]
        constants = {**module_constants, **_string_constants(node.body)}

        previous: ast.stmt | None = None
        for stmt in node.body:
            prior, previous = previous, stmt
            end = stmt.end_lineno or stmt.lineno

            if isinstance(stmt, ast.For):
                label = f"for {ast.unparse(stmt.iter)}"
                claims.append(RouteClaim(method, "middleware", label, "middleware", stmt.lineno, end))
                continue
            if not isinstance(stmt, ast.If):
                continue

            table_name = _dispatched_table(stmt)
            if table_name is not None:
                if table_name not in tables:
                    raise ValueError(f"{node.name} dispatches unknown table {table_name!r}")
                claims.extend(_table_claims(method, tables[table_name], functions, constants))
                continue

            parametric = _parametric_matcher(stmt, prior)
            if parametric is not None and prior is not None:
                target = _body_target(stmt.body)
                claims.append(RouteClaim(method, "parametric", parametric, target, prior.lineno, end))
                continue

            matchers = _chain_matchers(stmt.test, constants)
            if matchers and not _mentions_guard(stmt.test):
                target = _body_target(stmt.body)
                claims.extend(RouteClaim(method, kind, pattern, target, stmt.lineno, end) for kind, pattern in matchers)
                continue

            label = _middleware_label(stmt.test)
            claims.append(RouteClaim(method, "middleware", label, "middleware", stmt.lineno, end))

    return claims


def snapshot_entries(claims: list[RouteClaim]) -> dict[str, list[str]]:
    """Per-method ordered ``"kind pattern"`` entries."""
    out: dict[str, list[str]] = {method: [] for method in HANDLER_FUNCTIONS.values()}
    for claim in claims:
        out[claim.method].append(claim.entry())
    return out


# ── source lookup for tests ─────────────────────────────────────────────────


def _claim_matches(claim: RouteClaim, path: str) -> bool:
    if claim.kind == "exact":
        return claim.pattern == path
    if claim.kind == "prefix":
        return path.startswith(claim.pattern)
    if claim.kind == "prefix_suffix":
        prefix, suffix = claim.pattern.split("|", 1)
        return path.startswith(prefix) and path.endswith(suffix)
    return False  # parametric and middleware are not statically evaluable


def route_claim(method: str, path: str, source: str | None = None) -> RouteClaim:
    """The first route claim, in dispatch order, that matches ``path``."""
    for claim in build_inventory(source):
        if claim.method == method and claim.kind != "middleware" and _claim_matches(claim, path):
            return claim
    raise LookupError(f"no {method} route matches {path!r}")


def has_route(method: str, path: str, source: str | None = None) -> bool:
    """True when some ``method`` route matches ``path``."""
    try:
        route_claim(method, path, source)
    except LookupError:
        return False
    return True


def _header_end(lines: list[str], first: int) -> int:
    """0-based index of the line closing an ``if``/``def`` header at ``first``."""
    for index in range(first, len(lines)):
        code = lines[index].split("#", 1)[0].rstrip()
        if code.endswith(":"):
            return index
    raise ValueError(f"no header colon after line {first + 1}")


def route_source(method: str, path: str, source: str | None = None) -> str:
    """Dedented body of the code that handles ``method path``.

    The body of the legacy ``if`` branch and the body of the extracted route
    function are the same text, so this returns the same string whichever
    form the route has -- source-level assertions about a route do not depend
    on how dispatch is laid out, or on indentation.  For a parametric route
    the matcher assignment that precedes the branch is included.
    """
    text = source if source is not None else ROUTES_PATH.read_text(encoding="utf-8")
    claim = route_claim(method, path, text)
    lines = text.splitlines(keepends=True)
    first = claim.start - 1
    stripped = lines[first].lstrip()
    if stripped.startswith(("if ", "if(", "def ")):
        first = _header_end(lines, first) + 1
    return textwrap.dedent("".join(lines[first : claim.end]))


def route_order(method: str, source: str | None = None) -> list[str]:
    """Ordered ``"kind pattern"`` entries for one method, middleware included."""
    return snapshot_entries(build_inventory(source))[method]


def main(argv: list[str]) -> int:  # pragma: no cover - manual helper
    claims = build_inventory()
    if "--write-snapshot" in argv:
        payload = json.dumps(snapshot_entries(claims), indent=2) + "\n"
        SNAPSHOT_PATH.write_text(payload, encoding="utf-8")
        print(f"wrote {SNAPSHOT_PATH}")
        return 0
    routes = [c for c in claims if c.kind != "middleware"]
    print(f"routes: {len(routes)}  middleware: {len(claims) - len(routes)}")
    for method in HANDLER_FUNCTIONS.values():
        own = [c for c in routes if c.method == method]
        kinds: dict[str, int] = {}
        for c in own:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        inline = sum(1 for c in own if c.target == "inline")
        print(f"  {method:6} {len(own):4} routes {kinds}  inline={inline}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
