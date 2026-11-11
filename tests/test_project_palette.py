"""Project builder colour palette: what the planner or the wizard sends is
validated, a missing dark set is derived from the light one, and the palette is
written into the new project's docs as CSS tokens for both themes."""

import json

from api import project_palette as pal
from api import project_starter_agent as agent
from api import project_toolkit as tk

LIGHT = {"bg": "#FFF8F1", "surface": "#ffffff", "text": "#2b1d14", "primary": "#B5522B", "accent": "#2f7d6d"}
DARK = {"bg": "#17110d", "surface": "#221a15", "text": "#f5ebe2", "primary": "#e58a5f", "accent": "#5cc2ab"}


def test_a_full_palette_is_kept_with_lower_case_hex():
    out = pal.normalize_palette({"name": "Terracotta", "source": "recommended", "light": LIGHT, "dark": DARK,
                                 "why": "Warm clay suits a family bakery."})
    assert out["name"] == "Terracotta" and out["source"] == "recommended"
    assert out["light"]["bg"] == "#fff8f1" and out["light"]["primary"] == "#b5522b"
    assert out["dark"] == DARK
    assert out["why"] == "Warm clay suits a family bakery."


def test_short_hex_is_expanded_and_unknown_sources_become_custom():
    light = dict(LIGHT, bg="#fff")
    out = pal.normalize_palette({"light": light, "source": "magic"})
    assert out["light"]["bg"] == "#ffffff" and out["source"] == "custom"


def test_a_missing_or_broken_dark_set_is_derived_and_readable():
    out = pal.normalize_palette({"light": LIGHT, "dark": {"bg": "red"}})
    dark = out["dark"]
    assert set(dark) == set(pal.ROLES)
    assert pal.luminance(dark["bg"]) < 0.05 < pal.luminance(dark["text"])
    assert pal.contrast(dark["text"], dark["bg"]) >= 7
    assert pal.contrast(dark["primary"], dark["bg"]) >= 4.5


def test_invalid_palettes_are_dropped():
    assert pal.normalize_palette(None) is None
    assert pal.normalize_palette({"dark": DARK}) is None
    assert pal.normalize_palette({"light": dict(LIGHT, text="black")}) is None
    assert pal.normalize_palette({"light": dict(LIGHT, primary="#12345")}) is None
    assert pal.normalize_palette({"light": dict(LIGHT, accent="#abc; color:red")}) is None


def test_contrast_matches_the_wcag_formula():
    assert round(pal.contrast("#000000", "#ffffff"), 2) == 21.0
    assert round(pal.contrast("#777777", "#ffffff"), 2) == 4.48


def test_the_analysis_look_carries_a_palette_only_when_it_is_valid():
    raw = {"complete": True, "summary": "ok", "questions": [],
           "look": {"style": "playful", "motion": "subtle", "palette": {"name": "Clay", "light": LIGHT, "why": "Warm."}}}
    look = agent.parse_analysis(json.dumps(raw))["look"]
    assert look["palette"]["name"] == "Clay" and look["palette"]["source"] == "recommended"
    assert set(look["palette"]["dark"]) == set(pal.ROLES)
    raw["look"]["palette"] = {"light": {"bg": "nope"}}
    assert "palette" not in agent.parse_analysis(json.dumps(raw))["look"]


def test_the_analysis_prompt_asks_for_a_palette_for_both_themes():
    prompt = agent._ANALYSIS_PROMPT
    assert '"palette"' in prompt and '"light"' in prompt and '"dark"' in prompt


def test_the_palette_is_written_into_the_ui_doc_as_tokens_for_both_themes(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "UI_UX.md").write_text("# UI\n", encoding="utf-8")
    toolkit = tk.normalize_toolkit({"look": {"style": "elegant", "motion": "subtle",
                                             "palette": {"name": "Terracotta", "source": "logo", "light": LIGHT, "dark": DARK}}},
                                   template="website", libraries_root=tmp_path / "libs", skill_names=set())
    tk.apply_toolkit(tmp_path, toolkit, libraries_root=tmp_path / "libs")
    doc = (tmp_path / "docs" / "UI_UX.md").read_text(encoding="utf-8")
    assert "Colour palette: **Terracotta** (from the logo)" in doc
    assert "--color-primary: #b5522b;" in doc
    assert "@media (prefers-color-scheme: dark)" in doc and "--color-primary: #e58a5f;" in doc
    assert "[data-theme=\"dark\"]" in doc
