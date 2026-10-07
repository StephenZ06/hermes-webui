"""Job OS email: match alerts, daily digest, and reply-to-proceed codes."""

from __future__ import annotations

import time
from dataclasses import replace
from email.message import EmailMessage

import pytest

from api import mailer, profiles
from api.job_os import notify, tailor
from api.job_os.db import connect_job_os
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, get_job, normalize_job_input
from api.job_os.settings import load_settings, save_settings

ME = "me@gmail.com"


def _set(**notifications):
    save_settings({"notifications": notifications}, expected_revision=load_settings()["revision"])


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(mailer, "credentials", lambda: ("hermes.sender@gmail.com", "app-password"))
    # These tests cover the email and its reply codes, so every good match goes out at once.
    _set(email_enabled=True, to_address=ME, min_fit_score=70, release_count=1)
    sent = []
    yield lambda *args: sent.append(args) or args[1], sent


def _analysed(title, score, *, age=0):
    job = create_job(replace(normalize_job_input({"title": title, "company": "Acme", "canonical_url": f"https://jobs.example.test/{title}"}),
                             description="x"), status=JobStatus.SCRAPED)
    job = transition_job(job.id, JobStatus.ANALYZED, expected_revision=job.revision)
    conn = connect_job_os()
    conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at) VALUES (?, 'done', ?, 'good', ?, ?, ?)",
                 (job.id, score, '{"summary": "Fits well."}', int(time.time()) - age, int(time.time()) - age))
    conn.commit()
    conn.close()
    return job


def _reply(body, *, sender=ME, auth="mx.google.com; dkim=pass header.i=@gmail.com; spf=pass; dmarc=pass (p=NONE) header.from=gmail.com"):
    message = EmailMessage()
    if auth:
        message["Authentication-Results"] = auth
    message["Authentication-Results"] = "mx.google.com; dmarc=pass"  # a forged lower header must not count
    message["From"] = f"Me <{sender}>"
    message["Subject"] = "Re: Hermes Jobs: 1 new job match"
    message.set_content(body)
    return bytes(message)


def _codes(body):
    return dict((a.lower(), c) for a, c in notify._COMMAND.findall(body))


def test_match_alert_sends_strong_recent_matches_once(store):
    send, sent = store
    strong = _analysed("Strong", 85)
    _analysed("Weak", 50)
    _analysed("Old", 90, age=5 * 86400)
    assert notify.send_matches(send=send) == 1
    _context, to, subject, body = sent[0]
    assert to == ME and "Strong" in subject and "Weak" not in body and "Old" not in body
    assert set(_codes(body)) == {"tailor", "skip"}
    assert notify.send_matches(send=send) == 0  # never twice for the same job
    assert {e["type"] for e in __import__("api.job_os.applications", fromlist=["timeline"]).timeline(strong.id)} >= {"match_released", "match_notified"}


def test_without_email_matches_are_still_released_in_jobs(store):
    send, sent = store
    _set(email_enabled=False)
    job = _analysed("Strong", 85)
    assert notify.send_matches(send=send) == 1 and sent == []
    assert [j["id"] for j in notify.inbox()["released"]] == [job.id]


def _at(text):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kuala_Lumpur")).timestamp())


def test_good_matches_wait_for_five_or_the_evening_cutoff(store, monkeypatch):
    send, sent = store
    _set(release_count=5, release_cutoff_hour=20, min_fit_score=65)
    monkeypatch.setattr(time, "time", lambda: _at("2026-10-07 14:00"))
    for i, score in enumerate((90, 80, 70, 66)):
        _analysed(f"Good{i}", score)
    _analysed("Weak", 60)
    box = notify.inbox()
    assert box["waiting"] == 4 and box["released"] == []
    assert notify.send_matches(send=send, now=_at("2026-10-07 14:00")) == 0 and sent == []
    _analysed("Good4", 75)
    assert notify.send_matches(send=send, now=_at("2026-10-07 14:01")) == 5
    _context, _to, subject, body = sent[0]
    assert subject.startswith("5 new job matches") and "Weak" not in body
    assert body.index("Good0") < body.index("Good1") < body.index("Good2"), "best match first"
    released = notify.inbox()["released"]
    assert [j["fit_score"] for j in released] == [90, 80, 75, 70, 66]
    # One more good match waits; the 20:00 cut-off sends it, once that day.
    _analysed("Late", 88)
    assert notify.send_matches(send=send, now=_at("2026-10-07 19:59")) == 0
    assert notify.send_matches(send=send, now=_at("2026-10-07 20:00")) == 1
    _analysed("Later", 89)
    assert notify.send_matches(send=send, now=_at("2026-10-07 21:00")) == 0, "one cut-off release a day"
    assert notify.mark_matches_seen(now=_at("2026-10-07 21:30"))["released"] == []


def test_reply_code_runs_once_and_ignores_quoted_text(store, monkeypatch):
    send, sent = store
    first, second = _analysed("First", 88), _analysed("Second", 80)
    notify.send_matches(send=send)
    body = sent[0][3]
    blocks = body.split("---")
    codes_first = _codes(next(b for b in blocks if "First" in b))
    codes_second = _codes(next(b for b in blocks if "Second" in b))
    started = []
    monkeypatch.setattr(tailor, "request_tailoring", lambda job_id, **k: started.append(job_id))
    quoted = "\n".join("> " + line for line in body.splitlines())
    reply = _reply(f"TAILOR {codes_first['tailor']}\n\nOn Mon, 6 Oct 2026 at 09:00, Hermes Jobs <x@gmail.com> wrote:\n{quoted}\n"
                   f"SKIP {codes_second['skip']}")
    outcomes = notify.handle_message(reply, load_settings())
    assert started == [first.id] and len(outcomes) == 1
    assert get_job(second.id).status == JobStatus.ANALYZED  # quoted/after-quote codes are not commands
    again = notify.handle_message(reply, load_settings())
    assert started == [first.id] and "already used" in again[0]
    assert notify.handle_message(_reply(f"Thanks!\n> SKIP {codes_second['skip']}"), load_settings()) is None
    skip = notify.handle_message(_reply(f"skip {codes_second['skip']}"), load_settings())
    assert get_job(second.id).status == JobStatus.SKIPPED and skip[0].startswith("Skipped")


@pytest.mark.parametrize("kwargs", [
    {"sender": "attacker@example.com"},
    {"auth": "mx.google.com; dkim=fail; spf=softfail; dmarc=fail header.from=gmail.com"},
    {"auth": "mx.google.com; dkim=pass header.i=@gmail.com; spf=pass; dmarc=pass header.from=gmail.com",
     "sender": "Me@Gmail.com.attacker.example"},
])
def test_reply_from_anyone_else_or_unauthenticated_is_ignored(store, monkeypatch, kwargs):
    send, sent = store
    job = _analysed("Target", 90)
    notify.send_matches(send=send)
    code = _codes(sent[0][3])["skip"]
    assert notify.handle_message(_reply(f"SKIP {code}", **kwargs), load_settings()) is None
    assert get_job(job.id).status == JobStatus.ANALYZED
    assert notify.handle_message(_reply(f"SKIP {code}"), load_settings())[0].startswith("Skipped")  # code was not burned


def test_expired_and_wrong_action_codes_do_nothing(store):
    send, sent = store
    _analysed("Target", 90)
    notify.send_matches(send=send)
    codes = _codes(sent[0][3])
    assert notify.redeem_code("tailor", codes["skip"]) is None
    assert notify.redeem_code("skip", codes["skip"], now=int(time.time()) + notify.CODE_TTL + 1) is None


def test_poll_replies_acts_and_confirms(store, monkeypatch):
    send, sent = store
    job = _analysed("Target", 90)
    notify.send_matches(send=send)
    code = _codes(sent[0][3])["skip"]
    calls = []

    def fetch(address, password, from_address, state):
        calls.append((address, from_address))
        return [(7, _reply(f"SKIP {code}")), (8, _reply("thanks!"))], {"imap_uidvalidity": 1, "imap_last_uid": 8}

    assert notify.poll_replies(fetch=fetch, send=send) == 1
    assert calls == [("hermes.sender@gmail.com", ME)]
    assert get_job(job.id).status == JobStatus.SKIPPED
    assert sent[-1][2] == "Done: your reply" and "Skipped Target" in sent[-1][3]
    assert notify.load_state()["imap_last_uid"] == 8


class _FakeImap:
    mailbox = {"uidnext": 41, "messages": {}}
    searches = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def status(self, *a):
        return "OK", [f"INBOX (UIDNEXT {self.mailbox['uidnext']} UIDVALIDITY 9)".encode()]

    def select(self, *a, **k):
        return "OK", [b""]

    def uid(self, command, *args):
        if command == "SEARCH":
            self.searches.append(args)
            return "OK", [" ".join(str(u) for u in self.mailbox["messages"]).encode()]
        return "OK", [(b"1 (BODY[] {3}", self.mailbox["messages"][int(args[0])]), b")"]


def test_first_poll_starts_from_now_and_never_reads_old_mail(store, monkeypatch):
    monkeypatch.setattr(notify.imaplib, "IMAP4_SSL", _FakeImap)
    _FakeImap.mailbox = {"uidnext": 41, "messages": {40: b"old"}}
    found, state = notify._imap_fetch("a", "p", ME, {})
    assert found == [] and state == {"imap_uidvalidity": 9, "imap_last_uid": 40}
    _FakeImap.mailbox = {"uidnext": 43, "messages": {40: b"old", 41: b"new", 42: b"newer"}}
    found, state = notify._imap_fetch("a", "p", ME, state)
    assert found == [(41, b"new"), (42, b"newer")] and state["imap_last_uid"] == 42
    assert _FakeImap.searches[-1] == (None, "UID 41:*", "FROM", f'"{ME}"')


def test_digest_once_a_day_after_the_hour(store):
    send, sent = store
    _analysed("Target", 90)
    _set(digest_hour=8)
    morning = time.mktime(time.strptime("2026-10-06 07:30", "%Y-%m-%d %H:%M"))
    later = morning + 3600
    assert notify.maybe_send_digest(now=morning, send=send) is False
    assert notify.maybe_send_digest(now=later, send=send) is True
    assert "Target" in sent[-1][3] and sent[-1][1] == ME
    assert notify.maybe_send_digest(now=later + 60, send=send) is False


def test_empty_digest_is_skipped(store):
    send, sent = store
    assert notify.maybe_send_digest(send=send, force=True) is False and sent == []
    assert notify.recent_log()[0]["status"] == "skipped"
