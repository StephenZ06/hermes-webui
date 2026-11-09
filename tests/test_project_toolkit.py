"""Project builder toolkit: the look recommended from the brief, skill
suggestions, and what the wizard writes into a new project."""

import json

import pytest

from api import project_starter_agent as agent
from api import project_toolkit as tk


def test_analysis_keeps_a_valid_look_and_drops_an_invalid_one():
    raw = {"complete": True, "summary": "ok", "questions": [],
           "look": {"style": "Elegant", "motion": "subtle", "framework": "react", "tailwind": True,
                    "why": "A law firm needs calm trust."}}
    out = agent.parse_analysis(json.dumps(raw))
    assert out["look"] == {"style": "elegant", "motion": "subtle", "framework": "react", "tailwind": True,
                           "why": "A law firm needs calm trust."}
    raw["look"]["style"] = "shiny"
    assert "look" not in agent.parse_analysis(json.dumps(raw))
    raw["look"] = {"style": "bold", "motion": "expressive", "framework": "cobol"}
    assert agent.parse_analysis(json.dumps(raw))["look"]["framework"] == ""
    del raw["look"]
    assert "look" not in agent.parse_analysis(json.dumps(raw))


def test_the_analysis_prompt_asks_for_the_look():
    assert '"look"' in agent._ANALYSIS_PROMPT and "minimal" in agent._ANALYSIS_PROMPT


def test_visual_templates_and_their_platforms():
    assert tk.is_visual("website") and tk.is_visual("ios") and not tk.is_visual("cli")
    assert tk.platform_for("website", "react") == "web"
    assert tk.platform_for("ios", "swiftui") == "ios"
    assert tk.platform_for("ios", "react-native") == "react-native"
    assert tk.platform_for("android", "flutter") == "flutter"
    assert tk.default_framework("android") == "compose"


SKILLS = [
    {"name": "seo-audit", "category": "marketing", "description": "Check pages for search engine optimisation."},
    {"name": "ui-polish", "category": "design", "description": "Refine UI spacing, type and colour."},
    {"name": "pdf", "category": "documents", "description": "Read and fill PDF forms."},
    {"name": "rust-cli", "category": "dev", "description": "Command-line tools in Rust."},
]


def test_skill_suggestions_follow_the_template_and_the_brief():
    out = tk.suggest_skills(SKILLS, template="website", brief="A law firm site that ranks well in search")
    names = [s["name"] for s in out]
    assert names[:2] == ["seo-audit", "ui-polish"]
    assert [s["recommended"] for s in out[:2]] == [True, True]
    assert {s["name"]: s["recommended"] for s in out}["pdf"] is False
    cli = tk.suggest_skills(SKILLS, template="cli", brief="a small tool")
    assert cli[0]["name"] == "rust-cli" and cli[0]["recommended"] is True


LIB = """---
name: Calm UI
source: https://github.com/x/calm
license: MIT
kind: copy-paste
frameworks: [react]
tailwind: false
install: ""
---
"""
FADE = """---
name: Fade
role: text-effect
style: [elegant]
motion: subtle
platform: [web]
files: [src/fade.tsx, ../../escape.txt]
---
"""


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "libraries"
    d = root / "calm-ui"
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text(LIB)
    (d / "components" / "fade.md").write_text(FADE)
    (d / "source" / "src").mkdir(parents=True)
    (d / "source" / "src" / "fade.tsx").write_text("export const Fade = () => null")
    (tmp_path / "escape.txt").write_text("secret")
    return root


def test_toolkit_is_validated_against_the_catalog_and_the_installed_skills(catalog):
    raw = {"look": {"style": "elegant", "motion": "subtle", "framework": "react", "tailwind": False, "why": "calm"},
           "skills": ["ui-polish", "not-installed"],
           "components": [{"library": "calm-ui", "slug": "fade"}, {"library": "calm-ui", "slug": "nope"},
                          {"library": "../x", "slug": "y"}]}
    out = tk.normalize_toolkit(raw, template="website", libraries_root=catalog, skill_names={"ui-polish", "pdf"})
    assert out["look"]["style"] == "elegant"
    assert out["skills"] == ["ui-polish"]
    assert [(c["library"], c["slug"]) for c in out["components"]] == [("calm-ui", "fade")]
    assert tk.normalize_toolkit(None, template="cli", libraries_root=catalog, skill_names=set()) is None


def test_non_visual_templates_keep_skills_but_no_look_or_components(catalog):
    raw = {"look": {"style": "bold", "motion": "none"}, "skills": ["pdf"], "components": [{"library": "calm-ui", "slug": "fade"}]}
    out = tk.normalize_toolkit(raw, template="cli", libraries_root=catalog, skill_names={"pdf"})
    assert out == {"look": None, "skills": ["pdf"], "components": []}


def test_apply_writes_marked_sections_and_copies_only_safe_component_files(catalog, tmp_path):
    project = tmp_path / "site"
    (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Agent instructions\n\n## Before any change\n\nRead things.\n")
    (project / "docs" / "UI_UX.md").write_text("# UI and UX\n\nTBD\n")
    toolkit = tk.normalize_toolkit(
        {"look": {"style": "elegant", "motion": "subtle", "framework": "react", "tailwind": False, "why": "calm"},
         "skills": ["ui-polish"], "components": [{"library": "calm-ui", "slug": "fade"}]},
        template="website", libraries_root=catalog, skill_names={"ui-polish"})
    written = tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    agents = (project / "AGENTS.md").read_text()
    ui = (project / "docs" / "UI_UX.md").read_text()
    assert "<!-- hermes:toolkit:begin -->" in agents and "load the `ui-polish` skill" in agents
    assert "Use only the approved components" in agents
    assert "## Look and feel" in ui and "Elegant" in ui and "calm" in ui
    assert "## Approved components" in ui and "Fade" in ui and "vendor/ui/calm-ui/src/fade.tsx" in ui
    assert (project / "vendor" / "ui" / "calm-ui" / "src" / "fade.tsx").read_text().startswith("export")
    assert not (project / "vendor" / "ui" / "escape.txt").exists()
    assert not list(project.rglob("escape.txt"))
    assert "vendor/ui/calm-ui/src/fade.tsx" in written
    # Applying again does not duplicate the sections.
    tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    assert (project / "AGENTS.md").read_text().count("hermes:toolkit:begin") == 1


def test_apply_without_a_ui_doc_puts_the_look_in_agents(catalog, tmp_path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Agent instructions\n")
    toolkit = {"look": {"style": "bold", "motion": "expressive", "framework": "react", "tailwind": True, "why": ""},
               "skills": [], "components": []}
    tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    assert "Bold" in (project / "AGENTS.md").read_text()


def test_kickoff_message_names_the_approved_pieces_and_local_installs():
    toolkit = {"look": {"style": "elegant", "motion": "subtle", "framework": "react", "tailwind": False, "why": ""},
               "skills": ["ui-polish"], "components": [{"library": "calm-ui", "slug": "fade", "name": "Fade"}]}
    text = tk.kickoff_message("Lex & Co", "website", toolkit)
    assert "version 1" in text and "Lex & Co" in text
    assert "inside the project" in text and "docs/UI_UX.md" in text
    assert "ECC_HANDOFF" in text and "preview" in text
