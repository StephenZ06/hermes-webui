"""Project builder Customize step: typography, button and surface choices are
kept only when known, and reach the new project's UI doc as guidance and CSS
tokens."""

from api import project_look as pl
from api import project_starter_agent as agent
from api import project_toolkit as tk


def test_only_known_custom_choices_are_kept():
    raw = {"font": "serif", "scale": "large", "btnShape": "pill", "btnFill": "glitter", "btnHover": "lift",
           "corners": "round", "depth": "glass", "density": "airy", "evil": "<script>"}
    assert pl.normalize_custom(raw) == {"font": "serif", "scale": "large", "btnShape": "pill", "btnHover": "lift",
                                        "corners": "round", "depth": "glass", "density": "airy"}
    assert pl.normalize_custom({"font": "comic"}) is None
    assert pl.normalize_custom("serif") is None


def test_the_look_carries_custom_choices_into_the_ui_doc(tmp_path):
    look = agent.parse_look({"style": "playful", "motion": "subtle", "framework": "react",
                             "custom": {"font": "geometric", "btnShape": "pill", "btnFill": "tint", "corners": "round",
                                        "density": "compact", "nonsense": 1}}, palette_source="custom")
    assert look["custom"] == {"font": "geometric", "btnShape": "pill", "btnFill": "tint", "corners": "round", "density": "compact"}
    project = tmp_path / "site"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "UI_UX.md").write_text("# UI and UX\n")
    tk.apply_toolkit(project, {"look": look, "skills": [], "components": []}, libraries_root=tmp_path)
    ui = (project / "docs" / "UI_UX.md").read_text()
    assert "Button shape: **Pill** (fully round ends (999px))" in ui
    assert "Button fill: **Soft tint**" in ui and "Typeface: **Geometric**" in ui
    assert "--radius-button: 999px;" in ui and "--radius-surface: 16px;" in ui and "--space-unit: 4px;" in ui
    # Nothing chosen, nothing written.
    assert "custom" not in agent.parse_look({"style": "bold", "motion": "none"})
