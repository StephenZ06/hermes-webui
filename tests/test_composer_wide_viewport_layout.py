"""Composer chrome on wide desktop viewports.

Two defects live in the composer footer of the chat page, both only visible
once the window is large: the workspace chip is positioned by a different
mechanism than every chip beside it, and the composer box is *widened* on
ultrawide displays by a rule whose own comment says it caps the width.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def _rule(selector):
    """Return the declaration block that follows `selector` verbatim."""
    start = STYLE_CSS.index(selector)
    body = STYLE_CSS[start + len(selector):]
    return body[:body.index("}")]


# ── Workspace chip vertical alignment ────────────────────────────────────────

def test_every_composer_chip_wrapper_centres_its_chip_the_same_way():
    """The workspace pill rode a text baseline while its neighbours did not.

    `.composer-left` is a flex row, but what it lays out are the *wrappers*, not
    the chips. `.composer-ws-wrap` was the only wrapper that was itself a flex
    container, so the workspace group was centred by flexbox. Every other
    wrapper (profile, model, reasoning, toolsets) was a plain block, which makes
    its `inline-flex` chip an inline-level box positioned on the wrapper's text
    baseline, with the wrapper's height coming from a line box that includes the
    inherited 22.4px strut.

    Two positioning models side by side in one row agree only while the strut
    stays shorter than the chips. Raise the inherited line-height and they
    diverge: measured in headless Chromium at 2560x1440, `.composer-footer`
    with `line-height:2.6` puts the workspace group's centre at y=1311.55 and
    the profile and model chips at y=1309.61 -- the workspace pill sitting
    ~2px below the chips on either side of it, which is exactly the reported
    symptom. Font metrics move the same lever, which is why the drift shows up
    on one machine's font stack and not another's.

    Centring every wrapper with flexbox removes the baseline from the
    calculation entirely, so all chips share one axis whatever the font does.
    """
    shared = _rule(
        "  .composer-profile-wrap,\n"
        "  .composer-ws-wrap,\n"
        "  .composer-reasoning-wrap,\n"
        "  .composer-toolsets-wrap,\n"
        "  .composer-model-wrap{"
    )
    assert "display:flex" in shared and "align-items:center" in shared, (
        "every chip wrapper must centre its chip with flexbox; a block wrapper "
        "positions its inline-flex chip on the inherited text baseline instead"
    )
    # The workspace wrapper keeps only what is genuinely its own.
    assert ".composer-ws-wrap{gap:4px;}" in STYLE_CSS
    assert ".composer-ws-wrap{display:flex;align-items:center;gap:4px;}" not in STYLE_CSS, (
        "the workspace wrapper must not redeclare the shared centring, or the "
        "next edit to one of them silently splits the row in two again"
    )


def test_the_toolsets_wrapper_is_revealed_as_a_flex_wrapper_like_its_siblings():
    """The container query that reveals the toolsets chip must not undo the fix.

    `.composer-toolsets-wrap` is `display:none` until the composer-footer
    container is wide enough, and the reveal rule restates a display value. If
    that value stays `block`, the one chip that only exists on wide viewports is
    also the one chip that goes back to riding the text baseline -- on exactly
    the large monitors this change is about.
    """
    reveal = _rule("@container composer-footer (min-width: 1100px) {\n    .composer-toolsets-wrap{")
    assert "display:flex" in reveal, (
        "revealing the toolsets wrap as a block re-introduces baseline "
        "positioning for that chip alone"
    )


def test_the_workspace_chip_markup_still_pairs_a_files_button_with_a_label():
    """Guards the assumption the alignment fix is written against.

    The workspace control is two buttons inside one bordered pill, which is why
    its wrapper had a bespoke layout in the first place. If that collapses to a
    single button the shared wrapper rule still holds, but the `gap` on
    `.composer-ws-wrap` no longer has anything to space.
    """
    assert 'class="composer-workspace-group ws-chip"' in INDEX_HTML
    assert 'class="composer-workspace-files-btn"' in INDEX_HTML
    assert 'class="composer-workspace-label" id="composerWorkspaceLabel"' in INDEX_HTML


# ── Composer width on ultrawide displays ─────────────────────────────────────

def test_the_composer_and_its_selection_rail_share_one_width_token():
    """Two selectors carried the same width ladder, copied character for character.

    `.composer-box` and `.composer-selection-chips` sit directly on top of each
    other and must line up, yet each spelled out `clamp(780px,60vw,1100px)` and
    each carried its own ultrawide override. Editing one and not the other is a
    silent misalignment, so the ladder belongs to a token both read.
    """
    assert "--composer-max:" in STYLE_CSS, "the composer width ladder needs one definition"
    assert "max-width:var(--composer-max)" in _rule("  .composer-box{")
    assert "max-width:var(--composer-max)" in _rule(".composer-selection-chips{")
    assert "clamp(780px,60vw,1100px)" in _rule(":root{--composer-max:")


def test_ultrawide_viewports_do_not_stretch_the_composer_to_1600px():
    """A rule that said "cap" grew the composer by 500px on a big monitor.

    `@media (min-width:1600px)` set `.composer-box` and
    `.composer-selection-chips` to `max-width:1600px`, described in its own
    comment and changelog entry as keeping the chip cluster "anchored against a
    content-sized boundary instead of stretching". The base ladder already stops
    at 1100px, so the rule only ever ran in the widening direction: measured in
    the running app at 2560x1440, the composer box was 1600px wide against a
    conversation column of 860px, leaving ~1100px of dead space between the chip
    cluster and the send button and pulling the composer badly out of line with
    the text it belongs to.
    """
    assert "max-width:1600px" not in STYLE_CSS, (
        "nothing in the composer should stretch to 1600px on ultrawide"
    )
    assert "@media (min-width:1600px){:root{--composer-max:1200px;}}" in STYLE_CSS
    # The conversation column is the thing the composer has to stay near; if its
    # ceiling ever moves, this pairing is where the composer has to follow.
    assert "--msg-max: 780px;" in STYLE_CSS
    assert ".messages-inner { max-width: calc(var(--msg-max) + 80px); }" in STYLE_CSS


def test_the_ultrawide_composer_still_clears_the_toolsets_container_threshold():
    """Narrowing the composer can delete a chip, not just move it.

    The session-toolsets chip is revealed by a container query on
    `.composer-footer` at 1100px, and `.composer-footer` is 2px narrower than
    `.composer-box` because of the box's border. The base ladder tops out at
    1100px, i.e. a 1098px container, so the chip has only ever been reachable
    through the ultrawide step. Taking that step below 1102px does not make the
    chip narrower, it makes it permanently invisible: measured in the running
    app at 2560x1440, an ultrawide value of 1100px left `.composer-toolsets-wrap`
    at `display:none` with a zero-size box.
    """
    step = _rule("@media (min-width:1600px){:root{--composer-max:")
    ultrawide = int(step.split("px")[0])
    threshold = int(
        _rule("@container composer-footer (min-width: ").split("px")[0]
    )
    assert ultrawide >= threshold + 2, (
        f"an ultrawide composer of {ultrawide}px leaves a "
        f"{ultrawide - 2}px footer container, under the {threshold}px the "
        "toolsets chip needs -- the chip would never render"
    )
