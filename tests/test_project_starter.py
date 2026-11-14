"""Project starter packs must stay inside a selected trusted workspace."""

from pathlib import Path

from api import project_starter


def test_web_starter_writes_a_personalised_project_context(tmp_path: Path):
    result = project_starter.create_starter_pack(
        workspace_root=tmp_path,
        folder_name="orbit-dashboard",
        template="web",
        brief="A dashboard that helps a small SaaS team understand customer health.",
    )

    root = tmp_path / "orbit-dashboard"
    assert result["path"] == str(root)
    assert (root / "AGENTS.md").is_file()
    assert (root / ".agent" / "ECC_HANDOFF.md").is_file()
    assert (root / "docs" / "ARCHITECTURE.md").is_file()
    assert "customer health" in (root / "docs" / "PRODUCT.md").read_text(encoding="utf-8")
    assert "ECC_HANDOFF.md" in (root / "AGENTS.md").read_text(encoding="utf-8")


def test_starter_rejects_an_unsafe_or_existing_folder(tmp_path: Path):
    (tmp_path / "existing").mkdir()

    try:
        project_starter.create_starter_pack(tmp_path, "../escape", "blank", "")
    except project_starter.ProjectStarterError as exc:
        assert "folder name" in str(exc).lower()
    else:
        raise AssertionError("unsafe folder name was accepted")

    try:
        project_starter.create_starter_pack(tmp_path, "existing", "blank", "")
    except project_starter.ProjectStarterError as exc:
        assert "already exists" in str(exc).lower()
    else:
        raise AssertionError("existing folder was overwritten")


def test_adopting_an_existing_project_only_adds_missing_docs(tmp_path: Path):
    project = tmp_path / "existing-app"
    project.mkdir()
    (project / "README.md").write_text("# Keep me\n", encoding="utf-8")

    result = project_starter.adopt_starter_pack(project, "ios", "A focused iPhone app.")

    assert result["path"] == str(project)
    assert (project / "AGENTS.md").is_file()
    assert (project / "docs" / "IOS.md").is_file()
    assert (project / "README.md").read_text(encoding="utf-8") == "# Keep me\n"


def _rejects(callable_, *args):
    try:
        callable_(*args)
    except project_starter.ProjectStarterError as exc:
        return str(exc)
    raise AssertionError(f"accepted {args!r}")


def test_folder_names_that_break_on_disk_or_hide_are_rejected(tmp_path: Path):
    for bad in (".hidden", "trailing.", "a:b", "what?", "con", "NUL.txt", "tab\tname"):
        _rejects(project_starter.create_starter_pack, tmp_path, bad, "blank", "")
    assert list(tmp_path.iterdir()) == []


def test_create_never_merges_into_a_folder_that_appears_late(tmp_path: Path, monkeypatch):
    # Simulate another process creating the folder after the existence check.
    real_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: False if self.name == "late" else real_exists(self))
    (tmp_path / "late").mkdir()
    (tmp_path / "late" / "keep.txt").write_text("mine", encoding="utf-8")

    _rejects(project_starter.create_starter_pack, tmp_path, "late", "web", "")

    assert sorted(p.name for p in (tmp_path / "late").iterdir()) == ["keep.txt"]


def test_failed_adopt_removes_only_the_documents_it_added(tmp_path: Path, monkeypatch):
    project = tmp_path / "app"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "NOTES.md").write_text("keep", encoding="utf-8")
    real_write = project_starter._write
    calls = {"n": 0}

    def flaky(root, path, content):
        calls["n"] += 1
        if calls["n"] == 4:
            raise OSError("disk full")
        real_write(root, path, content)

    monkeypatch.setattr(project_starter, "_write", flaky)
    try:
        project_starter.adopt_starter_pack(project, "web", "")
    except OSError:
        pass
    else:
        raise AssertionError("write failure was swallowed")

    assert sorted(str(p.relative_to(project)) for p in project.rglob("*")) == ["docs", "docs/NOTES.md"]


def test_rollback_after_adopt_restores_the_original_folder(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text("# Keep me\n", encoding="utf-8")

    result = project_starter.adopt_starter_pack(project, "api", "")
    project_starter.rollback_adopted(project, result)

    assert sorted(p.name for p in project.iterdir()) == ["README.md"]


def test_a_folder_that_is_already_a_project_is_found(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    projects = [{"project_id": "a", "name": "Other", "workspace_path": str(tmp_path / "other")},
                {"project_id": "b", "name": "App", "workspace_path": str(project) + "/"}]

    assert project_starter.project_using_path(projects, project)["project_id"] == "b"
    assert project_starter.project_using_path(projects, tmp_path / "new") is None


def test_select_popups_open_above_the_project_starter_modal():
    import re

    css = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")

    def z(selector):
        match = re.search(re.escape(selector) + r"\{[^}]*z-index:(\d+)", css)
        assert match, selector
        return int(match.group(1))

    assert z(".themed-select-popup") > z(".project-starter-overlay")


def test_template_catalog_lists_the_files_each_template_creates(tmp_path: Path):
    catalog = {t["key"]: t for t in project_starter.template_catalog()}

    assert len(catalog) == 8
    assert {"blank", "web", "ios", "android", "api", "website", "cli", "research"} == set(catalog)
    for key, entry in catalog.items():
        target = tmp_path / key
        project_starter.create_starter_pack(tmp_path, key, key, "")
        written = sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file())
        assert written == sorted(entry["files"]), key


def test_starter_records_the_answers_from_docs_git_questions(tmp_path: Path):
    project_starter.create_starter_pack(
        tmp_path, "shop", "web", "An online shop.",
        answers=[{"question": "Which stack?", "answer": "Next.js + Postgres"}, {"question": "Skip", "answer": ""}],
    )

    text = (tmp_path / "shop" / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "**Which stack?** Next.js + Postgres" in text
    assert "Skip" not in text


def test_folder_browser_lists_visible_subfolders_and_blocks_escapes(tmp_path: Path):
    (tmp_path / "b").mkdir()
    (tmp_path / "A" / "inner").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "link").symlink_to(tmp_path / "b")

    assert [f["name"] for f in project_starter.list_child_folders(tmp_path)] == ["A", "b"]
    assert project_starter.list_child_folders(tmp_path, "A") == [{"name": "inner", "path": "A/inner"}]
    assert project_starter.resolve_parent(tmp_path, "A/inner") == (tmp_path / "A" / "inner").resolve()
    _rejects(project_starter.list_child_folders, tmp_path, "..")
    _rejects(project_starter.resolve_parent, tmp_path, "../..")


def test_docs_git_review_is_parsed_into_bounded_questions():
    from api.project_starter_agent import parse_analysis

    reply = 'Sure!\n```json\n{"complete": false, "summary": "A shop", "questions": [' + ",".join(
        f'{{"id": "q{i}", "question": "Q{i}?", "options": ["a","b","c","d","e","f","g"]}}' for i in range(9)
    ) + "]}\n```"
    result = parse_analysis(reply)

    assert result["complete"] is False
    assert len(result["questions"]) == 6
    # Three choices plus a typed answer: the wizard's four numbered keys.
    assert result["questions"][0] == {"id": "q0", "question": "Q0?", "options": ["a", "b", "c"],
                                      "details": ["", "", ""], "other": "Something else"}
    assert parse_analysis('{"complete": true, "questions": []}')["complete"] is True
    try:
        parse_analysis("no json here")
    except ValueError:
        pass
    else:
        raise AssertionError("unreadable review was accepted")


def test_new_projects_carry_the_lifecycle_contract_and_docs(tmp_path: Path):
    project_starter.create_starter_pack(tmp_path, "shop", "web", "An online candle shop.")
    root = tmp_path / "shop"

    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "project-lifecycle" in agents and ".agent/ECC_HANDOFF.md" in agents and "docs/UI_UX.md" in agents
    for rel in (".agent/CONTEXT.md", ".agent/PROJECT_STATUS.md", ".agent/TASKS.md", ".agent/CHANGELOG.md"):
        assert (root / rel).is_file(), rel
    architecture = (root / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "## Stack" in architecture and "candle shop" in architecture


def test_registry_gets_one_appended_entry_and_never_a_duplicate(tmp_path: Path):
    registry = tmp_path / "WORKSPACES.yaml"
    registry.write_text("projects:\n  shop:\n    display_name: Shop\n    access_mode: local\n    repo_path: /old/shop\n    status: confirmed project root\n")
    project = tmp_path / "Shop"
    project.mkdir()

    key = project_starter.register_in_lifecycle_registry("Shop", project, registry)
    assert key == "shop-2"
    assert project_starter.register_in_lifecycle_registry("Shop", project, registry) is None
    import yaml

    data = yaml.safe_load(registry.read_text())
    assert data["projects"]["shop"]["repo_path"] == "/old/shop"
    assert data["projects"]["shop-2"] == {"display_name": "Shop", "access_mode": "local",
                                         "repo_path": str(project.resolve()), "status": "confirmed project root"}


def test_recommended_option_must_be_one_of_the_options():
    from api.project_starter_agent import parse_analysis

    result = parse_analysis('{"complete": false, "questions": ['
                            '{"id": "stack", "question": "Stack?", "options": ["Next.js", "Django"], "recommended": "next.js", "why": "SSR and a big ecosystem"},'
                            '{"id": "db", "question": "DB?", "options": ["Postgres", "SQLite"], "recommended": "Mongo"}]}')

    assert result["questions"][0]["recommended"] == "Next.js" and result["questions"][0]["why"] == "SSR and a big ecosystem"
    assert "recommended" not in result["questions"][1]


def test_hidden_docs_git_sessions_never_reach_the_sidebar():
    from api.models import _hide_from_default_sidebar

    assert _hide_from_default_sidebar({"session_id": "abc", "source_tag": "project_starter"}) is True
    assert _hide_from_default_sidebar({"session_id": "abc", "source_tag": "project_starter"},
                                      show_cron=True, show_webhook=True, show_kanban=True) is True
    assert _hide_from_default_sidebar({"session_id": "abc", "source_tag": "webui"}) is False


def test_an_other_option_becomes_the_typed_answer_and_reasons_carry_examples():
    from api.project_starter_agent import parse_analysis

    result = parse_analysis('{"complete": false, "questions": [{"id": "stack", "question": "Stack?", "options": ['
                            '{"label": "Next.js", "detail": "React with server rendering"}, "Django", "Rails", "Other stack (type it)"],'
                            '"recommended": "Next.js", "why": "' + "x" * 700 + '",'
                            '"examples": ["Vercel hosts it free", "Shopify Hydrogen uses React", "", "a", "b"]}]}')
    [q] = result["questions"]
    assert q["options"] == ["Next.js", "Django", "Rails"]
    assert q["details"] == ["React with server rendering", "", ""]
    assert q["other"] == "Other stack (type it)"
    assert len(q["why"]) == 600
    assert q["examples"] == ["Vercel hosts it free", "Shopify Hydrogen uses React", "a"]


def test_each_option_carries_how_it_would_be_built_so_any_choice_can_be_explained():
    from api.project_starter_agent import _ANALYSIS_PROMPT, parse_analysis

    assert '"how"' in _ANALYSIS_PROMPT
    result = parse_analysis('{"complete": false, "questions": [{"id": "stack", "question": "Stack?", "options": ['
                            '{"label": "Astro", "detail": "static", "how": "Astro pages with content collections."},'
                            '{"label": "Next.js", "detail": "React", "how": "' + "y" * 500 + '"},'
                            '{"label": "Plain HTML", "detail": "none"}], "recommended": "Astro", "why": "Fast."}]}')
    [q] = result["questions"]
    assert q["hows"] == ["Astro pages with content collections.", "y" * 400, ""]
    plain = parse_analysis('{"complete": false, "questions": [{"id": "s", "question": "S?", "options": ["A", "B", "C"]}]}')
    assert "hows" not in plain["questions"][0]


def test_every_starter_document_links_to_the_others(tmp_path: Path):
    import re

    project_starter.create_starter_pack(tmp_path, "shop", "web", "An online candle shop.")
    root = tmp_path / "shop"
    docs = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.md"))
    for rel in docs:
        text = (root / rel).read_text(encoding="utf-8")
        targets = {((root / rel).parent / m).resolve() for m in re.findall(r"\]\(([^)#]+\.md)\)", text)}
        for target in targets:
            assert target.is_file(), (rel, target)  # no dead links
        linked = {t.relative_to(root.resolve()).as_posix() for t in targets}
        assert linked >= set(docs) - {rel}, (rel, set(docs) - {rel} - linked)


def test_website_template_takes_the_cli_slot_and_writes_website_documents(tmp_path: Path):
    keys = [t["key"] for t in project_starter.template_catalog()]
    # Second row of the wizard's 4-wide grid: API, Website, CLI, Research.
    assert keys[4:] == ["api", "website", "cli", "research"]
    project_starter.create_starter_pack(tmp_path, "site", "website", "A portfolio site.")
    docs = sorted(p.name for p in (tmp_path / "site" / "docs").iterdir())
    assert docs == ["PAGES.md", "PERFORMANCE.md", "PRODUCT.md", "SECURITY.md", "SEO.md", "SKILLS_POLICY.md", "TESTING.md", "UI_UX.md"]
    assert "## Sitemap" in (tmp_path / "site" / "docs" / "PAGES.md").read_text(encoding="utf-8")
    assert "## Hosting and domain" in (tmp_path / "site" / "docs" / "SEO.md").read_text(encoding="utf-8")


def test_every_template_tells_agents_to_install_dependencies_inside_the_project(tmp_path: Path):
    for key in project_starter.available_templates():
        project_starter.create_starter_pack(tmp_path, key, key, "")
        agents = (tmp_path / key / "AGENTS.md").read_text(encoding="utf-8")
        readme = (tmp_path / key / "README.md").read_text(encoding="utf-8")
        assert "`.venv`" in agents and "Never install globally" in agents and "npm install -g" in agents, key
        assert "never globally" in readme, key


def test_adopting_a_project_with_its_own_agents_md_appends_a_marked_hermes_section(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    own = "# Our agent rules\n\nUse tabs.\n"
    (project / "AGENTS.md").write_text(own, encoding="utf-8")

    result = project_starter.adopt_starter_pack(project, "web", "")
    text = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith(own)
    assert text.count("<!-- hermes:begin -->") == 1 and "<!-- hermes:end -->" in text
    for rule in (".agent/ECC_HANDOFF.md", "Never install globally", "Before finishing"):
        assert rule in text
    # A second adopt leaves the section alone.
    project_starter.adopt_starter_pack(project, "web", "")
    assert (project / "AGENTS.md").read_text(encoding="utf-8").count("<!-- hermes:begin -->") == 1

    project_starter.rollback_adopted(project, result)
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == own


def test_rollback_keeps_edits_the_user_made_around_the_section(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    result = project_starter.adopt_starter_pack(project, "api", "")
    path = project / "AGENTS.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nAdded later.\n", encoding="utf-8")
    project_starter.rollback_adopted(project, result)
    assert path.read_text(encoding="utf-8") == "# Rules\n\nAdded later.\n"


def test_web_and_app_projects_get_the_performance_checklist_and_the_rule_to_run_it():
    from api import project_starter as ps
    for key in ("web", "website", "ios", "android"):
        files = ps._pack_files("demo", key, "A clinic site.")
        perf = files["docs/PERFORMANCE.md"]
        assert "Debounce search and autocomplete inputs" in perf and "Self-host fonts" in perf
        # The setup agent is told to keep the marked text word for word.
        assert perf.count("<!-- hermes:performance:begin -->") == 1 and "<!-- hermes:performance:end -->" in perf
        assert "run `docs/PERFORMANCE.md`" in files["AGENTS.md"] and '"Performance checklist" note' in files["AGENTS.md"]
    for key in ("cli", "api", "research", "blank"):
        files = ps._pack_files("demo", key, "")
        assert "docs/PERFORMANCE.md" not in files and "PERFORMANCE.md" not in files["AGENTS.md"]


def test_the_setup_agent_keeps_the_performance_block():
    from api import project_starter_agent as agent
    assert "hermes:performance:begin" in agent._new_project_prompt("demo", "Web App", ["docs/PERFORMANCE.md"])


def test_adopting_keeps_a_projects_own_performance_doc_and_points_the_rule_at_the_checklist(tmp_path):
    from api import project_starter as ps
    root = tmp_path / "shop"
    (root / "docs").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Shop rules\n\nBe nice.\n")
    (root / "docs" / "PERFORMANCE.md").write_text("# Our own perf notes\n")
    result = ps.adopt_starter_pack(root, "web", "An existing shop.")
    assert (root / "docs" / "PERFORMANCE.md").read_text() == "# Our own perf notes\n"
    assert "Debounce search" in (root / "docs" / "PERFORMANCE_CHECKLIST.md").read_text()
    agents = (root / "AGENTS.md").read_text()
    assert "Be nice." in agents and "run `docs/PERFORMANCE_CHECKLIST.md`" in agents
    ps.rollback_adopted(root, result)
    assert (root / "AGENTS.md").read_text().rstrip() == "# Shop rules\n\nBe nice.".rstrip()
    assert not (root / "docs" / "PERFORMANCE_CHECKLIST.md").exists()


def test_a_project_adopted_before_the_rule_existed_gets_only_the_rule(tmp_path):
    from api import project_starter as ps
    root = tmp_path / "old"
    root.mkdir()
    before = "# Old rules\n\n<!-- hermes:begin -->\n## Hermes continuity\n\nRead the handoff.\n<!-- hermes:end -->\n"
    (root / "AGENTS.md").write_text(before)
    result = ps.adopt_starter_pack(root, "website", "x")
    agents = (root / "AGENTS.md").read_text()
    assert agents.count("<!-- hermes:begin -->") == 1 and "Read the handoff." in agents
    assert "run `docs/PERFORMANCE.md`" in agents and agents.index("PERFORMANCE.md") < agents.index("<!-- hermes:end -->")
    assert result["added"]["perf_appended"]
    # Adopting again adds nothing more.
    ps.adopt_starter_pack(root, "website", "x")
    assert (root / "AGENTS.md").read_text().count("hermes:performance:begin") == 1
    # Undoing the first adopt removes only the rule, not the older section.
    ps.rollback_adopted(root, result)
    after = (root / "AGENTS.md").read_text()
    assert "hermes:performance" not in after and "Read the handoff." in after and "<!-- hermes:end -->" in after


def test_the_adopt_agent_keeps_the_performance_block():
    from api import project_starter_agent as agent
    assert "hermes:performance:begin" in agent._adopt_prompt("shop")


def test_web_website_and_api_projects_get_the_security_checklist_and_the_rule_to_run_it():
    from api import project_starter as ps
    for key in ("web", "website", "api"):
        files = ps._pack_files("demo", key, "A clinic site.")
        sec = files["docs/SECURITY.md"]
        for item in ("Hide API keys", "Purge Git secrets", "Enable row-level security", "Block field tampering",
                     "Rate limit login", "Parameterize queries", "Scan dependencies for known vulnerabilities"):
            assert item in sec, item
        assert sec.count("- [ ]") == 20
        assert sec.count("<!-- hermes:security:begin -->") == 1 and "<!-- hermes:security:end -->" in sec
        assert "run `docs/SECURITY.md`" in files["AGENTS.md"] and '"Security checklist" note' in files["AGENTS.md"]
    for key in ("cli", "research", "blank"):
        files = ps._pack_files("demo", key, "")
        assert "docs/SECURITY.md" not in files and "SECURITY.md" not in files["AGENTS.md"]


def test_the_setup_agent_keeps_the_security_block():
    from api import project_starter_agent as agent
    assert "hermes:security:begin" in agent._new_project_prompt("demo", "Web App", ["docs/SECURITY.md"])
    assert "hermes:security:begin" in agent._adopt_prompt("demo")


def test_a_project_adopted_before_the_security_rule_existed_gets_only_that_rule(tmp_path):
    from api import project_starter as ps
    root = tmp_path / "older"
    root.mkdir()
    before = ("# Old rules\n\n<!-- hermes:begin -->\n## Hermes continuity\n\nRead the handoff.\n\n"
              "- <!-- hermes:performance:begin -->run `docs/PERFORMANCE.md`<!-- hermes:performance:end -->\n<!-- hermes:end -->\n")
    (root / "AGENTS.md").write_text(before)
    result = ps.adopt_starter_pack(root, "web", "x")
    agents = (root / "AGENTS.md").read_text()
    assert agents.count("hermes:performance:begin") == 1 and agents.count("hermes:security:begin") == 1
    assert agents.index("hermes:security:begin") < agents.index("<!-- hermes:end -->")
    assert result["added"].get("security_appended") and not result["added"].get("perf_appended")
    ps.adopt_starter_pack(root, "web", "x")
    assert (root / "AGENTS.md").read_text().count("hermes:security:begin") == 1
    ps.rollback_adopted(root, result)
    after = (root / "AGENTS.md").read_text()
    assert "hermes:security" not in after and after.count("hermes:performance:begin") == 1 and "Read the handoff." in after


def test_every_template_gets_the_skills_policy_and_its_rule():
    from api import project_starter as ps
    for key in ("blank", "web", "website", "ios", "android", "api", "cli", "research"):
        files = ps._pack_files("demo", key, "")
        policy = files["docs/SKILLS_POLICY.md"]
        assert policy.count("<!-- hermes:skills-policy:begin -->") == 1 and "on demand" in policy and "Load when the task is in the skill's domain" in policy
        assert "docs/SKILLS_POLICY.md" in files["AGENTS.md"] and "hermes:skills-policy:begin" in files["AGENTS.md"]
        assert len(policy) < 3000  # read on demand, never a burden


def test_adopting_an_older_project_adds_only_the_missing_rules_and_rolls_back_cleanly(tmp_path):
    from api import project_starter as ps
    root = tmp_path / "older"
    root.mkdir()
    before = ("# Old rules\n\n<!-- hermes:begin -->\n## Hermes continuity\n\nRead the handoff.\n\n"
              "- <!-- hermes:performance:begin -->run `docs/PERFORMANCE.md`<!-- hermes:performance:end -->\n"
              "- <!-- hermes:security:begin -->run `docs/SECURITY.md`<!-- hermes:security:end -->\n<!-- hermes:end -->\n")
    (root / "AGENTS.md").write_text(before)
    result = ps.adopt_starter_pack(root, "web", "x")
    agents = (root / "AGENTS.md").read_text()
    assert agents.count("hermes:skills-policy:begin") == 1 and result["added"].get("skills_policy_appended")
    assert not result["added"].get("perf_appended") and not result["added"].get("security_appended")
    ps.rollback_adopted(root, result)
    after = (root / "AGENTS.md").read_text()
    assert "skills-policy" not in after and after.count("hermes:security:begin") == 1 and "Read the handoff." in after
