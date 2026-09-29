"""Interactive motion stays cancellable and compositor-friendly."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_motion_ui_exposes_named_interruption_and_transform_only_spring():
    source = (ROOT / "static/motion-ui.js").read_text(encoding="utf-8")
    spring = source.split("function springTransform", 1)[1].split("function slidePanel", 1)[0]

    assert "function interrupt(name)" in source
    assert "interrupt," in source
    assert "const keyframes = { transform:" in spring
    for property_name in ("height:", "width:", "top:", "left:", "margin:"):
        assert property_name not in spring
