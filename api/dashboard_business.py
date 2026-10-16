"""Business dashboard: sales from Lemon Squeezy or Gumroad (or entered by hand),
goals such as "5 sales this week", and milestones that unlock as the numbers
grow.

The platform key lives in the active profile's env files (like the Apify
token), is checked with the platform before it is saved, and never leaves the
server: responses only say whether a platform is connected. Sales are copied
into ``dashboard.db`` and refreshed at most every ``SYNC_EVERY`` seconds when
the page is read, so the page works (from the last copy) when the platform is
unreachable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from api.dashboard_game import GameError, _LOCK, _connect, _insert

logger = logging.getLogger(__name__)

PLATFORMS = {
    "lemonsqueezy": {"label": "Lemon Squeezy", "env": "SALES_LEMONSQUEEZY_API_KEY", "api": "https://api.lemonsqueezy.com/v1"},
    "gumroad": {"label": "Gumroad", "env": "SALES_GUMROAD_ACCESS_TOKEN", "api": "https://api.gumroad.com/v2"},
}
SYNC_EVERY = 300
MAX_PAGES = 30
_MAX_BODY = 4 * 1024 * 1024
SALE_XP = 25
MILESTONE_XP = 100
GOAL_METRICS = ("sales", "revenue")
GOAL_PERIODS = ("week", "month")

# (key, title, description, test(stats) -> bool). Order is display order.
MILESTONES: list[tuple[str, str, str, Callable[[dict], bool]]] = [
    ("first_sale", "First Sale", "Someone paid for what you made", lambda s: s["sales"] >= 1),
    ("revenue_100", "First $100", "100 in revenue", lambda s: s["revenue"] >= 100_00),
    ("first_subscriber", "First Subscriber", "A recurring customer", lambda s: s["subscribers"] >= 1),
    ("customers_10", "10 Customers", "Ten people bought", lambda s: s["customers"] >= 10),
    ("revenue_1k", "First $1k", "1,000 in revenue", lambda s: s["revenue"] >= 1_000_00),
    ("mrr_500", "$500 MRR", "500 a month, recurring", lambda s: s["mrr"] >= 500_00),
    ("mrr_1k", "$1k MRR", "1,000 a month, recurring", lambda s: s["mrr"] >= 1_000_00),
    ("customers_100", "100 Customers", "A hundred buyers", lambda s: s["customers"] >= 100),
    ("revenue_10k", "First $10k", "10,000 in revenue", lambda s: s["revenue"] >= 10_000_00),
    ("mrr_10k", "$10k MRR", "The big one", lambda s: s["mrr"] >= 10_000_00),
]
ROAD = [0, 100_00, 500_00, 1_000_00, 2_500_00, 5_000_00, 10_000_00]  # MRR checkpoints (cents)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    product TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    refunded INTEGER NOT NULL DEFAULT 0,
    subscription TEXT,
    recurring INTEGER NOT NULL DEFAULT 0,
    test INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sales_created ON sales(created_at);
CREATE TABLE IF NOT EXISTS business_goals (
    id TEXT PRIMARY KEY,
    metric TEXT NOT NULL,
    period TEXT NOT NULL,
    target INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS business_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS milestones (
    key TEXT PRIMARY KEY,
    unlocked_at REAL NOT NULL
);
"""


class SalesError(GameError):
    pass


def _db():
    conn_cm = _connect()
    conn = conn_cm.__enter__()
    conn.executescript(_SCHEMA)
    return conn_cm, conn


class _Conn:
    def __enter__(self):
        self._cm, conn = _db()
        return conn

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)


def _meta(conn, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM business_meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def _set_meta(conn, key: str, value: Any) -> None:
    conn.execute("INSERT INTO business_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, json.dumps(value)))


# ── platform credentials ────────────────────────────────────────────────────

def _key(platform: str) -> str | None:
    from api.job_os.env import profile_env_value

    return profile_env_value(PLATFORMS[platform]["env"])[0] or None


def _write_key(platform: str, value: str | None) -> None:
    from api import profiles
    from api.shared_env import write_env_values

    write_env_values(profiles.get_active_hermes_home(), {PLATFORMS[platform]["env"]: value})


def _http(url: str, token: str, *, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(url, headers={
        # The key goes in a header, never the URL, so it cannot land in a log.
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.api+json, application/json",
        "User-Agent": "HermesDashboard/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed platform hosts
            raw = response.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise SalesError("The platform refused the key. Check it and try again.", 400) from error
        if error.code == 429:
            raise SalesError("The platform is rate limiting; try again in a minute.", 503) from error
        raise SalesError(f"The platform returned HTTP {error.code}", 502) from error
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise SalesError("The platform did not answer", 502) from error
    if len(raw) > _MAX_BODY:
        raise SalesError("The platform's answer was too large", 502)
    try:
        return json.loads(raw.decode("utf-8", "replace") or "null")
    except ValueError as error:
        raise SalesError("The platform returned something that is not JSON", 502) from error


Fetch = Callable[[str, str], Any]


def _account(platform: str, token: str, fetch: Fetch) -> dict[str, Any]:
    if platform == "lemonsqueezy":
        data = (fetch(PLATFORMS[platform]["api"] + "/users/me", token) or {}).get("data") or {}
        attrs = data.get("attributes") or {}
        return {"account": str(attrs.get("name") or attrs.get("email") or "")}
    data = fetch(PLATFORMS[platform]["api"] + "/user", token) or {}
    if data.get("success") is False:
        raise SalesError("Gumroad refused the token.", 400)
    user = data.get("user") or {}
    return {"account": str(user.get("name") or user.get("email") or "")}


def connect(platform: str, token: str, *, fetch: Fetch | None = None) -> dict[str, Any]:
    """Check the key with the platform, then save it and copy the sales in.
    Nothing is written when the platform refuses the key."""
    if platform not in PLATFORMS:
        raise SalesError("Choose Lemon Squeezy or Gumroad")
    token = str(token or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._\-]{16,2048}", token):
        raise SalesError("That doesn't look like an API key")
    fetch = fetch or _http
    account = _account(platform, token, fetch)
    _write_key(platform, token)
    with _LOCK, _Conn() as conn:
        _set_meta(conn, "platform", platform)
        _set_meta(conn, "account", account.get("account") or "")
        _set_meta(conn, "last_sync_at", 0)
        _set_meta(conn, "last_error", "")
    sync(force=True, fetch=fetch)
    return status()


def disconnect(*, forget_sales: bool = False) -> dict[str, Any]:
    with _LOCK, _Conn() as conn:
        platform = _meta(conn, "platform")
        _set_meta(conn, "platform", None)
        _set_meta(conn, "account", "")
        if forget_sales and platform:
            conn.execute("DELETE FROM sales WHERE platform = ?", (platform,))
    if platform in PLATFORMS:
        _write_key(platform, None)
    return status()


def status() -> dict[str, Any]:
    with _LOCK, _Conn() as conn:
        platform = _meta(conn, "platform")
        info = {
            "platform": platform,
            "label": PLATFORMS[platform]["label"] if platform in PLATFORMS else None,
            "account": _meta(conn, "account", ""),
            "last_sync_at": _meta(conn, "last_sync_at", 0),
            "last_error": _meta(conn, "last_error", ""),
            "test_mode": bool(conn.execute("SELECT 1 FROM sales WHERE test = 1 AND platform = ? LIMIT 1", (platform or "",)).fetchone()),
        }
    info["connected"] = bool(platform in PLATFORMS and _key(platform))
    info["platforms"] = [{"key": k, "label": v["label"]} for k, v in PLATFORMS.items()]
    return info


# ── fetching sales ──────────────────────────────────────────────────────────

def _iso(value: object) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time()


def _customer(value: object) -> str:
    # Only a stable fingerprint is kept, never the buyer's email or id.
    return hashlib.sha256(str(value or "").encode()).hexdigest()[:16] if value else ""


def _lemonsqueezy(token: str, fetch: Fetch) -> list[dict[str, Any]]:
    base = PLATFORMS["lemonsqueezy"]["api"]
    rows: list[dict[str, Any]] = []
    url: str | None = base + "/orders?page[size]=100"
    for _ in range(MAX_PAGES):
        if not url:
            break
        page = fetch(url, token) or {}
        for order in page.get("data") or []:
            a = order.get("attributes") or {}
            if a.get("status") not in ("paid", "refunded", "partial_refund"):
                continue
            item = a.get("first_order_item") or {}
            rows.append({"id": f"lemonsqueezy:order:{order.get('id')}", "platform": "lemonsqueezy",
                         "amount": int(a.get("total") or 0), "currency": str(a.get("currency") or "USD").upper(),
                         "product": str(item.get("product_name") or ""), "customer": _customer(a.get("customer_id") or a.get("user_email")),
                         "refunded": int(bool(a.get("refunded")) or a.get("status") == "refunded"),
                         "subscription": None, "recurring": 0, "test": int(bool(a.get("test_mode"))), "created_at": _iso(a.get("created_at"))})
        url = ((page.get("links") or {}).get("next")) or None
    # Renewals are subscription invoices, not orders: they are what MRR is made of.
    url = base + "/subscription-invoices?page[size]=100"
    for _ in range(MAX_PAGES):
        if not url:
            break
        page = fetch(url, token) or {}
        for invoice in page.get("data") or []:
            a = invoice.get("attributes") or {}
            if a.get("status") not in ("paid", "refunded", "partial_refund"):
                continue
            renewal = a.get("billing_reason") == "renewal"
            rows.append({"id": f"lemonsqueezy:invoice:{invoice.get('id')}", "platform": "lemonsqueezy",
                         "amount": int(a.get("total") or 0) if renewal else 0, "currency": str(a.get("currency") or "USD").upper(),
                         "product": "Subscription renewal" if renewal else "Subscription start",
                         "customer": _customer(a.get("customer_id") or a.get("user_email")),
                         "refunded": int(bool(a.get("refunded")) or a.get("status") == "refunded"),
                         "subscription": str(a.get("subscription_id") or ""), "recurring": 1, "test": int(bool(a.get("test_mode"))),
                         "created_at": _iso(a.get("created_at")), "_monthly": int(a.get("total") or 0)})
        url = ((page.get("links") or {}).get("next")) or None
    return rows


def _gumroad(token: str, fetch: Fetch) -> list[dict[str, Any]]:
    base = PLATFORMS["gumroad"]["api"] + "/sales"
    rows: list[dict[str, Any]] = []
    page_key = ""
    for _ in range(MAX_PAGES):
        url = base + (f"?page_key={urllib.parse.quote(page_key)}" if page_key else "")
        page = fetch(url, token) or {}
        if page.get("success") is False:
            raise SalesError("Gumroad refused the request", 502)
        for sale in page.get("sales") or []:
            recurring = bool(sale.get("subscription_id") or sale.get("recurrence"))
            rows.append({"id": f"gumroad:{sale.get('id')}", "platform": "gumroad",
                         "amount": int(sale.get("price") or 0), "currency": str(sale.get("currency") or "USD").upper(),
                         "product": str(sale.get("product_name") or ""), "customer": _customer(sale.get("purchaser_id") or sale.get("email")),
                         "refunded": int(bool(sale.get("refunded"))), "subscription": str(sale.get("subscription_id") or "") or None,
                         "recurring": int(recurring), "test": int(bool(sale.get("test"))), "created_at": _iso(sale.get("created_at")),
                         "_monthly": int(sale.get("price") or 0) if recurring else 0})
        page_key = str(page.get("next_page_key") or "")
        if not page_key:
            break
    return rows


def _store(conn, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            "INSERT INTO sales(id, platform, amount, currency, product, customer, refunded, subscription, recurring, test, created_at) "
            "VALUES(:id, :platform, :amount, :currency, :product, :customer, :refunded, :subscription, :recurring, :test, :created_at) "
            "ON CONFLICT(id) DO UPDATE SET refunded = excluded.refunded, amount = excluded.amount, product = excluded.product",
            {k: row[k] for k in ("id", "platform", "amount", "currency", "product", "customer", "refunded", "subscription", "recurring", "test", "created_at")})
        if row.get("subscription") and row.get("_monthly"):
            _set_meta(conn, f"sub:{row['subscription']}", {"monthly": row["_monthly"], "at": row["created_at"], "refunded": row["refunded"]})


def sync(*, force: bool = False, fetch: Fetch | None = None) -> None:
    """Copy new sales in from the connected platform (at most every SYNC_EVERY
    seconds unless forced). A failure is recorded and shown; the last copy stays."""
    with _LOCK, _Conn() as conn:
        platform = _meta(conn, "platform")
        last = _meta(conn, "last_sync_at", 0) or 0
    if platform not in PLATFORMS or (not force and time.time() - last < SYNC_EVERY):
        return
    token = _key(platform)
    if not token:
        return
    try:
        rows = (_lemonsqueezy if platform == "lemonsqueezy" else _gumroad)(token, fetch or _http)
    except SalesError as error:
        with _LOCK, _Conn() as conn:
            _set_meta(conn, "last_error", str(error))
            _set_meta(conn, "last_sync_at", time.time())
        return
    with _LOCK, _Conn() as conn:
        _store(conn, rows)
        _set_meta(conn, "last_sync_at", time.time())
        _set_meta(conn, "last_error", "")


_SYNCING = threading.Lock()


def sync_soon() -> None:
    """Refresh from the platform in the background when the copy is stale, so a
    slow or unreachable platform never holds up the page. One at a time."""
    with _LOCK, _Conn() as conn:
        platform = _meta(conn, "platform")
        last = _meta(conn, "last_sync_at", 0) or 0
    if platform not in PLATFORMS or time.time() - last < SYNC_EVERY or not _SYNCING.acquire(blocking=False):
        return

    def run():
        try:
            sync()
        except Exception:
            logger.info("background sales sync failed", exc_info=True)
        finally:
            _SYNCING.release()

    threading.Thread(target=run, name="dashboard-sales-sync", daemon=True).start()


# ── manual sales ────────────────────────────────────────────────────────────

def add_manual_sale(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    try:
        amount = round(float(payload.get("amount")) * 100)
    except (TypeError, ValueError):
        raise SalesError("Amount must be a number")
    if not 0 < amount <= 100_000_000:
        raise SalesError("Amount must be above 0")
    currency = str(payload.get("currency") or "USD").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise SalesError("Currency must be a 3-letter code such as USD")
    when = time.time()
    if payload.get("date"):
        try:
            when = datetime.fromisoformat(str(payload["date"])).replace(hour=12).timestamp()
        except ValueError:
            raise SalesError("Date must be YYYY-MM-DD")
    recurring = bool(payload.get("recurring"))
    row = {"id": f"manual:{uuid.uuid4().hex}", "platform": "manual", "amount": amount, "currency": currency,
           "product": str(payload.get("product") or "")[:120], "customer": _customer(payload.get("customer")),
           "refunded": 0, "subscription": (f"manual:{uuid.uuid4().hex}" if recurring else None), "recurring": int(recurring),
           "test": 0, "created_at": when, "_monthly": amount if recurring else 0}
    with _LOCK, _Conn() as conn:
        _store(conn, [row])
    return {"sale": {k: v for k, v in row.items() if not k.startswith("_")}}


def remove_manual_sale(sale_id: str) -> dict[str, Any]:
    sale_id = str(sale_id or "")
    if not sale_id.startswith("manual:"):
        raise SalesError("Only sales entered by hand can be removed")
    with _LOCK, _Conn() as conn:
        row = conn.execute("SELECT subscription FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if row is None:
            raise SalesError("Sale not found", 404)
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        if row["subscription"]:
            conn.execute("DELETE FROM business_meta WHERE key = ?", (f"sub:{row['subscription']}",))
        conn.execute("DELETE FROM xp_events WHERE key = ?", (f"sale:{sale_id}",))
    return {"removed": sale_id}


# ── goals ───────────────────────────────────────────────────────────────────

def add_goal(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    metric, period = str(payload.get("metric") or ""), str(payload.get("period") or "")
    if metric not in GOAL_METRICS or period not in GOAL_PERIODS:
        raise SalesError("A goal is a number of sales or an amount of revenue, per week or per month")
    try:
        target = float(payload.get("target"))
    except (TypeError, ValueError):
        raise SalesError("Target must be a number")
    target = round(target * 100) if metric == "revenue" else int(target)
    if target <= 0:
        raise SalesError("Target must be above 0")
    goal = {"id": uuid.uuid4().hex, "metric": metric, "period": period, "target": target, "created_at": time.time()}
    with _LOCK, _Conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM business_goals").fetchone()[0] >= 6:
            raise SalesError("You can have at most 6 goals")
        conn.execute("INSERT INTO business_goals(id, metric, period, target, created_at) VALUES(:id, :metric, :period, :target, :created_at)", goal)
    return {"goal": goal}


def remove_goal(goal_id: str) -> dict[str, Any]:
    with _LOCK, _Conn() as conn:
        if not conn.execute("DELETE FROM business_goals WHERE id = ?", (str(goal_id),)).rowcount:
            raise SalesError("Goal not found", 404)
    return {"removed": str(goal_id)}


def _period_start(period: str, day: date) -> date:
    return day - timedelta(days=day.weekday()) if period == "week" else day.replace(day=1)


def _previous_start(period: str, start: date) -> date:
    if period == "week":
        return start - timedelta(days=7)
    return (start - timedelta(days=1)).replace(day=1)


def _ts(day: date) -> float:
    return datetime(day.year, day.month, day.day).timestamp()


# ── the summary ─────────────────────────────────────────────────────────────

def _paid(rows) -> list:
    return [r for r in rows if not r["refunded"]]


def summary(now: float | None = None) -> dict[str, Any]:
    sync_soon()
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    with _LOCK, _Conn() as conn:
        platform = _meta(conn, "platform")
        rows = conn.execute("SELECT * FROM sales ORDER BY created_at DESC").fetchall()
        subs = {r["key"][4:]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM business_meta WHERE key LIKE 'sub:%'")}
        goals = [dict(g) for g in conn.execute("SELECT * FROM business_goals ORDER BY created_at")]
        unlocked = {r["key"]: r["unlocked_at"] for r in conn.execute("SELECT * FROM milestones")}
    # A connected platform shows its own sales (and manual ones); test-mode data only while it is all there is.
    rows = [r for r in rows if r["platform"] in (platform, "manual") or platform is None]
    live = [r for r in rows if not r["test"]]
    rows = live if live else rows
    paid = _paid(rows)
    currency = (paid[0]["currency"] if paid else "USD")
    month_start = _ts(today.replace(day=1))
    last_month_start = _ts((today.replace(day=1) - timedelta(days=1)).replace(day=1))
    week_start = _ts(today - timedelta(days=today.weekday()))
    sales_only = [r for r in paid if r["amount"] > 0]
    revenue = sum(r["amount"] for r in paid)
    month_rev = sum(r["amount"] for r in paid if r["created_at"] >= month_start)
    last_month_rev = sum(r["amount"] for r in paid if last_month_start <= r["created_at"] < month_start)
    cutoff = now - 35 * 86400  # a subscription counts while it renewed in the last ~month
    mrr = sum(v["monthly"] for v in subs.values() if not v.get("refunded") and v.get("at", 0) >= cutoff)
    stats = {
        "sales": len(sales_only), "revenue": revenue, "mrr": mrr,
        "customers": len({r["customer"] for r in sales_only if r["customer"]}) or len(sales_only),
        "subscribers": sum(1 for v in subs.values() if not v.get("refunded") and v.get("at", 0) >= cutoff),
    }
    # Milestones unlock once and stay unlocked; each earns XP. Test-mode sales
    # show on the page but never unlock anything.
    newly = []
    with _LOCK, _Conn() as conn:
        for key, title, _desc, test in MILESTONES:
            if live and key not in unlocked and test(stats):
                unlocked[key] = now
                newly.append(key)
                conn.execute("INSERT OR IGNORE INTO milestones(key, unlocked_at) VALUES(?, ?)", (key, now))
                _insert(conn, f"milestone:{key}", "business", f"Milestone: {title}", MILESTONE_XP, now, category="business",
                        detail={"kind": "milestone"})
    goal_rows = []
    for goal in goals:
        start = _period_start(goal["period"], today)

        def value(begin: date, end: date | None) -> int:
            inside = [r for r in sales_only if r["created_at"] >= _ts(begin) and (end is None or r["created_at"] < _ts(end))]
            return len(inside) if goal["metric"] == "sales" else sum(r["amount"] for r in inside)

        current = value(start, None)
        streak, begin = 0, start
        if current < goal["target"]:
            begin = _previous_start(goal["period"], start)
        while _ts(begin) >= goal["created_at"] - 40 * 86400 and value(begin, _next(goal["period"], begin)) >= goal["target"]:
            streak += 1
            begin = _previous_start(goal["period"], begin)
        goal_rows.append({**goal, "value": current, "progress": round(min(1.0, current / goal["target"]), 4), "met": current >= goal["target"], "streak": streak})
    months = []
    cursor = today.replace(day=1)
    for _ in range(6):
        nxt = (cursor + timedelta(days=32)).replace(day=1)
        months.append({"month": cursor.strftime("%Y-%m"), "label": cursor.strftime("%b"),
                       "revenue": sum(r["amount"] for r in paid if _ts(cursor) <= r["created_at"] < _ts(nxt))})
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    reached = max(i for i, mark in enumerate(ROAD) if mrr >= mark)
    return {
        "status": status(),
        "currency": currency,
        "totals": {**stats, "month_revenue": month_rev, "last_month_revenue": last_month_rev,
                   "week_sales": sum(1 for r in sales_only if r["created_at"] >= week_start),
                   "refunds": sum(1 for r in rows if r["refunded"])},
        "goals": goal_rows,
        "milestones": [{"key": k, "title": t, "description": d, "unlocked_at": unlocked.get(k), "new": k in newly or (unlocked.get(k, 0) >= now - 3 * 86400)}
                       for k, t, d, _ in MILESTONES],
        "road": {"checkpoints": ROAD, "reached": reached, "mrr": mrr,
                 "next": ROAD[reached + 1] if reached + 1 < len(ROAD) else None},
        "months": months,
        "recent": [{"id": r["id"], "platform": r["platform"], "amount": r["amount"], "currency": r["currency"], "product": r["product"],
                    "refunded": bool(r["refunded"]), "recurring": bool(r["recurring"]), "test": bool(r["test"]), "created_at": r["created_at"]}
                   for r in rows[:8] if r["amount"] > 0 or r["refunded"]],
    }


def _next(period: str, start: date) -> date:
    return start + timedelta(days=7) if period == "week" else (start + timedelta(days=32)).replace(day=1)


def sync_xp(conn) -> None:
    """Each paid sale earns business XP once (called from the XP ledger sync)."""
    conn.executescript(_SCHEMA)
    for row in conn.execute("SELECT * FROM sales WHERE refunded = 0 AND amount > 0 AND test = 0").fetchall():
        _insert(conn, f"sale:{row['id']}", "sales", f"Sale: {row['product'] or 'a purchase'}", SALE_XP, row["created_at"],
                category="business", detail={"kind": "sale"})
