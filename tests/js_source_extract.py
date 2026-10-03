import re


def _body_open_brace(js: str, start: int) -> int:
    """Index of the ``{`` that opens the body of the function declared at ``start``.

    The parameter list is matched first, so a default such as ``opts={}`` is not
    mistaken for the body.
    """
    paren = js.find("(", start)
    assert paren >= 0, "function parameter list not found"
    depth = 0
    for i in range(paren, len(js)):
        if js[i] == "(":
            depth += 1
        elif js[i] == ")":
            depth -= 1
            if depth == 0:
                brace = js.find("{", i)
                assert brace >= 0, "function body brace not found"
                return brace
    raise AssertionError("function parameter list unbalanced")


def _function_end(js: str, start: int, name: str) -> int:
    depth = 1
    i = _body_open_brace(js, start) + 1
    while i < len(js) and depth > 0:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    assert depth == 0, f"{name} function braces unbalanced"
    return i


def extract_function(js: str, name: str, prefix: str = "function") -> str:
    marker = f"{prefix} {name}("
    start = js.find(marker)
    assert start >= 0, f"{name} function not found in static/panels.js"
    return js[start:_function_end(js, start, name)]


_TOP_LEVEL_FUNCTION = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


def top_level_functions(js: str) -> str:
    """Every top-level function declaration in ``js``, without the code between them.

    For Node harnesses that load a slice of a browser module: the slice can also
    hold top-level wiring (``window.addEventListener``, globals read at load
    time) that cannot run outside the page.
    """
    parts = []
    pos = 0
    for match in _TOP_LEVEL_FUNCTION.finditer(js):
        if match.start() < pos:
            continue
        end = _function_end(js, match.start(), match.group(1))
        parts.append(js[match.start():end])
        pos = end
    return "\n\n".join(parts)
