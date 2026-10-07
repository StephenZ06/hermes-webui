"""Reading a job posting from a page's schema.org JobPosting data."""

from __future__ import annotations

import json

from api.job_os.extract import extract_job_posting


def _page(*blocks, head_extra=""):
    scripts = "".join(f'<script type="application/ld+json">{b if isinstance(b, str) else json.dumps(b)}</script>' for b in blocks)
    return f"<html><head><title>Careers</title>{head_extra}{scripts}</head><body><h1>Job</h1></body></html>"


POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Senior Backend Engineer",
    "hiringOrganization": {"@type": "Organization", "name": "Acme Robotics"},
    "jobLocation": {"@type": "Place", "address": {"addressLocality": "Berlin", "addressCountry": "DE"}},
    "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR",
                   "value": {"@type": "QuantitativeValue", "minValue": 70000, "maxValue": 90000, "unitText": "YEAR"}},
    "employmentType": ["FULL_TIME"],
    "datePosted": "2026-09-30",
    "description": "<p>Build <b>APIs</b> &amp; services.</p><ul><li>Python</li><li>Postgres</li></ul>",
}


def test_reads_every_field_from_a_plain_jobposting_block():
    job = extract_job_posting(_page(POSTING), "https://jobs.lever.co/acme/123")
    assert job["title"] == "Senior Backend Engineer"
    assert job["company"] == "Acme Robotics"
    assert job["location"] == "Berlin, DE"
    assert job["salary_text"] == "EUR 70,000–90,000 / year"
    assert job["employment_type"] == "Full time"
    assert job["posted_at"] == "2026-09-30"
    assert job["workplace"] == "onsite"
    assert "Build APIs & services." in job["description"] and "• Python" in job["description"]
    assert "<" not in job["description"]


def test_finds_the_posting_inside_a_graph_or_list_and_marks_remote():
    remote = dict(POSTING, jobLocationType="TELECOMMUTE", jobLocation=None,
                  applicantLocationRequirements={"@type": "Country", "name": "Europe"})
    wrapped = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, remote]}
    job = extract_job_posting(_page(wrapped), "https://x.test/j")
    assert job["workplace"] == "remote" and job["location"] == "Remote (Europe)"
    listed = extract_job_posting(_page([{"@type": "Organization"}, dict(POSTING, **{"@type": ["JobPosting"]})]), "https://x.test/j")
    assert listed["title"] == "Senior Backend Engineer"


def test_single_salary_value_and_hourly_unit():
    hourly = dict(POSTING, baseSalary={"currency": "USD", "value": {"value": 45, "unitText": "HOUR"}})
    assert extract_job_posting(_page(hourly), "https://x.test/j")["salary_text"] == "USD 45 / hour"


def test_hybrid_is_detected_from_the_text():
    hybrid = dict(POSTING, title="Engineer (Hybrid)")
    assert extract_job_posting(_page(hybrid), "https://x.test/j")["workplace"] == "hybrid"


def test_pages_without_a_posting_or_with_broken_json_return_none():
    assert extract_job_posting(_page({"@type": "Organization", "name": "Acme"}), "https://x.test") is None
    assert extract_job_posting(_page("{not json"), "https://x.test") is None
    assert extract_job_posting("<html></html>", "https://x.test") is None
    assert extract_job_posting(_page(dict(POSTING, title="")), "https://x.test") is None


def test_description_is_capped():
    long = dict(POSTING, description="<p>" + "word " * 20000 + "</p>")
    assert len(extract_job_posting(_page(long), "https://x.test")["description"]) <= 20000


def test_location_requirement_lists_are_joined():
    remote = dict(POSTING, jobLocationType="TELECOMMUTE", jobLocation=None,
                  applicantLocationRequirements=[{"@type": "Country", "name": "Argentina"}, {"@type": "Country", "name": "Chile"}])
    assert extract_job_posting(_page(remote), "https://x.test/j")["location"] == "Remote (Argentina, Chile)"


def test_indeed_click_links_are_postings_and_results_pages_are_not():
    from api.job_os.extract import indeed_job_key, looks_like_single_posting
    assert looks_like_single_posting("https://malaysia.indeed.com/rc/clk?jk=ab12&bb=x")
    assert not looks_like_single_posting("https://malaysia.indeed.com/q-backend-jobs.html")
    assert not looks_like_single_posting("https://www.indeed.com/jobs?q=backend")
    assert indeed_job_key("https://malaysia.indeed.com/rc/clk?jk=ab12&bb=x") == "ab12"
    assert indeed_job_key("https://malaysia.indeed.com/cmp/Acme") is None
    assert indeed_job_key("https://evilindeed.com/rc/clk?jk=ab12") is None
