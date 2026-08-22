import api.project_registry as project_registry
from api.streaming import _bound_project_prompt, _webui_ephemeral_system_prompt


class _FakeSession:
    def __init__(self, bound_project_key=None):
        self.bound_project_key = bound_project_key


def test_bound_project_prompt_none_for_unbound_session():
    assert _bound_project_prompt(_FakeSession(bound_project_key=None)) is None
    assert _bound_project_prompt(None) is None


def test_bound_project_prompt_injects_skill_and_local_location(monkeypatch, tmp_path):
    repo = tmp_path / "job-os"
    repo.mkdir()
    monkeypatch.setattr(
        project_registry,
        "list_registry_projects",
        lambda: [
            {
                "key": "job-os",
                "name": "Job OS",
                "access_mode": "local",
                "repo_path": str(repo),
                "ssh": None,
                "status": "confirmed project root",
                "required_docs": [".hermes.md", "CONTEXT.md"],
                "available": True,
                "unavailable_reason": None,
            }
        ],
    )
    monkeypatch.setattr(
        project_registry, "read_project_lifecycle_skill_text", lambda: "# Project Lifecycle\nBody."
    )

    prompt = _bound_project_prompt(_FakeSession(bound_project_key="job-os"))

    assert "bound to project 'Job OS'" in prompt
    assert "access_mode: local" in prompt
    assert f"repo_path: {repo}" in prompt
    assert ".hermes.md, CONTEXT.md" in prompt
    assert "Operate ONLY inside this resolved project location" in prompt
    assert "# Project Lifecycle\nBody." in prompt


def test_bound_project_prompt_injects_ssh_location(monkeypatch):
    monkeypatch.setattr(
        project_registry,
        "list_registry_projects",
        lambda: [
            {
                "key": "remote-project",
                "name": "Remote Project",
                "access_mode": "ssh",
                "repo_path": None,
                "ssh": {"target": "user@host", "key": "/keys/id_rsa", "remote_path": "/srv/app"},
                "status": "confirmed project root",
                "required_docs": [],
                "available": True,
                "unavailable_reason": None,
            }
        ],
    )
    monkeypatch.setattr(project_registry, "read_project_lifecycle_skill_text", lambda: "Skill body.")

    prompt = _bound_project_prompt(_FakeSession(bound_project_key="remote-project"))

    assert "access_mode: ssh" in prompt
    assert "ssh_target: user@host" in prompt
    assert "remote_path: /srv/app" in prompt


def test_bound_project_prompt_errors_visibly_when_registry_drifted(monkeypatch):
    monkeypatch.setattr(project_registry, "list_registry_projects", lambda: [])

    prompt = _bound_project_prompt(_FakeSession(bound_project_key="gone"))

    assert "PROJECT BINDING ERROR" in prompt
    assert "gone" in prompt
    assert "do not guess at a folder" in prompt


def test_bound_project_prompt_errors_visibly_when_project_became_unavailable(monkeypatch):
    monkeypatch.setattr(
        project_registry,
        "list_registry_projects",
        lambda: [
            {
                "key": "flaky",
                "name": "Flaky",
                "access_mode": "local",
                "repo_path": None,
                "ssh": None,
                "status": "NEEDS_CONFIRMATION",
                "required_docs": [],
                "available": False,
                "unavailable_reason": "repo path not confirmed",
            }
        ],
    )

    prompt = _bound_project_prompt(_FakeSession(bound_project_key="flaky"))

    assert "PROJECT BINDING ERROR" in prompt
    assert "repo path not confirmed" in prompt


def test_bound_project_prompt_errors_visibly_when_skill_file_missing(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        project_registry,
        "list_registry_projects",
        lambda: [
            {
                "key": "job-os",
                "name": "Job OS",
                "access_mode": "local",
                "repo_path": str(repo),
                "ssh": None,
                "status": "confirmed project root",
                "required_docs": [],
                "available": True,
                "unavailable_reason": None,
            }
        ],
    )
    monkeypatch.setattr(project_registry, "read_project_lifecycle_skill_text", lambda: None)

    prompt = _bound_project_prompt(_FakeSession(bound_project_key="job-os"))

    assert "PROJECT BINDING ERROR" in prompt
    assert "could not be read" in prompt


def test_webui_ephemeral_system_prompt_includes_bound_project_block(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        project_registry,
        "list_registry_projects",
        lambda: [
            {
                "key": "job-os",
                "name": "Job OS",
                "access_mode": "local",
                "repo_path": str(repo),
                "ssh": None,
                "status": "confirmed project root",
                "required_docs": [],
                "available": True,
                "unavailable_reason": None,
            }
        ],
    )
    monkeypatch.setattr(project_registry, "read_project_lifecycle_skill_text", lambda: "Skill body.")

    prompt = _webui_ephemeral_system_prompt(
        None,
        surface_context={"source": "webui", "session_id": "s1", "profile": "default", "workspace": str(repo)},
        session=_FakeSession(bound_project_key="job-os"),
    )

    assert "bound to project 'Job OS'" in prompt
    assert "Skill body." in prompt


def test_webui_ephemeral_system_prompt_unaffected_when_session_omitted():
    prompt = _webui_ephemeral_system_prompt(
        "Use a concise tone.",
        surface_context={"source": "webui", "session_id": "s1", "profile": "default", "workspace": "/tmp/x"},
    )

    assert "PROJECT BINDING" not in prompt
    assert "bound to project" not in prompt
