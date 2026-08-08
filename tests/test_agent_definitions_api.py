"""Personas (agent definitions) API: CRUD round-trip, builtin protection,
duplicate, caps, and profile isolation.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 1 -- Personas".
"""
import json
import urllib.error
import urllib.request

from tests._pytest_port import BASE


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read()), r.status


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def make_persona(created_list, **overrides):
    body = {"name": "Test Persona", "role": "Does testing", "system_prompt": "Be a test."}
    body.update(overrides)
    d, status = post("/api/agent-definitions/create", body)
    assert status == 200, f"create failed: {d}"
    pid = d["definition"]["id"]
    created_list.append(pid)
    return pid, d["definition"]


def cleanup_personas(ids):
    for pid in ids:
        try:
            post("/api/agent-definitions/delete", {"id": pid})
        except Exception:
            pass


# ── CRUD round-trip ─────────────────────────────────────────────────────

def test_list_includes_builtins():
    d, status = get("/api/agent-definitions")
    assert status == 200
    assert d["builtin_count"] >= 1
    ids = [x["id"] for x in d["definitions"]]
    assert any(i.startswith("builtin:") for i in ids)
    builtins = [x for x in d["definitions"] if x["id"].startswith("builtin:")]
    assert all(x["builtin"] is True for x in builtins)


def test_create_persona_appears_in_list():
    pids = []
    try:
        pid, definition = make_persona(pids, name="Reviewer Bot", tags=["a", "b"])
        assert len(pid) == 12
        assert definition["name"] == "Reviewer Bot"
        assert definition["builtin"] is False
        assert definition["tags"] == ["a", "b"]
        assert "created_at" in definition and "updated_at" in definition

        d, status = get("/api/agent-definitions")
        assert status == 200
        ids = [x["id"] for x in d["definitions"]]
        assert pid in ids
    finally:
        cleanup_personas(pids)


def test_create_requires_name():
    d, status = post("/api/agent-definitions/create", {"system_prompt": "hi"})
    assert status == 400
    assert "error" in d


def test_update_persona():
    pids = []
    try:
        pid, _ = make_persona(pids, name="Original")
        d, status = post("/api/agent-definitions/update", {"id": pid, "name": "Renamed", "role": "New role"})
        assert status == 200
        assert d["definition"]["name"] == "Renamed"
        assert d["definition"]["role"] == "New role"

        d2, _ = get("/api/agent-definitions")
        match = next(x for x in d2["definitions"] if x["id"] == pid)
        assert match["name"] == "Renamed"
    finally:
        cleanup_personas(pids)


def test_update_nonexistent_returns_404():
    d, status = post("/api/agent-definitions/update", {"id": "does-not-exist", "name": "x"})
    assert status == 404


def test_delete_removes_custom_row():
    pids = []
    pid, _ = make_persona(pids, name="Deleteme")
    d, status = post("/api/agent-definitions/delete", {"id": pid})
    assert status == 200
    assert d["ok"] is True

    d2, _ = get("/api/agent-definitions")
    ids = [x["id"] for x in d2["definitions"]]
    assert pid not in ids


def test_delete_requires_id():
    d, status = post("/api/agent-definitions/delete", {})
    assert status == 400


def test_delete_nonexistent_returns_404():
    d, status = post("/api/agent-definitions/delete", {"id": "does-not-exist"})
    assert status == 404


# ── Built-in protection ─────────────────────────────────────────────────

def test_update_builtin_rejected():
    d, status = get("/api/agent-definitions")
    builtin_id = next(x["id"] for x in d["definitions"] if x["id"].startswith("builtin:"))
    d2, status2 = post("/api/agent-definitions/update", {"id": builtin_id, "name": "Hacked"})
    assert status2 == 400
    assert "built-in" in d2["error"].lower() or "builtin" in d2["error"].lower()


def test_delete_builtin_rejected():
    d, status = get("/api/agent-definitions")
    builtin_id = next(x["id"] for x in d["definitions"] if x["id"].startswith("builtin:"))
    d2, status2 = post("/api/agent-definitions/delete", {"id": builtin_id})
    assert status2 == 400
    # Builtin must still be present afterward.
    d3, _ = get("/api/agent-definitions")
    ids = [x["id"] for x in d3["definitions"]]
    assert builtin_id in ids


# ── Duplicate ────────────────────────────────────────────────────────────

def test_duplicate_builtin_produces_custom_row():
    d, _ = get("/api/agent-definitions")
    builtin = next(x for x in d["definitions"] if x["id"].startswith("builtin:"))
    pids = []
    try:
        dup, status = post("/api/agent-definitions/duplicate", {"id": builtin["id"]})
        assert status == 200
        new_def = dup["definition"]
        pids.append(new_def["id"])
        assert new_def["id"] != builtin["id"]
        assert new_def["builtin"] is False
        assert new_def["name"] == builtin["name"] + " (copy)"
    finally:
        cleanup_personas(pids)


def test_duplicate_custom_copies_tags_independently():
    pids = []
    try:
        pid, original = make_persona(pids, name="Original", tags=["x", "y"])
        dup, status = post("/api/agent-definitions/duplicate", {"id": pid})
        assert status == 200
        new_def = dup["definition"]
        pids.append(new_def["id"])
        assert new_def["tags"] == ["x", "y"]
        assert new_def["tags"] is not original["tags"]

        # Mutating the copy's tags via update must not affect the original.
        post("/api/agent-definitions/update", {"id": new_def["id"], "tags": ["z"]})
        d, _ = get("/api/agent-definitions")
        orig_row = next(x for x in d["definitions"] if x["id"] == pid)
        assert orig_row["tags"] == ["x", "y"]
    finally:
        cleanup_personas(pids)


def test_duplicate_nonexistent_returns_404():
    d, status = post("/api/agent-definitions/duplicate", {"id": "does-not-exist"})
    assert status == 404


# ── Caps ─────────────────────────────────────────────────────────────────

def test_name_capped_at_128_chars():
    pids = []
    try:
        pid, definition = make_persona(pids, name="x" * 500)
        assert len(definition["name"]) == 128
    finally:
        cleanup_personas(pids)


def test_system_prompt_over_cap_rejected():
    d, status = post("/api/agent-definitions/create", {
        "name": "Too long",
        "system_prompt": "x" * 8001,
    })
    assert status == 400


def test_invalid_color_rejected():
    d, status = post("/api/agent-definitions/create", {"name": "Bad color", "color": "not-a-color"})
    assert status == 400


def test_tags_capped_at_10_items():
    pids = []
    try:
        pid, definition = make_persona(pids, tags=[f"t{i}" for i in range(20)])
        assert len(definition["tags"]) == 10
    finally:
        cleanup_personas(pids)


# ── Profile isolation ────────────────────────────────────────────────────

def test_profile_isolation(tmp_path, monkeypatch):
    """Two profiles must never see each other's custom personas.

    Unit-level (not HTTP) since it targets the storage layer directly: the
    module resolves its storage path via api.profiles.get_active_hermes_home()
    on every call, so patching that function simulates two distinct active
    profiles without needing real auth/profile-switch plumbing.
    """
    from api import agent_definitions

    home_a = tmp_path / "profile-a"
    home_b = tmp_path / "profile-b"
    home_a.mkdir()
    home_b.mkdir()

    import api.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_a))
    agent_definitions.create_definition({"name": "Profile A Persona"})
    a_list = agent_definitions.list_definitions()["definitions"]
    a_names = [d["name"] for d in a_list if not d["id"].startswith("builtin:")]
    assert a_names == ["Profile A Persona"]

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_b))
    b_list = agent_definitions.list_definitions()["definitions"]
    b_names = [d["name"] for d in b_list if not d["id"].startswith("builtin:")]
    assert b_names == []

    agent_definitions.create_definition({"name": "Profile B Persona"})
    b_list2 = agent_definitions.list_definitions()["definitions"]
    b_names2 = [d["name"] for d in b_list2 if not d["id"].startswith("builtin:")]
    assert b_names2 == ["Profile B Persona"]

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_a))
    a_list2 = agent_definitions.list_definitions()["definitions"]
    a_names2 = [d["name"] for d in a_list2 if not d["id"].startswith("builtin:")]
    assert a_names2 == ["Profile A Persona"]
