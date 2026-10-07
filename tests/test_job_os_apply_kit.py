"""Apply kit: Luna's ready-to-paste screening answers from the job, the master
resume and the person's standard answers."""

from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os import apply_kit, llm, resume
from api.job_os.models import JobStatus
from api.job_os.repository import create_job, normalize_job_input
from api.job_os.settings import load_settings, save_settings

MASTER = "# Jane Doe\n## Experience\n- SOC analyst for 3 years: Splunk, QRadar, incident triage.\n" + "Monitored alerts. " * 20


class _H:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile, self.wfile, self.status = io.BytesIO(raw), io.BytesIO(), None

    def send_response(self, s):
        self.status = s

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    seen = {}

    def transport(**kw):
        seen.update(kw)
        return json.dumps({"answers": [{"question": "What is your notice period?", "answer": "One month."},
                                       {"question": "What are your salary expectations?", "answer": "QAR 15,000 a month."},
                                       {"question": "", "answer": "dropped"}]})
    monkeypatch.setattr(llm, "_transport", transport)
    return seen


_IDS = __import__("itertools").count(5459822)


def _job(description="Monitor SIEM alerts; Splunk required."):
    return create_job(normalize_job_input({"title": "SOC Analyst", "company": "Ooredoo", "country": "Qatar", "description": description,
                                           "canonical_url": f"https://www.bayt.com/en/qatar/jobs/soc-analyst-{next(_IDS)}/"}),
                      status=JobStatus.SCRAPED)


def test_the_kit_uses_the_stated_answers_resume_and_job(store):
    resume.save_resume(filename="cv.md", text=MASTER)
    save_settings({"apply": {"notice_period": "One month", "expected_salary": "Qatar: QAR 15,000/month; Malaysia: RM 8,000/month"}},
                  expected_revision=load_settings()["revision"])
    job = _job()
    kit = apply_kit.request(job.id, run_async=False)
    assert kit["status"] == "done"
    assert kit["answers"] == [{"question": "What is your notice period?", "answer": "One month."},
                              {"question": "What are your salary expectations?", "answer": "QAR 15,000 a month."}]
    prompt = store["user"]
    assert "Notice period: One month" in prompt and "QAR 15,000/month" in prompt and "Job country: Qatar" in prompt
    assert "Splunk, QRadar" in prompt and "Monitor SIEM alerts" in prompt
    assert "Relocation:" not in prompt, "blank answers are left out"
    assert all(q in prompt for q in apply_kit.QUESTIONS)
    assert "never invent" in store["system"] and "Not provided — fill in before sending" in store["system"]


def test_the_kit_needs_a_description_and_a_resume_and_survives_a_failure(store, monkeypatch):
    with pytest.raises(apply_kit.ApplyKitError, match="description"):
        apply_kit.request(_job(description="").id, run_async=False)
    job = _job()
    with pytest.raises(apply_kit.ApplyKitError, match="master resume"):
        apply_kit.request(job.id, run_async=False)
    resume.save_resume(filename="cv.md", text=MASTER)
    monkeypatch.setattr(llm, "_transport", lambda **kw: "not json")
    kit = apply_kit.request(job.id, run_async=False)
    assert kit["status"] == "failed" and kit["error"]


def test_route_and_job_detail_carry_the_kit(store):
    resume.save_resume(filename="cv.md", text=MASTER)
    job = _job()
    h = _H()
    routes.handle_post(h, urlparse(f"/api/job-os/jobs/{job.id}/apply-kit"))
    assert h.status == 200 and json.loads(h.wfile.getvalue())["apply_kit"]["status"] in ("running", "done")
    import time
    for _ in range(50):
        if apply_kit.get_kit(job.id)["status"] == "done":
            break
        time.sleep(0.05)
    d = _H()
    routes.handle_get(d, urlparse(f"/api/job-os/jobs/{job.id}"))
    assert json.loads(d.wfile.getvalue())["job"]["apply_kit"]["answers"][0]["answer"] == "One month."


def test_settings_validate_the_application_answers(store):
    from api.job_os.settings import SettingsError
    with pytest.raises(SettingsError):
        save_settings({"apply": {"notice_period": "x" * 500}}, expected_revision=0)
    saved = save_settings({"apply": {"other": "Line one\nLine two"}}, expected_revision=0)
    assert saved["apply"]["other"] == "Line one\nLine two"
