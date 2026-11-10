"""The usage card's response accepts a window's reset time as a datetime or as
the ISO text the per-profile probe returns (used while a scheduled job holds
the cron lock); text used to crash the request and hide the card."""

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from api import routes


class _Handler:
    def __init__(self):
        self.status, self.headers, self.wfile = None, {}, io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass


def _render(reset_at):
    handler = _Handler()
    snapshot = SimpleNamespace(provider="openai-codex", plan=None, unavailable_reason=None, windows=(
        SimpleNamespace(label="Session", used_percent=5.0, reset_at=reset_at, detail=None),))
    routes._render_account_usage_response(handler, snapshot)
    return handler.status, json.loads(handler.wfile.getvalue())


def test_a_probe_reset_time_given_as_text_is_served():
    status, body = _render("2026-11-10T13:00:00+00:00")
    assert status == 200 and body["available"] is True
    assert body["windows"][0]["reset_at"] == "2026-11-10T13:00:00+00:00"
    assert _render("2026-11-10T13:00:00Z")[1]["windows"][0]["reset_at"] == "2026-11-10T13:00:00+00:00"


def test_datetimes_still_work_and_unreadable_text_drops_only_the_reset_time():
    when = datetime(2026, 11, 10, 13, tzinfo=timezone.utc)
    assert _render(when)[1]["windows"][0]["reset_at"] == when.isoformat()
    status, body = _render("soon")
    assert status == 200 and body["windows"][0]["reset_at"] is None and body["windows"][0]["used_percent"] == 5.0
