"""The chat surface has to reach the composer, with nothing showing underneath.

`.messages` is a transparent scroller over `#mainChat`, so whatever colour the
chat area appears to be is painted by whichever element happens to be inside it.
Give one of those inner elements an opaque background and the chat surface stops
where that element stops -- the shell's own colour shows through the remainder as
a band.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def _skin_rule_containing(selector):
    """Return the whole rule (selector list + block) that carries `selector`."""
    at = STYLE_CSS.index(selector)
    start = STYLE_CSS.rindex("}", 0, at) + 1
    end = STYLE_CSS.index("}", at) + 1
    return STYLE_CSS[start:end]


def test_no_skin_paints_an_opaque_surface_on_the_empty_state():
    """A 52px black band sat between the empty chat and the composer.

    `.empty-state` is `flex:1` inside `.messages`, so it fills the scroller --
    but only down to `.messages-inner`, which contributes its own 52px of
    padding even with no messages in it. The geist-contrast skin painted
    `.empty-state` an opaque `var(--surface)` (#0a0a0a), while `.messages` and
    `.messages-inner` stayed transparent over `#mainChat`'s `var(--bg)`
    (#000000). Measured in the running app at 2560x1440 on that skin:
    `#emptyState` ended at y=1273.6, `.composer-wrap` began at y=1325.6, and the
    52px between them painted pure black across the full 2211px width of the
    chat area -- the chat background visibly stopping short of the composer with
    a black gap underneath it.

    The same skin leaves a chat that *has* messages on `var(--bg)`, so the
    surface on the empty state was also making a new chat a different colour
    from a used one. Dropping it fixes both: the empty state inherits the same
    background as the transcript, and there is no inner element whose edge can
    become a seam.
    """
    surface_rule = _skin_rule_containing(
        ':root[data-skin="geist-contrast"] .composer-box{background:var(--surface)!important;'
    )
    assert ".empty-state," not in surface_rule, (
        "an opaque background on .empty-state stops at the empty state's own "
        "edge, leaving the rest of the scroller showing the shell colour"
    )
    # Nothing else may reintroduce it either: the empty state's only background
    # is the shared accent glow, which fades to transparent and so has no edge.
    assert (
        ".empty-state{background:radial-gradient(ellipse at 50% 20%,"
        "var(--accent-bg) 0%,transparent 60%);}" in STYLE_CSS
    )


def test_the_chat_scroller_stays_transparent_over_the_view_background():
    """The invariant the fix relies on.

    `#mainChat` is the one element that paints the chat area, and it is sized by
    the flex column, so it always reaches the composer. `.messages` and
    `.messages-inner` must stay transparent over it -- the moment either one
    takes an opaque colour, the chat surface is being painted by something that
    stops at its own content instead of at the bottom of the view.
    """
    assert ".main-view{flex:1;min-height:0;min-width:0;display:flex;flex-direction:column;background:var(--bg);}" in STYLE_CSS
    scroller = STYLE_CSS[STYLE_CSS.index("  .messages{"):]
    scroller = scroller[:scroller.index("}")]
    assert "background" not in scroller
    inner = STYLE_CSS[STYLE_CSS.index("  .messages-inner{"):]
    inner = inner[:inner.index("}")]
    assert "background" not in inner
