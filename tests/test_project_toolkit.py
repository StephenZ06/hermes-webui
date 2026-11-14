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
    assert out == {"look": None, "skills": ["pdf"], "components": [], "needs": []}


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


def test_a_detailed_brief_outweighs_the_template_hints():
    skills = SKILLS + [{"name": "pdf-invoices", "category": "documents", "description": "Generate invoices as PDF."}]
    out = tk.suggest_skills(skills, template="website", brief="Clients download their invoices as PDF from the site.")
    by = {s["name"]: s for s in out}
    assert by["pdf-invoices"]["recommended"] and by["pdf-invoices"]["fit"] == ["invoices", "pdf"]
    assert out[0]["name"] == "pdf-invoices"


def test_needs_recommend_skills_the_brief_never_mentions():
    skills = SKILLS + [{"name": "auth-flows", "category": "security", "description": "Sign-up and login with verification codes."}]
    out = tk.suggest_skills(skills, template="web", brief="A physio clinic.", needs=["auth"])
    by = {s["name"]: s for s in out}
    assert by["auth-flows"]["recommended"] and by["auth-flows"]["needs"] == ["Sign-in"] and by["auth-flows"]["fit"] == []


def test_the_planner_returns_needs_from_the_known_list_only():
    raw = {"complete": True, "summary": "ok", "questions": [], "needs": ["auth", "scheduling", "teleport"]}
    assert agent.parse_analysis(json.dumps(raw))["needs"] == ["auth", "scheduling"]
    assert '"needs"' in agent._ANALYSIS_PROMPT and "{needs_list}" in agent._ANALYSIS_PROMPT


def test_a_template_default_stands_in_when_the_planner_names_no_needs():
    assert tk.resolve_needs("web", ["dashboard"]) == ["dashboard"]
    assert tk.resolve_needs("website", None) == ["marketing", "forms", "help"]
    assert tk.resolve_needs("cli", []) == []


GLOW = """---
name: Glow card
role: cards
style: [bold]
motion: subtle
platform: [web]
files: []
---
"""


def test_a_component_without_a_file_list_is_copied_from_the_librarys_registry(catalog, tmp_path):
    from api import library_catalog as lc
    lib = catalog / "calm-ui"
    (lib / "components" / "glow-card.md").write_text(GLOW)
    (lib / "source" / "src" / "components" / "glow").mkdir(parents=True)
    (lib / "source" / "src" / "components" / "glow" / "card.tsx").write_text("export const Glow = () => null")
    (lib / "source" / "public" / "r").mkdir(parents=True)
    # shadcn-style registry: paths are relative to src/; hostile entries are ignored.
    (lib / "source" / "public" / "r" / "glow-card.json").write_text(json.dumps({"files": [
        {"path": "components/glow/card.tsx"}, {"path": "../../../escape.txt"}, {"path": ""}, "junk"]}))
    assert lc.registry_files(lib / "source", "glow-card") == ["src/components/glow/card.tsx"]
    assert lc.registry_files(lib / "source", "missing") == []
    project = tmp_path / "site"
    (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Agent instructions\n")
    (project / "docs" / "UI_UX.md").write_text("# UI and UX\n")
    toolkit = tk.normalize_toolkit({"components": [{"library": "calm-ui", "slug": "glow-card"}], "skills": [],
                                    "look": {"style": "bold", "motion": "subtle"}},
                                   template="website", libraries_root=catalog, skill_names=set())
    written = tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    assert "vendor/ui/calm-ui/src/components/glow/card.tsx" in written
    assert "copied to `vendor/ui/calm-ui/src/components/glow/card.tsx`" in (project / "docs" / "UI_UX.md").read_text()
    assert not list(project.rglob("escape.txt"))


def test_what_the_app_needs_goes_into_the_product_doc_with_the_components_that_serve_it(catalog, tmp_path):
    project = tmp_path / "clinic"
    (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Agent instructions\n")
    (project / "docs" / "PRODUCT.md").write_text("# Product\n\nTBD\n")
    toolkit = tk.normalize_toolkit({"skills": [], "components": [{"library": "calm-ui", "slug": "fade"}],
                                    "needs": ["scheduling", "marketing", "nonsense"]},
                                   template="website", libraries_root=catalog, skill_names=set())
    assert toolkit["needs"] == ["scheduling", "marketing"]
    written = tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    product = (project / "docs" / "PRODUCT.md").read_text()
    assert "docs/PRODUCT.md" in written and "## What the app needs" in product and "<!-- hermes:toolkit:begin -->" in product
    assert "- Scheduling\n" in product and "- Landing page" in product
    # Without a product doc the list goes into AGENTS.md instead.
    other = tmp_path / "cli"
    other.mkdir()
    (other / "AGENTS.md").write_text("# Agent instructions\n")
    tk.apply_toolkit(other, {"look": None, "skills": [], "components": [], "needs": ["auth"]}, libraries_root=catalog)
    assert "- Sign-in" in (other / "AGENTS.md").read_text()


def test_a_registry_entry_named_in_another_word_order_still_counts(tmp_path):
    from api import library_catalog as lc
    src = tmp_path / "source"
    (src / "src" / "ui").mkdir(parents=True)
    (src / "src" / "ui" / "blobs.tsx").write_text("x")
    (src / "public" / "r").mkdir(parents=True)
    (src / "public" / "r" / "loaders-gooey-blobs.json").write_text(json.dumps({"files": [{"path": "ui/blobs.tsx"}]}))
    (src / "public" / "r" / "hover-img.json").write_text(json.dumps({"files": [{"path": "ui/blobs.tsx"}]}))
    assert lc.registry_files(src, "gooey-blobs-loaders") == ["src/ui/blobs.tsx"]
    assert lc.registry_files(src, "hover-image") == ["src/ui/blobs.tsx"]
    assert lc.registry_files(src, "gooey") == []


def test_a_component_with_no_code_in_the_source_says_so(catalog, tmp_path):
    lib = catalog / "calm-ui"
    (lib / "components" / "pro-glow.md").write_text(GLOW.replace("Glow card", "Pro glow"))
    project = tmp_path / "site"
    (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# A\n")
    (project / "docs" / "UI_UX.md").write_text("# UI\n")
    toolkit = tk.normalize_toolkit({"components": [{"library": "calm-ui", "slug": "pro-glow"}], "skills": []},
                                   template="website", libraries_root=catalog, skill_names=set())
    tk.apply_toolkit(project, toolkit, libraries_root=catalog)
    assert "not in the library's downloaded source" in (project / "docs" / "UI_UX.md").read_text()


def test_caveman_is_recommended_for_every_project_when_installed():
    skills = SKILLS + [{"name": "caveman", "category": "style", "description": "Terse replies."}]
    for template in ("web", "cli", "blank"):
        out = {s["name"]: s for s in tk.suggest_skills(skills, template=template, brief="")}
        assert out["caveman"]["recommended"] is True and out["caveman"]["default"] is True
    assert "caveman" not in {s["name"] for s in tk.suggest_skills(SKILLS, template="web", brief="")}
