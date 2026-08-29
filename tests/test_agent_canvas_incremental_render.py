"""Agent Canvas must patch its tree in place, not rebuild it on every event.

``scheduleRender()`` runs on every subagent spawn/tool/complete event and on
every reconcile tick. The old ``renderTree()`` wiped ``_treeEl.innerHTML`` and
re-created every card, which restarted each card's pop-in, the status dot's
pulse and the running card's orbit. Measured in a browser over eight tool
calls: 27 ``animationstart`` events per card against 2 ``animationend`` —
entrances that visibly began and never finished. Same defect in the activity
feed, which re-wrote every row.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_tree_patches_in_place_when_the_shape_is_unchanged():
    js = read("static/agent-canvas.js")
    assert "function treeSignature(){" in js
    assert "function patchTree(){" in js
    assert "if(signature === _lastTreeSignature && !_suppressRootPopOnce && patchTree()) return;" in js


def test_signature_covers_shape_only_so_status_changes_do_not_rebuild():
    """Status, tool counts and durations change on almost every event; if they
    were part of the signature every event would still rebuild the tree."""
    js = read("static/agent-canvas.js")
    body = js.split("function treeSignature(){", 1)[1].split("\n  }", 1)[0]
    assert "subagent_id" in body and "parent_id" in body
    for churny in ("status", "toolCount", "durationSeconds", "inputTokens"):
        assert churny not in body, f"{churny} must not be part of the tree signature"


def test_patch_failure_falls_back_to_a_rebuild():
    """A half-updated tree is worse than a rebuilt one, so patchTree() reports
    when the DOM and the node map have drifted apart."""
    js = read("static/agent-canvas.js")
    body = js.split("function patchTree(){", 1)[1].split("\n  }", 1)[0]
    assert "if(!node) return false;" in body
    assert "return true;" in body


def test_card_build_and_update_share_one_source_of_truth():
    """buildCard() renders the skeleton then defers to updateCardEl(), so a
    field can never render one way on build and another on update."""
    js = read("static/agent-canvas.js")
    assert "const CARD_SKELETON = `" in js
    assert "function updateCardEl(card, node, ctx){" in js
    assert "card.innerHTML = CARD_SKELETON;\n    updateCardEl(card, node, ctx);" in js


def test_rebuild_animates_only_the_nodes_that_were_not_on_screen():
    js = read("static/agent-canvas.js")
    assert "const alreadyOnScreen = !!(ctx && ctx.seen && ctx.seen.has(node.subagent_id));" in js
    assert "if((isRoot && _suppressRootPopOnce) || alreadyOnScreen){" in js
    # A children row only replays its trunk/cluster reveal for a real arrival.
    assert "const anyNew = !(ctx && ctx.seen) || kids.some(k => !ctx.seen.has(k.subagent_id));" in js


def test_reveal_suppression_is_a_class_so_reduced_motion_still_wins():
    """An inline animation would outrank the prefers-reduced-motion rules."""
    js = read("static/agent-canvas.js")
    css = read("static/style.css")
    assert "(anyNew ? '' : ' no-reveal')" in js
    assert ".agent-canvas-trunk.no-reveal{animation:none;}" in css
    assert ".agent-canvas-trunk.no-reveal.is-flowing{animation:agent-canvas-flow .6s linear infinite;}" in css
    marker = "@media (prefers-reduced-motion:reduce){\n  .agent-canvas-trunk{"
    block = css.split(marker, 1)[1].split("\n}", 1)[0]
    assert ".agent-canvas-trunk.no-reveal.is-flowing{animation:none" in block, (
        "the reduced-motion block must also neutralise .no-reveal.is-flowing, "
        "which is more specific than its plain .is-flowing rule"
    )


def test_empty_card_slots_are_actually_hidden():
    """The slots are always present so an update never inserts or removes a
    child — but each carries its own display value, which outranks [hidden]."""
    css = read("static/style.css")
    assert (
        ".agent-canvas-card-sub[hidden],\n"
        ".agent-canvas-card-stats[hidden],\n"
        ".agent-canvas-card-terminal[hidden]{display:none;}"
    ) in css


def test_feed_prepends_new_rows_instead_of_rewriting_the_list():
    js = read("static/agent-canvas.js")
    assert "function feedItemHtml(entry){" in js
    assert "_feedEl.insertAdjacentHTML('afterbegin', feedItemHtml(fresh[i]));" in js
    assert "while(_feedEl.children.length > FEED_MAX) _feedEl.lastElementChild.remove();" in js
    # Entries need a stable ordering key for "which of these are new".
    assert "id: ++_feedSeq" in js
    assert "if(newestId === _lastFeedTopId) return;" in js


def test_incremental_state_is_dropped_on_every_session_or_mode_switch():
    """Nothing on screen is reusable across sessions, so the bookkeeping has to
    reset or the next tree would silently skip its entrance."""
    js = read("static/agent-canvas.js")
    for fn in ("function reset(){", "function returnToLiveView(){", "function showHistoricalTree(parentEntry){"):
        body = js.split(fn, 1)[1][:900]
        assert "_lastTreeSignature = '';" in body, f"{fn} must clear the tree signature"
        assert "_renderedCardIds = new Set();" in body, f"{fn} must clear the rendered-id set"
        assert "_lastFeedTopId = null;" in body, f"{fn} must clear the feed marker"
