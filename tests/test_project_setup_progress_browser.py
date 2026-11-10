"""The setup step shows what Architecture is doing now under its task, and a
project the wizard created is deleted with its folder (the dialog says so)."""

from tests.test_project_builder_wizard_browser import _through_brief, _to_template, page  # noqa: F401  (fixture)


def test_the_setup_task_shows_the_agents_latest_step_until_it_finishes(page):
    polls = {"n": 0}

    def job(route):
        if "j2" not in route.request.url:
            return route.fallback()
        polls["n"] += 1
        if polls["n"] <= 2:
            return route.fulfill(json={"status": "running", "kind": "setup", "progress": "Running npm install"})
        return route.fulfill(json={"status": "done", "kind": "setup", "result": {"summary": "Installed and documented."}})

    page.unroute("**/api/projects/create_starter")
    page.route("**/api/projects/create_starter", lambda r: r.fulfill(json={
        "ok": True, "project": {"project_id": "p1", "name": "lex", "workspace_path": "/tmp/ws/lex"},
        "starter": {}, "docs_job": "j2", "kickoff": ""}))
    page.route("**/api/projects/starter/job*", job)
    _to_template(page, "Website")
    _through_brief(page)
    page.wait_for_selector(".ps-look-card")
    page.click(".ps-next")
    page.wait_for_selector(".ps-kit-skill")
    page.click(".ps-next")
    page.click(".ps-extra")
    page.wait_for_function("() => (document.querySelector('.ps-task.is-running .ps-task-log')||{}).textContent === 'Running npm install'")
    page.wait_for_selector(".ps-summary:not([hidden])", timeout=15000)
    assert page.locator(".ps-task-log").count() == 0
    assert page.inner_text(".ps-summary") == "Installed and documented."


def test_deleting_a_wizard_project_says_its_folder_goes_and_asks_for_it(page):
    sent = []
    page.route("**/api/projects/delete", lambda r: (sent.append(r.request.post_data_json), r.fulfill(json={"ok": True, "folder_deleted": True}))[1])
    page.evaluate("""() => { window.__msg = null; window.showConfirmDialog = (o) => { window.__msg = o.message; return Promise.resolve(true); };
      _confirmDeleteProject({project_id: 'p1', name: 'lex', workspace_path: '/tmp/ws/lex', created_folder: true}); }""")
    page.wait_for_function("() => window.__msg")
    assert "/tmp/ws/lex is deleted" in page.evaluate("window.__msg")
    page.wait_for_function("() => true")
    page.wait_for_timeout(300)
    assert sent == [{"project_id": "p1", "delete_folder": True}]
    page.evaluate("""() => { window.__msg = null; _confirmDeleteProject({project_id: 'p2', name: 'mine', workspace_path: '/tmp/ws/mine'}); }""")
    page.wait_for_function("() => window.__msg")
    assert "deleted with everything" not in page.evaluate("window.__msg")
    page.wait_for_timeout(300)
    assert sent[-1] == {"project_id": "p2", "delete_folder": False}
