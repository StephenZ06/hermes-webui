"""Point-of-use URL policy for job pages Firecrawl is asked to fetch."""

from __future__ import annotations

import socket

import pytest

from api.job_os.network_policy import UnsafeJobUrl, validate_external_job_url


def _resolver(mapping):
    def resolve(host, *_args, **_kwargs):
        if host not in mapping:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in mapping[host]]
    return resolve


PUBLIC = _resolver({"boards.greenhouse.io": ["104.18.1.1"], "jobs.lever.co": ["52.1.2.3"]})


def test_public_https_job_page_is_accepted_and_normalised():
    url = validate_external_job_url("HTTPS://Boards.Greenhouse.io/acme/jobs/123#apply", resolve=PUBLIC)
    assert url == "https://boards.greenhouse.io/acme/jobs/123"


@pytest.mark.parametrize("bad", [
    "ftp://jobs.lever.co/acme",
    "javascript:alert(1)",
    "https://user:pass@jobs.lever.co/acme",
    "https://",
    "not a url",
    "https://jobs.lever.co/" + "a" * 2100,
])
def test_malformed_credentialed_and_non_http_urls_are_rejected(bad):
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url(bad, resolve=PUBLIC)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.18.80", "169.254.169.254", "100.64.0.1", "::1", "fc00::1"])
def test_hosts_that_resolve_to_internal_addresses_are_rejected(ip):
    resolve = _resolver({"evil.example": [ip]})
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url("https://evil.example/job", resolve=resolve)


def test_literal_internal_ip_is_rejected_without_dns():
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url("http://127.0.0.1:3002/v1/scrape", resolve=PUBLIC)


def test_any_internal_address_among_several_is_rejected():
    resolve = _resolver({"mixed.example": ["104.18.1.1", "10.1.1.1"]})
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url("https://mixed.example/job", resolve=resolve)


def test_resolution_happens_at_every_call_not_once():
    answers = iter([["104.18.1.1"], ["127.0.0.1"]])

    def rebinding(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in next(answers)]

    assert validate_external_job_url("https://rebind.example/a", resolve=rebinding)
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url("https://rebind.example/a", resolve=rebinding)


def test_unresolvable_host_is_rejected():
    with pytest.raises(UnsafeJobUrl):
        validate_external_job_url("https://nowhere.invalid/job", resolve=PUBLIC)
