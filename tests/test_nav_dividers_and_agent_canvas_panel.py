"""Regression tests for two nav-rearrangement follow-up fixes:

1. The rail/sidebar-nav group dividers reused `.sidebar-divider`, a class
   built for a plain block-level context. Inside `.rail` (flex column,
   align-items:center) an empty childless div shrinks to ~0 width, so the
   `border-top` line never renders -- but `padding-top`/`margin-top` still
   consume vertical space, producing an invisible "divider" that reads as
   a plain gap. Dedicated `.rail-divider`/`.sidebar-nav-divider` classes
   fix this with an explicit width instead of relying on shrink-to-content.

2. #panelAgentCanvas (the wide-sidebar panel-view shown when Agent Canvas
   is the active main-view panel) didn't exist at all, so switchPanel()'s
   `$('panel'+capitalize(name))` lookup returned null and the sidebar area
   went fully blank for that panel.

3. This app has a persistent customizable tab-order feature
   (localStorage 'hermes-webui-tab-order', applied via _applyTabOrder() on
   every boot). It re-sequences [data-panel] buttons with insertBefore --
   but the divider divs have no data-panel attribute, so any saved order
   (even a stale one from before this nav rearrangement) left them
   stranded wherever the static HTML placed them while the real buttons
   moved elsewhere, bunching all 3 dividers right after Chat. Each divider
   now carries data-after-panel="<tab>" and _applyTabOrder() re-anchors it
   immediately after that tab on every call.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
PANELS_JS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")


def test_rail_dividers_use_dedicated_class_not_reused_sidebar_divider():
    rail_start = HTML.index('<nav class="rail"')
    rail_end = HTML.index("</nav>", rail_start)
    rail_block = HTML[rail_start:rail_end]
    assert rail_block.count('class="rail-divider"') == 3, (
        "rail should have exactly 3 group dividers using the dedicated class"
    )
    assert "sidebar-divider" not in rail_block, (
        "the rail must not reuse .sidebar-divider -- it shrinks to ~0 width "
        "in this align-items:center flex column, producing an invisible "
        "line plus dead vertical space instead of a visible divider"
    )


def test_sidebar_nav_dividers_use_dedicated_class():
    nav_start = HTML.index('<div class="sidebar-nav">')
    nav_end = HTML.index("</div>", HTML.rindex('data-panel="settings"', nav_start))
    nav_block = HTML[nav_start:nav_end]
    assert nav_block.count('class="sidebar-nav-divider"') == 3
    assert "sidebar-divider" not in nav_block


def test_rail_divider_css_has_explicit_width():
    start = CSS.index(".rail-divider{")
    end = CSS.index("}", start)
    rule = CSS[start:end]
    assert "width:" in rule and "width:0" not in rule, (
        ".rail-divider must set an explicit non-zero width -- .rail uses "
        "align-items:center, which shrinks an unsized empty div to 0 width"
    )


def test_sidebar_nav_divider_css_has_explicit_sizing():
    start = CSS.index(".sidebar-nav-divider{")
    end = CSS.index("}", start)
    rule = CSS[start:end]
    assert "width:" in rule


def test_panel_agent_canvas_exists_with_header():
    assert 'id="panelAgentCanvas"' in HTML, (
        "switchPanel() looks up $('panel'+capitalize(name)) for the active "
        "panel -- without #panelAgentCanvas the sidebar area goes blank "
        "when Agent Canvas is the active main-view panel"
    )
    start = HTML.index('id="panelAgentCanvas"')
    end = HTML.index("</div>", HTML.index("</div>", start) + 1)
    block = HTML[start:end]
    assert "panel-head" in block
    assert "Agent Canvas" in block or "tab_agent_canvas" in block


def test_dividers_carry_anchor_panel_for_reorder_survival():
    expected_anchors = ["tasks", "skills", "workspaces"]
    for cls in ("rail-divider", "sidebar-nav-divider"):
        anchors = []
        for chunk in HTML.split(f'class="{cls}"')[1:]:
            tag = chunk[: chunk.index(">")]
            assert 'data-after-panel="' in tag, (
                f"every .{cls} element must carry data-after-panel, missing on: {tag}"
            )
            anchors.append(tag.split('data-after-panel="', 1)[1].split('"', 1)[0])
        assert anchors == expected_anchors, (
            f".{cls} elements must carry data-after-panel in order "
            f"{expected_anchors}, got {anchors}"
        )


def test_apply_tab_order_reanchors_dividers_after_moving_buttons():
    start = PANELS_JS.index("function _applyTabOrder(order){")
    end = PANELS_JS.index("\nfunction _applyTabVisibility(", start)
    body = PANELS_JS[start:end]
    move_idx = body.index("container.insertBefore(node,anchor||null)")
    divider_idx = body.index("container.querySelectorAll('[data-after-panel]')")
    assert divider_idx > move_idx, (
        "divider re-anchoring must run AFTER the button-move loop, using "
        "each anchor tab's final post-move position"
    )
    assert "container.insertBefore(divider,anchorNode.nextSibling)" in body, (
        "each divider must be re-inserted immediately after its "
        "data-after-panel tab's current DOM position"
    )
