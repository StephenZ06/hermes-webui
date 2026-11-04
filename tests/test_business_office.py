"""Business Office: isolation, approvals, OAuth state, vault grants, runtime."""
from __future__ import annotations

import json
import threading
import time

import pytest

from api import config, notebook_vault
from api.business_office import adapters, crypto, http as office_http, http_client, oauth, registry, runtime, service, store
from api.business_office.adapters import gmail, obsidian
from api.business_office.errors import ToolError

A, B = "saas-temani", "cafe"


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.delenv(crypto.KEY_ENV, raising=False)
    runtime._running.clear()
    return tmp_path


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = (tmp_path / "vault").resolve()
    (root / ".obsidian").mkdir(parents=True)
    (root / "01 Projects" / "Temani").mkdir(parents=True)
    (root / "01 Projects" / "Cafe").mkdir(parents=True)
    (root / "01 Projects" / "Temani" / "Plan.md").write_text(
        "---\ntags: [x]\n---\nIntro [[Other]] line\n![[a.png]]\nüñí tail\n", encoding="utf-8")
    (root / "01 Projects" / "Cafe" / "Stock.md").write_text("cafe secret\n", encoding="utf-8")
    monkeypatch.setattr(notebook_vault, "_root", lambda: root)
    return root


def connect_gmail(business, *, email="a@example.com", scopes=None, token="tok-a"):
    return store.save_connection(business, "gmail", tokens={"access_token": token, "refresh_token": f"r-{token}"}, account_id=email,
                                 account_label=email, scopes=scopes or [registry.GMAIL_READ, registry.GMAIL_COMPOSE],
                                 expires_at=time.time() + 3600)


def grant(business, root, folder, agent="documents", **flags):
    row = store.add_vault_grant(business, str(root), folder)
    store.set_vault_agent_grant(business, row["id"], agent, flags)
    return row


def run(business, agent, capability, payload):
    task = store.create_task(business, agent, capability, payload)
    return task["id"], service.run_task(task["id"])


class FakeGmail:
    """Stands in for the network, at the one outbound function."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.draft_body = "Hello"
        monkeypatch.setattr(http_client, "request_json", self)

    def __call__(self, method, url, *, form=None, body=None, token="", allow_empty=False):
        self.calls.append((method, url, token))
        if url.endswith("/drafts/send"):
            return {"id": "sent1", "threadId": "t1"}
        if "/drafts/d1" in url:
            import base64
            data = base64.urlsafe_b64encode(self.draft_body.encode()).decode()
            return {"message": {"payload": {"mimeType": "text/plain", "body": {"data": data},
                                            "headers": [{"name": "To", "value": "c@example.com"}, {"name": "Subject", "value": "Hi"}]}}}
        return {"messages": []}

    @property
    def sends(self):
        return [call for call in self.calls if call[1].endswith("/drafts/send")]


# ── registry ────────────────────────────────────────────────────────────────────

def test_external_writes_can_never_be_automatic():
    send = registry.capability("gmail.send_draft")
    assert registry.AUTOMATIC not in registry.allowed_modes(send)
    with pytest.raises(store.StoreError):
        store.set_capability_mode(A, "email", send.id, registry.AUTOMATIC)


def test_a_forced_automatic_row_still_cannot_skip_approval(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    with store.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO capability_modes VALUES(?,?,?,?)", (A, "email", "gmail.send_draft", "automatic"))
    with pytest.raises(ToolError) as caught:
        run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    assert caught.value.kind == "denied"
    assert not fake.sends


def test_grants_do_not_leak_to_other_floors_by_default():
    read = registry.capability("gmail.read_message")
    assert store.capability_mode(A, "email", read) == registry.AUTOMATIC
    for agent in ("marketing", "operations", "documents", "conductor"):
        assert store.capability_mode(A, agent, read) == registry.DISABLED


def test_no_publishing_capability_exists_yet():
    assert not [item for item in registry.CAPABILITIES if item.provider in ("threads", "instagram") and item.risk != registry.READ]


def test_unknown_input_is_refused():
    with pytest.raises(ValueError):
        registry.validate_input(registry.capability("gmail.read_message"), {"message_id": "1", "business_id": B})


# ── secrets and isolation ───────────────────────────────────────────────────────

def test_tokens_are_encrypted_and_bound_to_their_business(state):
    connect_gmail(A, token="very-secret-token")
    assert b"very-secret-token" not in (state / store.DB_NAME).read_bytes()
    assert store.connection_tokens(A, "gmail")["access_token"] == "very-secret-token"
    with store.connect() as conn:
        sealed = conn.execute("SELECT token_enc FROM connections").fetchone()[0]
    with pytest.raises(crypto.SecretError):
        crypto.decrypt(sealed, context=f"token:{B}:gmail")


def test_two_businesses_hold_separate_gmail_accounts(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A, token="tok-a")
    connect_gmail(B, email="b@example.com", token="tok-b")
    run(A, "email", "gmail.search_messages", {"query": "x"})
    run(B, "email", "gmail.search_messages", {"query": "x"})
    assert [call[2] for call in fake.calls] == ["tok-a", "tok-b"]


def test_overview_never_contains_secrets():
    connect_gmail(A, token="very-secret-token")
    store.save_oauth_app("google", "client-id", "client-very-secret")
    text = json.dumps(office_http.overview(A, "https://h"))
    assert "very-secret-token" not in text and "client-very-secret" not in text and "secret_enc" not in text


def test_a_business_cannot_decide_or_cancel_another_businesss_work(monkeypatch):
    FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    with pytest.raises(store.StoreError):
        service.decide_approval(B, outcome["approval_id"], True)
    with pytest.raises(store.StoreError):
        runtime.cancel(B, task_id)


def test_tasks_cannot_depend_on_another_business():
    other = store.create_task(B, "email", "gmail.search_messages", {"query": "x"})
    with pytest.raises(store.StoreError):
        store.create_task(A, "email", "gmail.search_messages", {"query": "x"}, depends_on=[other["id"]])


# ── approvals ───────────────────────────────────────────────────────────────────

def test_send_waits_for_approval_then_sends_once(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    assert outcome["status"] == "waiting_approval" and not fake.sends
    approval = store.get_approval(outcome["approval_id"])
    assert approval["payload"]["to"] == "c@example.com" and approval["payload"]["body"] == "Hello"
    service.decide_approval(A, approval["id"], True)
    assert service.run_task(task_id)["status"] == "completed"
    assert len(fake.sends) == 1
    with pytest.raises(ToolError):
        service.run_task(task_id)
    assert len(fake.sends) == 1


def test_a_draft_changed_after_approval_is_not_sent(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    service.decide_approval(A, outcome["approval_id"], True)
    fake.draft_body = "Changed"
    with pytest.raises(ToolError):
        service.run_task(task_id)
    assert not fake.sends
    assert store.get_approval(outcome["approval_id"])["status"] == "stale"


def test_an_expired_approval_cannot_be_used(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    service.decide_approval(A, outcome["approval_id"], True)
    with store.connect() as conn:
        conn.execute("UPDATE approvals SET expires_at=1")
    with pytest.raises(ToolError):
        service.run_task(task_id)
    assert not fake.sends


def test_rejected_action_never_runs(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    service.decide_approval(A, outcome["approval_id"], False)
    assert store.get_task(task_id)["status"] == "cancelled"
    with pytest.raises(ToolError):
        service.run_task(task_id)
    assert not fake.sends


def test_a_timed_out_send_is_uncertain_and_not_retried(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    task_id, outcome = run(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    service.decide_approval(A, outcome["approval_id"], True)
    real = gmail.invoke
    monkeypatch.setattr(gmail, "invoke", lambda *a: (_ for _ in ()).throw(ToolError("timeout", "slow")))
    with pytest.raises(ToolError) as caught:
        service.run_task(task_id)
    assert caught.value.kind == "uncertain"
    assert store.get_approval(outcome["approval_id"])["status"] == "uncertain"
    monkeypatch.setattr(gmail, "invoke", real)
    with pytest.raises(ToolError):
        service.run_task(task_id)
    assert not fake.sends


def test_paused_business_and_agent_block_calls(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A)
    store.set_paused(A, True)
    with pytest.raises(ToolError) as caught:
        run(A, "email", "gmail.search_messages", {"query": "x"})
    assert caught.value.kind == "paused"
    store.set_paused(A, False)
    store.set_paused(A, True, "email")
    with pytest.raises(ToolError):
        run(A, "email", "gmail.search_messages", {"query": "x"})
    assert not fake.calls


def test_missing_scope_is_refused_before_the_network(monkeypatch):
    fake = FakeGmail(monkeypatch)
    connect_gmail(A, scopes=[registry.GMAIL_READ])
    with pytest.raises(ToolError) as caught:
        run(A, "email", "gmail.create_draft", {"to": "x@y.z", "subject": "s", "body": "b"})
    assert caught.value.kind == "permission"
    assert not fake.calls


def test_expired_sign_in_becomes_a_visible_state(monkeypatch):
    connect_gmail(A)
    store.update_tokens(A, "gmail", {"access_token": "old", "refresh_token": "r"}, time.time() - 10)
    store.save_oauth_app("google", "id", "secret")
    monkeypatch.setattr(http_client, "request_json", lambda *a, **k: (_ for _ in ()).throw(ToolError("rejected", "invalid_grant")))
    with pytest.raises(ToolError):
        run(A, "email", "gmail.search_messages", {"query": "x"})
    assert store.get_connection(A, "gmail")["status"] == "unauthorized"


def test_audit_never_keeps_a_token_in_detail(monkeypatch):
    store.audit(A, actor="user", decision="x", detail="failed with sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in store.list_audit(A)[0]["detail"]


# ── OAuth ───────────────────────────────────────────────────────────────────────

def _google_ok(method, url, *, form=None, body=None, token="", allow_empty=False):
    if url.endswith("/token"):
        return {"access_token": "acc", "refresh_token": "ref", "expires_in": 3600,
                "scope": f"{registry.GMAIL_READ} {registry.GMAIL_COMPOSE}"}
    return {"emailAddress": "owner@example.com"}


def _state_of(url):
    from urllib.parse import parse_qs, urlsplit
    return parse_qs(urlsplit(url).query)


def test_sign_in_stores_on_the_business_that_started_it(monkeypatch):
    store.save_oauth_app("google", "id", "secret")
    monkeypatch.setattr(http_client, "request_json", _google_ok)
    query = _state_of(oauth.start(A, "gmail", "https://h", "cookie"))
    assert query["access_type"] == ["offline"] and query["redirect_uri"] == ["https://h" + oauth.CALLBACK_PATH]
    assert registry.GMAIL_READ in query["scope"][0] and "gmail.send" not in query["scope"][0]
    oauth.finish(query["state"][0], "code", "cookie")
    assert store.get_connection(A, "gmail")["account_label"] == "owner@example.com"
    assert store.get_connection(B, "gmail") is None


def test_state_is_single_use_and_tied_to_the_session(monkeypatch):
    store.save_oauth_app("google", "id", "secret")
    monkeypatch.setattr(http_client, "request_json", _google_ok)
    first = _state_of(oauth.start(A, "gmail", "https://h", "cookie"))["state"][0]
    with pytest.raises(store.StoreError):
        oauth.finish(first, "code", "someone-else")
    with pytest.raises(store.StoreError):
        oauth.finish(first, "code", "cookie")
    second = _state_of(oauth.start(A, "gmail", "https://h", "cookie"))["state"][0]
    oauth.finish(second, "code", "cookie")
    with pytest.raises(store.StoreError):
        oauth.finish(second, "code", "cookie")


def test_expired_state_is_refused():
    store.save_oauth_state("s", A, "gmail", "https://h/cb", oauth.session_hash("c"), ttl=-1)
    with pytest.raises(store.StoreError):
        oauth.finish("s", "code", "c")


def test_partial_consent_shows_degraded(monkeypatch):
    store.save_oauth_app("google", "id", "secret")

    def partial(method, url, **kw):
        result = _google_ok(method, url, **kw)
        if url.endswith("/token"):
            result["scope"] = registry.GMAIL_READ
        return result

    monkeypatch.setattr(http_client, "request_json", partial)
    oauth.finish(_state_of(oauth.start(A, "gmail", "https://h", "c"))["state"][0], "code", "c")
    assert store.get_connection(A, "gmail")["status"] == "degraded"


def test_threads_sign_in_exchanges_for_a_long_lived_token_and_strips_meta_suffix(monkeypatch):
    store.save_oauth_app("threads", "id", "secret")
    seen = []

    def fake(method, url, *, form=None, token="", **kw):
        seen.append((url, form))
        if url.endswith("/oauth/access_token"):
            return {"access_token": "short", "user_id": 1}
        if "th_exchange_token" in url:
            return {"access_token": "long", "expires_in": 5183944}
        return {"id": "9", "username": "brand"}

    monkeypatch.setattr(http_client, "request_json", fake)
    oauth.finish(_state_of(oauth.start(A, "threads", "https://h", "c"))["state"][0], "abc#_", "c")
    assert seen[0][1]["code"] == "abc"
    connection = store.get_connection(A, "threads")
    assert connection["account_label"] == "@brand"
    assert store.connection_tokens(A, "threads")["access_token"] == "long"


def test_cancelled_sign_in_is_reported_and_consumes_state():
    store.save_oauth_state("s", A, "gmail", "https://h/cb", oauth.session_hash("c"))
    assert office_http.finish_oauth("error=access_denied&state=s", "c") == "/#office/integrations"
    assert store.take_oauth_state("s") is None
    assert office_http.overview(A, "https://h")["oauth_failure"]


def test_http_client_refuses_other_hosts():
    with pytest.raises(ToolError) as caught:
        http_client.request_json("GET", "https://evil.example.com/x", token="t")
    assert caught.value.kind == "denied"


def test_disconnect_forgets_tokens_even_if_revoke_fails(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(http_client, "request_json", lambda *a, **k: (_ for _ in ()).throw(ToolError("timeout", "x")))
    oauth.disconnect(A, "gmail")
    assert store.get_connection(A, "gmail") is None
    assert store.list_audit(A)[0]["outcome"] == "revoke_failed"


# ── Obsidian ────────────────────────────────────────────────────────────────────

def test_search_sees_only_granted_folders(vault):
    grant(A, vault, "01 Projects/Temani", can_search=True)
    grant(B, vault, "01 Projects/Cafe", can_search=True)
    _id, found = run(A, "documents", "obsidian.search_notes", {"query": "line"})
    assert [row["title"] for row in found["result"]["notes"]] == ["Plan"]
    _id, none = run(A, "documents", "obsidian.search_notes", {"query": "cafe secret"})
    assert none["result"]["notes"] == []


def test_folder_prefix_is_not_a_grant_on_a_sibling(vault):
    (vault / "01 Projects" / "Temani Private").mkdir()
    (vault / "01 Projects" / "Temani Private" / "x.md").write_text("line\n")
    grant(A, vault, "01 Projects/Temani", can_search=True, can_read=True)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani Private/x.md"})


def test_an_ungranted_agent_is_refused(vault):
    grant(A, vault, "01 Projects/Temani", agent="email", can_read=True)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani/Plan.md"})


def test_each_operation_needs_its_own_flag(vault):
    grant(A, vault, "01 Projects/Temani", can_read=True)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.create_note", {"folder": "01 Projects/Temani", "title": "N", "body": "b"})


def test_another_vault_inherits_nothing(vault, tmp_path, monkeypatch):
    grant(A, vault, "01 Projects/Temani", can_read=True)
    other = (tmp_path / "other").resolve()
    (other / "01 Projects" / "Temani").mkdir(parents=True)
    (other / "01 Projects" / "Temani" / "Plan.md").write_text("x\n")
    monkeypatch.setattr(notebook_vault, "_root", lambda: other)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani/Plan.md"})


@pytest.mark.parametrize("path", ["../outside.md", "01 Projects/Temani/../Cafe/Stock.md", "/etc/passwd.md"])
def test_traversal_is_refused(vault, path):
    grant(A, vault, "01 Projects/Temani", can_read=True)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.read_note", {"path": path})


def test_symlink_escape_is_refused(vault, tmp_path):
    (tmp_path / "out.md").write_text("private\n")
    (vault / "01 Projects" / "Temani" / "link.md").symlink_to(tmp_path / "out.md")
    grant(A, vault, "01 Projects/Temani", can_read=True, can_search=True)
    with pytest.raises(ToolError):
        run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani/link.md"})
    _id, found = run(A, "documents", "obsidian.search_notes", {"query": "private"})
    assert found["result"]["notes"] == []


def test_edit_keeps_everything_else_byte_for_byte(vault):
    grant(A, vault, "01 Projects/Temani", can_read=True, can_edit=True)
    path = vault / "01 Projects" / "Temani" / "Plan.md"
    before = path.read_bytes()
    _id, read = run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani/Plan.md"})
    assert path.read_bytes() == before, "reading must not write"
    run(A, "documents", "obsidian.edit_note", {"path": "01 Projects/Temani/Plan.md", "expected_revision": read["result"]["source"]["revision"],
                                               "find": "Intro", "replace": "Opening"})
    assert path.read_bytes() == before.replace(b"Intro", b"Opening")


def test_concurrent_edit_is_a_conflict_not_an_overwrite(vault):
    grant(A, vault, "01 Projects/Temani", can_read=True, can_edit=True)
    path = vault / "01 Projects" / "Temani" / "Plan.md"
    _id, read = run(A, "documents", "obsidian.read_note", {"path": "01 Projects/Temani/Plan.md"})
    path.write_text(path.read_text(encoding="utf-8") + "from obsidian\n", encoding="utf-8")
    with pytest.raises(ToolError) as caught:
        run(A, "documents", "obsidian.edit_note", {"path": "01 Projects/Temani/Plan.md", "expected_revision": read["result"]["source"]["revision"],
                                                   "find": "Intro", "replace": "X"})
    assert caught.value.kind == "conflict"
    assert "from obsidian" in path.read_text(encoding="utf-8") and "Intro" in path.read_text(encoding="utf-8")


def test_create_never_overwrites(vault):
    grant(A, vault, "01 Projects/Temani", can_create=True)
    with pytest.raises(ToolError) as caught:
        run(A, "documents", "obsidian.create_note", {"folder": "01 Projects/Temani", "title": "Plan", "body": "new"})
    assert caught.value.kind == "conflict"
    assert "Intro" in (vault / "01 Projects" / "Temani" / "Plan.md").read_text(encoding="utf-8")


def test_a_grant_must_name_a_real_vault_folder(vault):
    with pytest.raises(store.StoreError):
        office_http.handle_post("vault/grants/add", {"business_id": A, "folder": "../x"}, "https://h", "")
    with pytest.raises(store.StoreError):
        office_http.handle_post("vault/grants/add", {"business_id": A, "folder": "missing"}, "https://h", "")


# ── runtime ─────────────────────────────────────────────────────────────────────

def _settle(threads):
    for thread in threads:
        thread.join(5)


def test_independent_tasks_run_concurrently_within_the_limit(monkeypatch):
    connect_gmail(A)
    store.update_settings(A, {"max_parallel": 2, "max_parallel_per_agent": 2, "max_parallel_per_provider": 2})
    release, active, peak = threading.Event(), [0], [0]
    lock = threading.Lock()

    def slow(*args):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        release.wait(5)
        with lock:
            active[0] -= 1
        return {}

    monkeypatch.setattr(gmail, "invoke", slow)
    for _ in range(3):
        store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    started = runtime.tick()
    assert len(started) == 2
    time.sleep(0.2)
    assert peak[0] == 2
    release.set()
    _settle(started)
    _settle(runtime.tick())
    assert all(task["status"] == "completed" for task in store.list_tasks(A))


def test_dependencies_hold_a_task_until_they_finish(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: {})
    first = store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    second = store.create_task(A, "email", "gmail.search_messages", {"query": "y"}, depends_on=[first["id"]])
    _settle(runtime.tick())
    assert store.get_task(second["id"])["status"] == "waiting_dependency"
    _settle(runtime.tick())
    assert store.get_task(second["id"])["status"] in ("queued", "assigned", "running", "completed")


def test_a_failed_dependency_cancels_the_dependent(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: (_ for _ in ()).throw(ToolError("not_found", "no")))
    first = store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    second = store.create_task(A, "email", "gmail.search_messages", {"query": "y"}, depends_on=[first["id"]])
    _settle(runtime.tick())
    runtime.tick()
    assert store.get_task(second["id"])["status"] == "cancelled"


def test_rate_limit_retries_read_with_backoff(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: (_ for _ in ()).throw(ToolError("rate_limited", "slow", retry_after=60)))
    task = store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    _settle(runtime.tick())
    fresh = store.get_task(task["id"])
    assert fresh["status"] == "queued" and fresh["retries"] == 1 and fresh["not_before"] > time.time() + 50


def test_write_is_not_retried(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: (_ for _ in ()).throw(ToolError("timeout", "slow")))
    task = store.create_task(A, "email", "gmail.create_draft", {"to": "a@b.c", "subject": "s", "body": "b"})
    _settle(runtime.tick())
    assert store.get_task(task["id"])["status"] == "failed"


def test_restart_retries_reads_and_flags_writes():
    read = store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    write = store.create_task(A, "email", "gmail.create_draft", {"to": "a@b.c", "subject": "s", "body": "b"})
    waiting = store.create_task(A, "email", "gmail.send_draft", {"draft_id": "d1"})
    store.update_task(read["id"], status="running")
    store.update_task(write["id"], status="running")
    store.update_task(waiting["id"], status="waiting_approval")
    runtime.recover()
    assert store.get_task(read["id"])["status"] == "queued"
    flagged = store.get_task(write["id"])
    assert flagged["status"] == "failed" and flagged["needs_review"]
    assert store.get_task(waiting["id"])["status"] == "waiting_approval"


def test_paused_business_keeps_its_queue_waiting(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: {})
    store.set_paused(A, True)
    task = store.create_task(A, "email", "gmail.search_messages", {"query": "x"})
    assert runtime.tick() == []
    assert store.get_task(task["id"])["status"] == "queued"


def test_schedule_runs_once_per_slot(monkeypatch):
    connect_gmail(A)
    monkeypatch.setattr(gmail, "invoke", lambda *a: {})
    schedule = store.create_schedule(A, "email", "Inbox check", "gmail.search_messages", {"query": "x"}, 15)
    due = schedule["next_run_at"] + 1
    _settle(runtime.tick(due))
    _settle(runtime.tick(due))
    assert len(store.list_tasks(A)) == 1


def test_only_reads_can_be_scheduled():
    with pytest.raises(store.StoreError):
        store.create_schedule(A, "email", "x", "gmail.send_draft", {"draft_id": "d"}, 15)


def test_seeded_businesses_survive_reopen():
    assert [row["id"] for row in store.list_businesses()] == ["saas-temani", "saas-ai-honeypot", "cafe"]
    store.create_business("New Shop")
    store._READY.clear()
    assert len(store.list_businesses()) == 4
