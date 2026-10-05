"""Public posting APIs of application-tracking sites."""

from __future__ import annotations

import pytest

from api.job_os.ats_api import ats_posting, canonical_posting_url

U = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class NotFound(Exception):
    def __str__(self):
        return "HTTP 404"


def fetcher(answers):
    calls = []

    def fetch(url):
        calls.append(url)
        value = answers.get(url.split("?")[0])
        if value is None:
            raise NotFound()
        return value
    return fetch, calls


def test_greenhouse_reads_the_job_api_and_404_is_closed():
    fetch, calls = fetcher({"https://boards-api.greenhouse.io/v1/boards/affirm/jobs/1": {
        "title": "Staff Engineer", "company_name": "Affirm", "location": {"name": "Remote Canada"},
        "content": "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;",
        "pay_input_ranges": [{"min_cents": 15000000, "max_cents": 20000000, "currency_type": "CAD"}]}})
    kind, job = ats_posting("https://boards.greenhouse.io/affirm/jobs/1", fetch, {})
    assert kind == "posting" and (job["company"], job["workplace"], job["salary_text"], job["description"]) == \
        ("Affirm", "remote", "CAD 150,000–200,000", "Build & ship")
    assert ats_posting("https://boards.greenhouse.io/affirm/jobs/2", fetch, {}) == ("closed", None)


def test_ashby_board_is_fetched_once_and_unknown_ids_are_closed():
    fetch, calls = fetcher({"https://api.ashbyhq.com/posting-api/job-board/Silver": {"jobs": [
        {"id": U, "title": "Backend Engineer", "location": "Argentina", "isRemote": True, "workplaceType": "Remote",
         "employmentType": "FullTime", "publishedAt": "2026-09-18", "descriptionHtml": "<p>Python</p>",
         "compensation": {"compensationTierSummary": "$60K – $80K"}}]}})
    cache = {}
    kind, job = ats_posting(f"https://jobs.ashbyhq.com/Silver/{U}", fetch, cache)
    assert kind == "posting" and (job["workplace"], job["salary_text"], job["employment_type"]) == ("remote", "$60K – $80K", "Full time")
    assert ats_posting(f"https://jobs.ashbyhq.com/Silver/{U.replace('a', 'f')}", fetch, cache) == ("closed", None)
    assert len(calls) == 1


def test_workable_and_smartrecruiters():
    fetch, _ = fetcher({
        "https://apply.workable.com/api/v1/widget/accounts/gramian": {"name": "Gramian", "jobs": [
            {"shortcode": "ABC123", "title": "Python Dev", "country": "France", "telecommuting": True,
             "employment_type": "Full-time", "published_on": "2026-09-29", "description": "<p>Hi</p>"}]},
        "https://api.smartrecruiters.com/v1/companies/Rave1/postings/92298649": {
            "name": "Software Engineer", "company": {"name": "Rave"}, "typeOfEmployment": {"label": "Full-time"},
            "location": {"city": "Portland", "region": "OR", "country": "us", "remote": False, "hybrid": True},
            "jobAd": {"sections": {"jobDescription": {"text": "<p>Code</p>"}, "qualifications": {"text": "<li>Python</li>"}}}},
    })
    kind, job = ats_posting("https://apply.workable.com/gramian/j/ABC123", fetch, {})
    assert kind == "posting" and job["location"] == "Remote (France)" and job["company"] == "Gramian"
    assert ats_posting("https://apply.workable.com/gramian/j/ZZZ999", fetch, {}) == ("closed", None)
    kind, job = ats_posting("https://jobs.smartrecruiters.com/Rave1/92298649-software-engineer", fetch, {})
    assert kind == "posting" and job["workplace"] == "hybrid" and job["location"] == "Portland, OR, US"
    assert "Code" in job["description"] and "• Python" in job["description"]


def test_other_sites_are_left_to_the_page_reader_and_apply_links_are_trimmed():
    assert ats_posting(f"https://jobs.lever.co/acme/{U}", lambda u: pytest.fail("no API"), {}) == ("unsupported", None)
    assert canonical_posting_url(f"https://jobs.lever.co/acme/{U}/apply") == f"https://jobs.lever.co/acme/{U}"
    assert canonical_posting_url(f"https://jobs.ashbyhq.com/acme/{U}/application") == f"https://jobs.ashbyhq.com/acme/{U}"
