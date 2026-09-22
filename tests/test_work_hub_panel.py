"""Static contracts for the native Work Hub screen."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_work_hub_uses_native_panel_and_curated_mx_icons():
    page = read("static/index.html")
    script = read("static/work-hub.js")

    assert 'id="panelNotes"' in page
    assert "Work Hub" in page
    assert "static/work-hub.js" in page
    assert "mx-icons" in script
    assert "react" not in script.lower()


def test_work_hub_has_reduced_motion_and_narrow_drawer_rules():
    css = read("static/style.css")

    assert ".work-hub" in css
    assert "prefers-reduced-motion" in css
    assert "@media" in css


def test_work_hub_script_parses_in_supported_node_runtime():
    result = subprocess.run(
        ["node", "--check", str(ROOT / "static/work-hub.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_work_hub_post_bodies_use_the_shared_json_api_contract():
    script = read("static/work-hub.js")

    assert "body: JSON.stringify({ item:" in script
    assert "body: JSON.stringify({ item_id:" in script
