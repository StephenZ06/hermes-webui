"""A source/Docker build with no Git metadata must still bust static assets."""
from pathlib import Path

from api import routes


def test_unknown_runtime_version_uses_static_content_fingerprint(tmp_path, monkeypatch):
    static_root = tmp_path / "static"
    static_root.mkdir()
    for name, content in {
        "index.html": "shell",
        "style.css": "first-style",
        "ui.js": "first-ui",
        "sw.js": "first-sw",
    }.items():
        (static_root / name).write_text(content, encoding="utf-8")
    office_root = static_root / "office"
    office_root.mkdir()
    office_builder = office_root / "builders.js"
    office_builder.write_text("first-office-builder", encoding="utf-8")

    # Patch the modules the code under test reads at call time (by dotted
    # path / via routes): another test may have reloaded api.updates, leaving
    # this file's import-time references stale.
    monkeypatch.setattr("api.updates.WEBUI_VERSION", "unknown")
    monkeypatch.setattr(routes.api_config, "get_static_root", lambda: static_root)

    first = routes._static_asset_version_token()
    (static_root / "ui.js").write_text("changed-ui", encoding="utf-8")
    second = routes._static_asset_version_token()
    office_builder.write_text("changed-office-builder", encoding="utf-8")
    third = routes._static_asset_version_token()

    assert first.startswith("local-")
    assert second.startswith("local-")
    assert first != second
    assert second != third
