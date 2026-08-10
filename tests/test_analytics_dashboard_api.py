"""Analytics/cost dashboard API: provider breakdown, week/month bucketing,
top-spending sessions, and CLI (state.db) merge.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Analytics/cost dashboard".
"""
import io
import json
import pathlib
import sqlite3
import sys
import time
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))


class _FakeHandler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO()
        self.headers = {}
        self.request = None

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def json_body(self):
        return json.loads(bytes(self.body).decode("utf-8"))


def _call_analytics(monkeypatch, tmp_path, entries, days="30", granularity="week", now=None, state_db_rows=None):
    import api.routes as routes
    from api import models

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / "_index.json").write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(routes, "SESSION_DIR", session_dir)
    if now is not None:
        monkeypatch.setattr(time, "time", lambda: now)

    if state_db_rows is not None:
        db = tmp_path / "state.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, source TEXT, model TEXT, billing_provider TEXT,
                input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL,
                cache_read_tokens INTEGER, title TEXT, started_at REAL, ended_at REAL
            )
        """)
        for row in state_db_rows:
            conn.execute(
                "INSERT INTO sessions (id, source, model, billing_provider, input_tokens, "
                "output_tokens, estimated_cost_usd, cache_read_tokens, title, started_at, ended_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get("id"), row.get("source", "cli"), row.get("model"),
                    row.get("billing_provider"), row.get("input_tokens", 0),
                    row.get("output_tokens", 0), row.get("estimated_cost_usd", 0.0),
                    row.get("cache_read_tokens", 0), row.get("title", ""),
                    row.get("started_at"), row.get("ended_at"),
                ),
            )
        conn.commit()
        conn.close()
        monkeypatch.setattr(models, "_active_state_db_path", lambda: db)
    else:
        monkeypatch.setattr(models, "_active_state_db_path", lambda: None)

    handler = _FakeHandler()
    parsed = SimpleNamespace(query=f"days={days}&granularity={granularity}")
    routes._handle_analytics(handler, parsed)
    assert handler.status == 200
    return handler.json_body()


def test_empty_state_returns_zeros_without_raising(monkeypatch, tmp_path):
    data = _call_analytics(monkeypatch, tmp_path, [])
    assert data["total_sessions"] == 0
    assert data["total_cost"] == 0
    assert data["total_tokens"] == 0
    assert data["providers"] == []
    assert data["trend"] == []
    assert data["top_sessions"] == []


def test_provider_breakdown_groups_by_model_provider(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    entries = [
        {"session_id": "s1", "updated_at": now, "model": "claude-opus-4", "model_provider": "anthropic",
         "input_tokens": 1000, "output_tokens": 200, "estimated_cost": 1.5, "title": "Session A"},
        {"session_id": "s2", "updated_at": now, "model": "gpt-5.5", "model_provider": "openai",
         "input_tokens": 500, "output_tokens": 100, "estimated_cost": 0.5, "title": "Session B"},
        {"session_id": "s3", "updated_at": now, "model": "claude-sonnet-5", "model_provider": "anthropic",
         "input_tokens": 300, "output_tokens": 50, "estimated_cost": 0.3, "title": "Session C"},
    ]
    data = _call_analytics(monkeypatch, tmp_path, entries, now=now)

    assert data["total_sessions"] == 3
    assert data["total_cost"] == 2.3
    providers = {p["provider"]: p for p in data["providers"]}
    assert set(providers) == {"anthropic", "openai"}
    assert providers["anthropic"]["sessions"] == 2
    assert providers["anthropic"]["cost"] == 1.8
    assert providers["openai"]["sessions"] == 1
    assert providers["openai"]["cost"] == 0.5
    # Shares sum to (approximately) 100 across providers.
    assert sum(p["cost_share"] for p in data["providers"]) in (99, 100, 101)
    # Sorted by cost descending.
    assert data["providers"][0]["provider"] == "anthropic"


def test_provider_derived_from_model_prefix_when_no_explicit_provider(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    entries = [
        {"session_id": "s1", "updated_at": now, "model": "openrouter/some-model",
         "input_tokens": 100, "output_tokens": 10, "estimated_cost": 0.1},
        {"session_id": "s2", "updated_at": now, "model": "unqualified-model",
         "input_tokens": 100, "output_tokens": 10, "estimated_cost": 0.1},
    ]
    data = _call_analytics(monkeypatch, tmp_path, entries, now=now)
    providers = {p["provider"] for p in data["providers"]}
    assert "openrouter" in providers
    assert "unknown" in providers


def test_top_sessions_sorted_desc_and_capped_at_10(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    entries = [
        {"session_id": f"s{i}", "updated_at": now, "model": "m", "model_provider": "p",
         "input_tokens": 10, "output_tokens": 10, "estimated_cost": i * 0.1, "title": f"Session {i}"}
        for i in range(1, 16)
    ]
    data = _call_analytics(monkeypatch, tmp_path, entries, now=now)
    top = data["top_sessions"]
    assert len(top) == 10
    costs = [t["cost"] for t in top]
    assert costs == sorted(costs, reverse=True)
    assert top[0]["cost"] == round(15 * 0.1, 6)
    assert top[0]["title"] == "Session 15"


def test_granularity_day_week_month_produce_distinct_bucket_keys(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    entries = [
        {"session_id": "s1", "updated_at": now, "model": "m", "model_provider": "p",
         "input_tokens": 10, "output_tokens": 10, "estimated_cost": 1.0},
    ]
    day_data = _call_analytics(monkeypatch, tmp_path / "day", entries, granularity="day", now=now)
    week_data = _call_analytics(monkeypatch, tmp_path / "week", entries, granularity="week", now=now)
    month_data = _call_analytics(monkeypatch, tmp_path / "month", entries, granularity="month", now=now)

    assert day_data["granularity"] == "day"
    assert week_data["granularity"] == "week"
    assert month_data["granularity"] == "month"
    assert len(day_data["trend"]) == 1
    assert day_data["trend"][0]["bucket"] == "2026-08-10"
    assert len(week_data["trend"]) == 1
    assert week_data["trend"][0]["bucket"].startswith("2026-W")
    assert len(month_data["trend"]) == 1
    assert month_data["trend"][0]["bucket"] == "2026-08"


def test_invalid_granularity_falls_back_to_week(monkeypatch, tmp_path):
    data = _call_analytics(monkeypatch, tmp_path, [], granularity="fortnight")
    assert data["granularity"] == "week"


def test_invalid_days_defaults_to_30(monkeypatch, tmp_path):
    data = _call_analytics(monkeypatch, tmp_path, [], days="not-a-number")
    assert data["period_days"] == 30


def test_days_clamped_to_365_max(monkeypatch, tmp_path):
    data = _call_analytics(monkeypatch, tmp_path, [], days="9999")
    assert data["period_days"] == 365


def test_cli_sessions_merged_with_billing_provider(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    state_rows = [
        {"id": "cli1", "model": "gpt-5.5", "billing_provider": "openai-codex",
         "input_tokens": 200, "output_tokens": 40, "estimated_cost_usd": 0.8,
         "title": "CLI session", "started_at": now, "ended_at": now, "source": "cli"},
    ]
    data = _call_analytics(monkeypatch, tmp_path, [], now=now, state_db_rows=state_rows)
    assert data["total_sessions"] == 1
    providers = {p["provider"]: p for p in data["providers"]}
    assert "openai-codex" in providers
    assert providers["openai-codex"]["cost"] == 0.8


def test_cli_sessions_with_null_billing_provider_derive_from_model(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    state_rows = [
        {"id": "cli1", "model": "custom/dolphin", "billing_provider": None,
         "input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.0,
         "title": "Local model", "started_at": now, "ended_at": now, "source": "cli"},
    ]
    data = _call_analytics(monkeypatch, tmp_path, [], now=now, state_db_rows=state_rows)
    providers = {p["provider"] for p in data["providers"]}
    assert "custom" in providers


def test_webui_source_rows_excluded_from_cli_merge(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    state_rows = [
        {"id": "w1", "model": "m", "billing_provider": "p", "input_tokens": 10,
         "output_tokens": 10, "estimated_cost_usd": 5.0, "title": "webui dupe",
         "started_at": now, "ended_at": now, "source": "webui"},
    ]
    data = _call_analytics(monkeypatch, tmp_path, [], now=now, state_db_rows=state_rows)
    assert data["total_sessions"] == 0
    assert data["total_cost"] == 0


def test_title_redacted_in_top_sessions(monkeypatch, tmp_path):
    now = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
    entries = [
        {"session_id": "s1", "updated_at": now, "model": "m", "model_provider": "p",
         "input_tokens": 10, "output_tokens": 10, "estimated_cost": 1.0,
         "title": "api_key: sk-ant-verysecrettoken1234567890"},
    ]
    data = _call_analytics(monkeypatch, tmp_path, entries, now=now)
    assert "sk-ant-verysecrettoken1234567890" not in json.dumps(data["top_sessions"])
