from pathlib import Path


def test_startup_script_is_not_redundantly_preloaded():
    """The immediate parser-blocking script gets no useful preload head start."""
    source = (Path(__file__).parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    assert 'rel="preload" href="static/pwa-startup.js' not in source
