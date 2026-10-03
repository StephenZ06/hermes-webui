"""Bundled page-navigation icon assets mirror the user-provided icon folder."""
import hashlib
import pathlib


REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
SERVICE_WORKER = (REPO / "static" / "sw.js").read_text(encoding="utf-8")

ICON_MAP = {
    "tasks": "Tasks.png",
    "agents": "Personas.png",
    "profiles": "Profiles.png",
    "memory": "Memory.png",
    "knowledge": "Knowledge.png",
    "skills": "Skills.png",
    "workspaces": "Spaces.png",
    "notes": "Work Hub.png",
    "insights": "Insights.png",
    "logs": "Logs.png",
    "audit": "Activity.png",
}


def test_page_navigation_icons_are_replaced_in_desktop_and_mobile():
    for panel, source_name in ICON_MAP.items():
        class_name = f'page-nav-mark page-nav-mark--{panel}'
        asset_name = f'nav-{panel}-mark.png'
        source = REPO / "icons" / source_name
        deployed = REPO / "static" / asset_name
        assert INDEX.count(f'class="{class_name}"') == 2
        assert deployed.is_file()
        # icons/ is the local, untracked design-source folder. When it is
        # present, the shipped copy must match it; a clean checkout or CI
        # verifies the shipped assets and their wiring only.
        if source.parent.is_dir():
            assert source.is_file(), f"{source_name} missing from the icons/ source folder"
            assert hashlib.sha256(deployed.read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()
        assert f'mask-image:url("{asset_name}")' in CSS
        assert f'-webkit-mask-image:url("{asset_name}")' in CSS
        assert f"'./static/{asset_name}'," in SERVICE_WORKER
