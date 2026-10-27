"""Follow-up drafts for quiet applications, the two-follow-up cap and the
stale sweep."""

from __future__ import annotations

import json
import time

import pytest

from api.job_os import applications, followup, llm
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import get_job
from tests.test_job_os_gates import _job
from tests.test_job_os_tailor import store  # noqa: F401 - shared fixture

DAY = 86400
BODY = ("Hello, I applied for the Data Analyst role two weeks ago and remain keen. My SQL reporting work for the "
        "finance team matches what you described. Could you share where the process stands and the likely timeline "
        "for next steps? Thank you for your time and consideration.")


def _applied(slug, days_ago):
    job = _job(slug)
    applications.mark_applied(job.id)
    then = int(time.time()) - days_ago * DAY
    conn = connect_job_os()
    conn.execute("UPDATE job_events SET created_at=? WHERE job_id=?", (then, job.id))
    conn.commit()
    conn.close()
    return get_job(job.id)


def test_only_applications_waiting_on_a_reply_have_a_follow_up(store):  # noqa: F811
    assert followup.state(_job("fresh")) is None
    quiet, recent = _applied("quiet", 9), _applied("recent", 2)
    assert followup.state(quiet)["due"] is True and followup.state(quiet)["quiet_days"] == 9
    assert followup.state(recent)["due"] is False


def test_a_draft_uses_only_what_was_sent_and_flags_new_numbers(store, monkeypatch):  # noqa: F811
    job = _applied("draft", 10)
    seen = []

    def fake(**kw):
        seen.append(kw["user"])
        return json.dumps({"channel": "email", "subject": "Data Analyst application", "body": BODY + " I grew revenue 73%."})
    monkeypatch.setattr(llm, "_transport", fake)
    out = followup.request(job.id, run_async=False)
    draft = out["draft"]
    assert draft["status"] == "done" and draft["subject"] == "Data Analyst application"
    assert draft["unverified"] == ["73%"]  # not in the resume that was sent
    assert "<<<SENT RESUME" in seen[0]


def test_i_sent_it_restarts_the_clock_and_two_is_the_cap(store, monkeypatch):  # noqa: F811
    job = _applied("cap", 12)
    monkeypatch.setattr(llm, "_transport", lambda **kw: json.dumps({"channel": "email", "subject": "s", "body": BODY}))
    followup.request(job.id, run_async=False)
    after = followup.mark_sent(job.id)
    assert after["sent"] == 1 and after["quiet_days"] == 0 and after["due"] is False
    # The board's follow-up nudge restarts too.
    card = next(c for col in applications.board()["columns"] for c in col["jobs"] if c["id"] == job.id)
    assert not any("follow up" in r for r in card["attention"])
    followup.mark_sent(job.id)
    assert followup.state(get_job(job.id))["max_reached"] is True
    with pytest.raises(followup.FollowUpError):
        followup.request(job.id, run_async=False)
    with pytest.raises(followup.FollowUpError):
        followup.mark_sent(job.id)


def test_a_status_change_retires_the_draft(store, monkeypatch):  # noqa: F811
    job = _applied("reply", 10)
    monkeypatch.setattr(llm, "_transport", lambda **kw: json.dumps({"channel": "email", "subject": "s", "body": BODY}))
    followup.request(job.id, run_async=False)
    conn = connect_job_os()
    conn.execute("UPDATE follow_ups SET updated_at=updated_at-100 WHERE job_id=?", (job.id,))
    conn.commit()
    conn.close()
    current = get_job(job.id)
    applications.move_to_column(job.id, "interview", expected_revision=current.revision, payload={"by": "email"})
    assert followup.state(get_job(job.id))["draft"] is None


def test_the_stale_sweep_selects_and_moves_quiet_applications(store):  # noqa: F811
    old, older, fresh = _applied("old", 61), _applied("older", 90), _applied("new", 20)
    listed = [j["id"] for j in followup.stale(60)]
    assert listed == [older.id, old.id]
    assert [j["id"] for j in followup.stale(15)][-1] == fresh.id
    out = followup.sweep([old.id, older.id, "missing"])
    assert out == {"moved": 2, "skipped": 1}
    assert get_job(old.id).status == JobStatus.NO_RESPONSE
    moved = [e for e in applications.timeline(old.id) if e["type"] == "status_changed"][-1]["data"]
    assert moved["by"] == "sweep" and moved["to"] == "no_response"
