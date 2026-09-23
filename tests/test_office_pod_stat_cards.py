"""The floating per-pod stat card generalised to both outlets.

Business has a fixed, named, coloured roster; Projects has no name to give a
pod (it's just "whoever's parent spawned this cluster") but still gets a
colour, derived and stable rather than a human's choice --
static/office/index.js's officeCardSpecs() is the one place that difference
lives. Real behaviour is
covered end-to-end by tests/test_office_browser_smoke.py
(HERMES_WEBUI_BROWSER_TESTS=1, since it needs a real OrthographicCamera to
prove the projection lands somewhere sane); this file pins the source-level
structure so the generalisation itself is checked without a browser.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")


def _function_body(src, name):
    marker = f"function {name}("
    start = src.index(marker)
    brace = src.index("{", start)
    depth = 0
    i = brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError(f"unterminated function: {name}")


def test_office_card_specs_has_a_branch_for_each_outlet():
    body = _function_body(OFFICE_INDEX_SRC, "officeCardSpecs")
    assert "_outlet === 'business'" in body
    assert "_roster.departments.map" in body
    # Projects has no department names, but its stable landmark does:
    # the central conductor platform carries a Conductor card.
    assert "{ key: '__conductor__', name: 'Conductor'" in body
    assert "key: '__conductor__'" in body
    assert "colorForProjectsCluster(key)" in body


def test_projects_cards_are_derived_from_the_live_desks_not_a_standing_list():
    body = _function_body(OFFICE_INDEX_SRC, "officeCardSpecs")
    at = body.index("// Projects:")
    tail = body[at:]
    assert "(view.desks || []).forEach" in tail


def test_reposition_no_longer_gates_on_the_business_outlet():
    body = _function_body(OFFICE_INDEX_SRC, "repositionDepartmentCards")
    assert "_outlet" not in body, (
        "repositioning must run for whichever outlet currently has cards up, "
        "not just Business"
    )


def test_overview_cards_stay_anchored_instead_of_hiding_or_detaching():
    body = _function_body(OFFICE_INDEX_SRC, "repositionDepartmentCards")
    assert "MIN_CARD_ZOOM" not in OFFICE_INDEX_SRC
    assert "const candidates" not in body
    assert "placement = { x, y, bounds" in body


def test_a_card_without_a_colour_clears_any_previous_one():
    # A card element is reused by key across renders; if a Projects pod ever
    # reused a DOM node that had carried a colour, it must not keep glowing
    # with a stale one.
    body = _function_body(OFFICE_INDEX_SRC, "renderDepartmentCards")
    assert "el.style.removeProperty('--office-dept-color')" in body


def test_the_card_name_row_is_omitted_not_left_blank():
    body = _function_body(OFFICE_INDEX_SRC, "renderDepartmentCards")
    assert "spec.name ? `<div class=\"office-dept-card-name\">" in body
