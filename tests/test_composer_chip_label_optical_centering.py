"""Composer chip labels are centred on their ink, not on their line box.

The reported symptom was the workspace pill's text sitting low against the
folder icon beside it. Every box-level measurement said the row was perfect,
because it was: `.composer-workspace-group` and its two buttons all centre at
the same y. What is off is the *glyphs* inside the label's box.

Flexbox centres the line box. Where the glyphs sit inside that box is decided
by the font, and the offset of the x-height band's centre from the box centre
works out to `(ascent - descent - xHeight) / 2` -- independent of line-height,
so nothing about `align-items`, `line-height` or padding can move it. Measured
in headless Chromium the local fallback font gives +0.5px, which is why this
never reproduced here; Segoe UI, which is what the `-apple-system` stack lands
on for Windows users, has a far more asymmetric ascent/descent and works out
to roughly +2.2px. That is what the reporter's screenshot showed: icon and
chevron centred at 29.5, the text's x-height band at 31.0.

`text-box-edge` trims the line box to the glyph metrics so flex centring has
the ink to work with. The under-edge choice matters and is not cosmetic: these
labels carry `overflow:hidden` for their ellipsis, so an `alphabetic`
under-edge -- which ends the box at the baseline -- clips descenders outright.
Verified in headless Chromium on the string "workspace": with `cap alphabetic`
the deepest ink pixel lands exactly on the baseline, i.e. the p's tail is gone,
and the x-band does not move anyway. `cap text` keeps the font's descent edge,
so descenders survive, and the offset becomes `(cap - descent - xHeight) / 2`:
-0.5px measured locally, about -0.35px for Segoe UI.

The rule has to cover every label in the footer row. Correcting one label alone
would leave it a full 2.5px off its neighbours on the reporter's font, trading
one misalignment for a worse one.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).parent.parent
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")

# Every text label sitting beside an icon in the composer footer row.
FOOTER_CHIP_LABELS = (
    ".composer-workspace-label",
    ".composer-profile-label",
    ".composer-model-label",
    ".composer-reasoning-label",
    ".composer-toolsets-label",
    ".provider-quota-chip-label",
    ".yolo-pill-label",
)


def _trim_rule() -> str:
    """The selector list and declaration of the text-box rule, comments out.

    The rule is preceded by a long comment that names `cap alphabetic` as the
    thing it is deliberately not doing, so the prose has to be stripped before
    asserting on what the CSS actually says.
    """
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    m = re.search(r"[^{}]*text-box:[^;]*;[^}]*}", css)
    assert m, "no text-box rule found in static/style.css"
    start = css.rfind("}", 0, m.start()) + 1
    return css[start:m.end()]


def test_footer_chip_labels_trim_their_line_box():
    rule = _trim_rule()
    for sel in FOOTER_CHIP_LABELS:
        assert sel in rule, (
            f"{sel} must be in the text-box rule — correcting only some labels "
            "in the row leaves the corrected ones misaligned against the rest"
        )


def test_under_edge_is_text_not_alphabetic():
    # An alphabetic under-edge ends the box at the baseline, and these labels
    # clip to their box for the ellipsis, so every descender is cut off.
    rule = _trim_rule()
    assert "cap text" in rule, (
        "the trim must be `cap text`: a cap over-edge with the font's descent "
        f"edge kept underneath (got: {rule!r})"
    )
    assert "cap alphabetic" not in rule, (
        "`cap alphabetic` clips descenders on these overflow:hidden labels — "
        "verified in headless Chromium, the p in 'workspace' loses its tail"
    )


def test_labels_still_clip_for_their_ellipsis():
    # The trim only makes sense because these labels clip; if that ever stops
    # being true the under-edge reasoning above needs revisiting.
    assert "text-overflow:ellipsis" in CSS
    m = re.search(r"\.composer-workspace-label\{([^}]*)\}", CSS)
    assert m and "overflow:hidden" in m.group(1), (
        "the workspace label is expected to clip — the choice of under-edge "
        "in the text-box rule depends on it"
    )
