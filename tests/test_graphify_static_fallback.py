"""Regression tests for /graphify-projects/* static serving."""

from pathlib import Path
from unittest.mock import MagicMock


def test_graphify_static_fallback_serves_file(tmp_path):
    from api import config
    from api.graphify_static import graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        graph_root = tmp_path / "graphify-out" / "projects"
        graph_root.mkdir(parents=True)
        (graph_root / "workspace-graph-map.json").write_text(
            '{"projects": {}}', encoding="utf-8"
        )

        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/workspace-graph-map.json"

        result = graphify_static_fallback(None, handler, parsed)
        assert result is True
        handler.send_response.assert_called_once_with(200)
        handler.wfile.write.assert_called_once()
        written = handler.wfile.write.call_args[0][0]
        assert b'"projects"' in written
    finally:
        config.REPO_ROOT = original


def test_graphify_static_fallback_serves_interactive_graph_html_as_html(tmp_path):
    from api import config
    from api.graphify_static import _GRAPHIFY_CSP, _GRAPHIFY_CSP_REPORT_ONLY, graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        graph_root = tmp_path / "graphify-out" / "projects" / "demo"
        graph_root.mkdir(parents=True)
        (graph_root / "graph.html").write_text("<!doctype html>", encoding="utf-8")

        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/demo/graph.html"

        assert graphify_static_fallback(None, handler, parsed) is True
        handler.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")
        handler.send_header.assert_any_call("Cache-Control", "no-store")
        handler.send_header.assert_any_call("Content-Security-Policy", _GRAPHIFY_CSP)
        assert handler._csp_report_only_policy == _GRAPHIFY_CSP_REPORT_ONLY
        assert "connect-src 'self' https://unpkg.com" in _GRAPHIFY_CSP
        written = handler.wfile.write.call_args[0][0]
        assert b"hermes-graph-theme" in written
        assert b"graph-sidebar-toggle" in written
        assert b"ResizeObserver" in written
    finally:
        config.REPO_ROOT = original


def test_graphify_html_bridge_applies_initial_theme_and_section_controls(tmp_path):
    """An embedded graph must not flash Graphify defaults or trap its detail panes open."""
    from api import config
    from api.graphify_static import graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        graph_root = tmp_path / "graphify-out" / "projects" / "demo"
        graph_root.mkdir(parents=True)
        (graph_root / "graph.html").write_text(
            "<head></head><body><div id=\"graph\"></div><div id=\"sidebar\">"
            "<input id=\"search\"><div id=\"info-panel\"><h3>Node Info</h3></div>"
            "<div id=\"legend-wrap\"><h3>Communities</h3></div></div></body>",
            encoding="utf-8",
        )
        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/demo/graph.html"

        assert graphify_static_fallback(None, handler, parsed) is True
        written = handler.wfile.write.call_args[0][0]
        assert b"hermes_graph_theme" in written
        assert b"#search{background:var(--graph-bg)" in written
        assert b"graph-section-toggle" in written
        assert b"info-panel" in written and b"legend-wrap" in written
        assert b"font-family:var(--graph-font-ui)" in written
        assert b"place-content:center!important" in written
        assert b"hermes-graph-ready" in written
        assert b"document.body.appendChild(button)" in written
        assert b"transition:right .2s" in written
        assert b"right:12px!important;top:12px!important" in written
        assert b"#search-wrap{padding-right:51px!important}" in written
        assert b"flex-basis .36s cubic-bezier(.22,1,.36,1)" in written
        assert b"@media(prefers-reduced-motion:reduce){#sidebar{transition:none!important}}" in written
        assert b"flex:0 0 var(--hermes-sidebar-width)!important" in written
        assert b"#search{height:31px!important;min-height:31px!important" in written
        assert b"width:31px!important;height:31px!important;display:grid!important" in written
    finally:
        config.REPO_ROOT = original


def test_graphify_html_bridge_disables_vis_network_improved_layout(tmp_path):
    from api import config
    from api.graphify_static import graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        graph_root = tmp_path / "graphify-out" / "projects" / "demo"
        graph_root.mkdir(parents=True)
        (graph_root / "graph.html").write_text(
            "<head></head><body><script>const network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, { physics: {} });</script></body>",
            encoding="utf-8",
        )
        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/demo/graph.html"

        assert graphify_static_fallback(None, handler, parsed) is True
        written = handler.wfile.write.call_args[0][0]
        assert b"layout: { improvedLayout: false }" in written
    finally:
        config.REPO_ROOT = original


def test_graphify_static_fallback_404_outside_root(tmp_path):
    from api import config
    from api.graphify_static import graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        graph_root = tmp_path / "graphify-out" / "projects"
        graph_root.mkdir(parents=True)

        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/../workspace-graph-map.json"

        result = graphify_static_fallback(None, handler, parsed)
        assert result is True
        handler.send_response.assert_called_once_with(404)
    finally:
        config.REPO_ROOT = original


def test_a_missing_workspace_graph_map_reads_as_no_graphs_not_an_error(tmp_path):
    from api import config
    from api.graphify_static import graphify_static_fallback

    original = config.REPO_ROOT
    config.REPO_ROOT = tmp_path
    try:
        handler = MagicMock()
        parsed = MagicMock()
        parsed.path = "/graphify-projects/workspace-graph-map.json"
        assert graphify_static_fallback(None, handler, parsed) is True
        handler.send_response.assert_called_once_with(200)
        assert handler.wfile.write.call_args[0][0] == b"{}"

        other = MagicMock()
        parsed.path = "/graphify-projects/missing.html"
        graphify_static_fallback(None, other, parsed)
        other.send_response.assert_called_once_with(404)  # only the optional index is softened
    finally:
        config.REPO_ROOT = original
