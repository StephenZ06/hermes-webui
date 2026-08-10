"""Knowledge Browser API: list/read/search across MEMORY.md entries, USER.md,
SOUL.md, saved prompts, and standalone prompt files.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Knowledge Browser".
"""
import json
import urllib.error
import urllib.request

from tests._pytest_port import BASE


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def _delete(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data, method="DELETE",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


# ── HTTP round-trip: seed via existing endpoints, verify Knowledge Browser sees it ──

def test_memory_entry_appears_in_knowledge_list_and_search():
    original = get("/api/memory")[0].get("memory", "")
    marker = "Knowledge-browser-test-marker-entry-9c2f"
    new_content = (original + ("\n§\n" if original.strip() else "") + marker)
    try:
        d, status = post("/api/memory/write", {"section": "memory", "content": new_content})
        assert status == 200, d

        items, status = get("/api/knowledge/list")
        assert status == 200
        matches = [i for i in items["items"] if i["type"] == "memory" and marker in i["snippet"]]
        assert len(matches) == 1, f"expected exactly one matching memory item, got {matches}"
        item_id = matches[0]["id"]

        read_data, status = get(f"/api/knowledge/read?id={item_id}")
        assert status == 200
        assert marker in read_data["item"]["content"]

        search_data, status = get("/api/knowledge/search?q=" + marker)
        assert status == 200
        assert any(r["id"] == item_id for r in search_data["results"])
    finally:
        post("/api/memory/write", {"section": "memory", "content": original})


def test_soul_appears_as_single_knowledge_item():
    original = get("/api/memory")[0].get("soul", "")
    marker_content = "# Test Soul\nKnowledge-browser-soul-marker-7ab1"
    try:
        post("/api/memory/write", {"section": "soul", "content": marker_content})
        items, status = get("/api/knowledge/list")
        assert status == 200
        matches = [i for i in items["items"] if i["id"] == "soul:0"]
        assert len(matches) == 1
        read_data, status = get("/api/knowledge/read?id=soul:0")
        assert status == 200
        assert "Knowledge-browser-soul-marker-7ab1" in read_data["item"]["content"]
    finally:
        post("/api/memory/write", {"section": "soul", "content": original})


def test_saved_prompt_appears_in_knowledge_list():
    d, status = post("/api/prompts", {"label": "KB test prompt", "text": "Knowledge browser saved prompt body 4f2e"})
    assert status == 200, d
    pid = d["prompt"]["id"]
    try:
        items, status = get("/api/knowledge/list")
        assert status == 200
        matches = [i for i in items["items"] if i["id"] == f"saved_prompt:{pid}"]
        assert len(matches) == 1
        assert matches[0]["title"] == "KB test prompt"

        read_data, status = get(f"/api/knowledge/read?id=saved_prompt:{pid}")
        assert status == 200
        assert read_data["item"]["content"] == "Knowledge browser saved prompt body 4f2e"

        search_data, status = get("/api/knowledge/search?q=4f2e")
        assert status == 200
        assert any(r["id"] == f"saved_prompt:{pid}" for r in search_data["results"])
    finally:
        _delete("/api/prompts", {"id": pid})


# ── Endpoint validation ──

def test_read_unknown_id_returns_404():
    d, status = get("/api/knowledge/read?id=does-not-exist")
    assert status == 404


def test_read_missing_id_returns_404():
    d, status = get("/api/knowledge/read")
    assert status == 404


def test_search_requires_q():
    d, status = get("/api/knowledge/search")
    assert status == 400


def test_search_empty_q_rejected():
    d, status = get("/api/knowledge/search?q=")
    assert status == 400


def test_list_returns_items_key():
    d, status = get("/api/knowledge/list")
    assert status == 200
    assert isinstance(d.get("items"), list)


# ── Unit-level: prompt files, memory splitting, caps, gating, isolation ──

def test_memory_md_splits_into_individual_section_entries(tmp_path, monkeypatch):
    from api import knowledge_browser

    home = tmp_path / "profile-a"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text("First fact.\n§\nSecond fact.\n§\nThird fact.", encoding="utf-8")

    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home))

    result = knowledge_browser.list_items()
    memory_items = [i for i in result["items"] if i["type"] == "memory"]
    assert len(memory_items) == 3
    ids = sorted(i["id"] for i in memory_items)
    assert ids == ["memory:0", "memory:1", "memory:2"]


def test_prompt_file_indexed_and_readable(tmp_path, monkeypatch):
    from api import knowledge_browser

    home = tmp_path / "profile-a"
    (home / "prompts").mkdir(parents=True)
    (home / "prompts" / "example.md").write_text("# Example prompt\nDo the thing carefully.", encoding="utf-8")

    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home))

    listed = knowledge_browser.list_items()
    matches = [i for i in listed["items"] if i["type"] == "prompt_file"]
    assert len(matches) == 1
    assert matches[0]["id"] == "prompt_file:example.md"
    assert matches[0]["title"] == "example"

    read = knowledge_browser.read_item("prompt_file:example.md")
    assert read is not None
    assert "Do the thing carefully." in read["content"]


def test_read_item_with_unrecognized_id_returns_none_not_a_path_read(tmp_path, monkeypatch):
    """An id that doesn't match the current enumeration must never resolve to
    an arbitrary filesystem read — read_item re-derives from list, it never
    joins client input directly onto a path."""
    from api import knowledge_browser

    home = tmp_path / "profile-a"
    home.mkdir(parents=True)
    # A file that exists on disk but was never enumerated (wrong dir).
    secret = tmp_path / "outside-secret.md"
    secret.write_text("should never be readable via knowledge browser", encoding="utf-8")

    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home))

    assert knowledge_browser.read_item("prompt_file:../outside-secret.md") is None
    assert knowledge_browser.read_item("prompt_file:outside-secret.md") is None


def test_search_query_capped_and_case_insensitive(tmp_path, monkeypatch):
    from api import knowledge_browser

    home = tmp_path / "profile-a"
    (home / "prompts").mkdir(parents=True)
    (home / "prompts" / "a.md").write_text("Contains the word Elephant in it.", encoding="utf-8")

    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home))

    result = knowledge_browser.search_items("elephant")
    assert any(r["id"] == "prompt_file:a.md" for r in result["results"])

    too_long = knowledge_browser.search_items("x" * 500)
    assert len(too_long["query"]) == knowledge_browser.SEARCH_QUERY_MAX


def test_memory_disabled_flag_excludes_memory_items(tmp_path, monkeypatch):
    from api import knowledge_browser

    home = tmp_path / "profile-a"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text("A fact that should be hidden.", encoding="utf-8")

    import api.profiles as profiles_mod
    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home))
    monkeypatch.setattr(knowledge_browser, "_memory_flags", lambda: (False, True))

    result = knowledge_browser.list_items()
    assert not any(i["type"] == "memory" for i in result["items"])


def test_profile_isolation(tmp_path, monkeypatch):
    from api import knowledge_browser

    home_a = tmp_path / "profile-a"
    home_b = tmp_path / "profile-b"
    (home_a / "prompts").mkdir(parents=True)
    (home_b / "prompts").mkdir(parents=True)
    (home_a / "prompts" / "a-only.md").write_text("Content only in profile A.", encoding="utf-8")

    import api.profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_a))
    a_items = knowledge_browser.list_items()["items"]
    assert any(i["id"] == "prompt_file:a-only.md" for i in a_items)

    monkeypatch.setattr(profiles_mod, "get_active_hermes_home", lambda: str(home_b))
    b_items = knowledge_browser.list_items()["items"]
    assert not any(i["id"] == "prompt_file:a-only.md" for i in b_items)
