"""Job OS's model calls ride out a brief rate limit or outage.

One 429 from the provider used to fail a job's analysis for good ("The AI
model could not be reached (RateLimitError)"). The single transport in
api/job_os/llm.py now retries rate limits, connection drops and server
errors with a short backoff, and still fails at once on anything else.
"""
from __future__ import annotations

import sys
import types

import pytest


class RateLimitError(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429 Too Many Requests")
        self.status_code = 429
        self.response = types.SimpleNamespace(headers={"retry-after": retry_after} if retry_after else {})


class BadRequestError(Exception):
    status_code = 400


def _reply(text):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))])


@pytest.fixture
def transport(monkeypatch):
    from api.job_os import llm

    calls = []
    waits = []
    outcomes = []

    def call_llm(**kwargs):
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _reply(outcome)

    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = []
    aux = types.ModuleType("agent.auxiliary_client")
    aux.call_llm = call_llm
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)
    import api.config
    monkeypatch.setattr(api.config, "keep_server_interpreter_packages", lambda: None, raising=False)
    monkeypatch.setattr(llm, "_sleep", waits.append)

    def run(*results):
        outcomes[:] = list(results)
        return llm._default_transport(system="s", user="u", max_tokens=10, provider="p", model="m", effort="high")

    return run, calls, waits


def test_a_rate_limit_is_retried_and_the_answer_comes_through(transport):
    run, calls, waits = transport
    assert run(RateLimitError(), '{"ok": true}') == '{"ok": true}'
    assert len(calls) == 2 and len(waits) == 1 and waits[0] > 0


def test_retry_after_from_the_provider_is_honoured_within_a_cap(transport):
    run, calls, waits = transport
    run(RateLimitError(retry_after="7"), '{"ok": true}')
    assert waits == [7.0]


def test_a_rate_limit_that_persists_still_fails_with_its_reason(transport):
    from api.job_os.llm import LLMError

    run, calls, waits = transport
    with pytest.raises(LLMError, match="RateLimitError"):
        run(RateLimitError(), RateLimitError(), RateLimitError(), RateLimitError())
    assert len(calls) == 3


def test_a_request_the_provider_rejects_is_not_retried(transport):
    from api.job_os.llm import LLMError

    run, calls, waits = transport
    with pytest.raises(LLMError, match="BadRequestError"):
        run(BadRequestError("bad"), '{"ok": true}')
    assert len(calls) == 1 and waits == []
