"""Business dashboard: platform sales (Lemon Squeezy, Gumroad) and manual ones,
goals, milestones and the XP they earn. The platforms are faked here; the key
is checked before it is saved and never returned."""

import time

import pytest


@pytest.fixture()
def biz(monkeypatch, tmp_path):
    from api import dashboard_business, dashboard_game, work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr(dashboard_game, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda **_: [])
    monkeypatch.setattr(dashboard_game, "_sync_jobs", lambda conn: None)
    keys = {}
    monkeypatch.setattr(dashboard_business, "_key", lambda platform: keys.get(platform))
    monkeypatch.setattr(dashboard_business, "_write_key", lambda platform, value: keys.__setitem__(platform, value) if value else keys.pop(platform, None))
    return dashboard_business, dashboard_game, keys


def _iso(days_ago=0):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(time.time() - days_ago * 86400))


def lemon(orders, invoices=(), *, test=False, refuse=False):
    def fetch(url, token):
        if refuse:
            from api.dashboard_business import SalesError
            raise SalesError("The platform refused the key. Check it and try again.", 400)
        if url.endswith("/users/me"):
            return {"data": {"attributes": {"name": "Matt"}}}
        if "/orders" in url:
            return {"data": [{"id": str(i), "attributes": {"status": "paid" if not r else "refunded", "refunded": r, "total": t, "currency": "USD",
                                                           "first_order_item": {"product_name": "Pro"}, "customer_id": i, "test_mode": test,
                                                           "created_at": _iso(d)}} for i, (t, d, r) in enumerate(orders)], "links": {}}
        if "/subscription-invoices" in url:
            return {"data": [{"id": f"inv{i}", "attributes": {"status": "paid", "total": t, "currency": "USD", "billing_reason": "renewal",
                                                              "subscription_id": f"s{i}", "customer_id": 100 + i, "test_mode": test,
                                                              "created_at": _iso(d)}} for i, (t, d) in enumerate(invoices)], "links": {}}
        raise AssertionError(url)
    return fetch


def test_connect_checks_the_key_saves_it_and_never_returns_it(biz):
    dashboard_business, _, keys = biz
    status = dashboard_business.connect("lemonsqueezy", "ls_test_key_0123456789abcdef", fetch=lemon([(2900, 1, False)]))
    assert status["connected"] and status["account"] == "Matt" and status["label"] == "Lemon Squeezy"
    assert "ls_test_key_0123456789abcdef" not in str(status) and keys["lemonsqueezy"]

    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.connect("gumroad", "gr_wrong_key_0123456789", fetch=lemon([], refuse=True))
    assert "gumroad" not in keys  # nothing saved when refused
    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.connect("stripe", "x" * 20)


def test_sales_revenue_mrr_refunds_and_milestones(biz):
    dashboard_business, dashboard_game, _ = biz
    dashboard_business.connect("lemonsqueezy", "ls_live_key_0123456789abcdef",
                               fetch=lemon([(14900, 2, False), (2900, 1, False), (900, 0, True)], invoices=[(2900, 3), (2900, 50)]))
    data = dashboard_business.summary()
    totals = data["totals"]
    assert totals["sales"] == 4  # two orders and two renewals (the refund is not a sale)
    assert totals["revenue"] == 14900 + 2900 + 2900 + 2900
    assert totals["mrr"] == 2900  # the renewal 50 days ago has lapsed
    assert totals["refunds"] == 1
    unlocked = {m["key"] for m in data["milestones"] if m["unlocked_at"]}
    assert {"first_sale", "revenue_100", "first_subscriber"} <= unlocked and "mrr_1k" not in unlocked
    assert data["road"]["reached"] == 0 and data["road"]["next"] == 100_00

    profile = dashboard_game.character()
    business_xp = next(a["xp"] for a in profile["areas"] if a["key"] == "business")
    assert business_xp == 4 * dashboard_business.SALE_XP + 3 * dashboard_business.MILESTONE_XP
    assert dashboard_game.character()["total_xp"] == profile["total_xp"]  # awarded once


def test_test_mode_sales_show_but_never_reward(biz):
    dashboard_business, dashboard_game, _ = biz
    dashboard_business.connect("lemonsqueezy", "ls_test_key_0123456789abcdef", fetch=lemon([(2900, 0, False)], test=True))
    data = dashboard_business.summary()
    assert data["status"]["test_mode"] and data["totals"]["sales"] == 1
    assert not any(m["unlocked_at"] for m in data["milestones"])
    assert dashboard_game.character()["total_xp"] == 0


def test_manual_sales_goals_and_streaks(biz):
    dashboard_business, _, _ = biz
    goal = dashboard_business.add_goal({"metric": "sales", "period": "week", "target": 2})["goal"]
    dashboard_business.add_goal({"metric": "revenue", "period": "month", "target": 100})
    first = dashboard_business.add_manual_sale({"amount": "29", "product": "Pro"})["sale"]
    dashboard_business.add_manual_sale({"amount": 49.5, "product": "Pro yearly"})

    goals = {g["metric"]: g for g in dashboard_business.summary()["goals"]}
    assert goals["sales"]["value"] == 2 and goals["sales"]["met"] and goals["sales"]["streak"] >= 1
    assert goals["revenue"]["value"] == 7850 and goals["revenue"]["progress"] == pytest.approx(0.785)

    dashboard_business.remove_manual_sale(first["id"])
    assert dashboard_business.summary()["totals"]["sales"] == 1
    dashboard_business.remove_goal(goal["id"])
    assert len(dashboard_business.summary()["goals"]) == 1
    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.add_manual_sale({"amount": -5})
    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.add_goal({"metric": "vibes", "period": "week", "target": 1})
    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.remove_manual_sale("lemonsqueezy:order:1")


def test_a_failing_platform_keeps_the_last_copy_and_says_why(biz):
    dashboard_business, _, _ = biz
    dashboard_business.connect("lemonsqueezy", "ls_live_key_0123456789abcdef", fetch=lemon([(2900, 1, False)]))

    def down(url, token):
        from api.dashboard_business import SalesError
        raise SalesError("The platform did not answer", 502)

    dashboard_business.sync(force=True, fetch=down)
    data = dashboard_business.summary()
    assert data["totals"]["sales"] == 1 and "did not answer" in data["status"]["last_error"]


def test_gumroad_sales_are_read_page_by_page(biz):
    dashboard_business, _, _ = biz
    pages = {"": {"success": True, "sales": [{"id": "a", "price": 1500, "product_name": "Kit", "created_at": _iso(1), "purchaser_id": "p1"}], "next_page_key": "k2"},
             "k2": {"success": True, "sales": [{"id": "b", "price": 900, "product_name": "Kit", "created_at": _iso(0), "refunded": True}]}}

    def fetch(url, token):
        if url.endswith("/user"):
            return {"success": True, "user": {"name": "Matt"}}
        return pages["k2" if "page_key=k2" in url else ""]

    dashboard_business.connect("gumroad", "gumroad_token_0123456789", fetch=fetch)
    totals = dashboard_business.summary()["totals"]
    assert (totals["sales"], totals["revenue"], totals["refunds"]) == (1, 1500, 1)


def test_a_stale_copy_refreshes_in_the_background_without_holding_up_the_page(biz, monkeypatch):
    import threading

    dashboard_business, _, _ = biz
    dashboard_business.connect("lemonsqueezy", "ls_live_key_0123456789abcdef", fetch=lemon([(2900, 1, False)]))
    release = threading.Event()
    started = threading.Event()

    def slow_sync(**_):
        started.set()
        release.wait(5)

    monkeypatch.setattr(dashboard_business, "sync", slow_sync)
    with dashboard_business._LOCK, dashboard_business._Conn() as conn:
        dashboard_business._set_meta(conn, "last_sync_at", 0)

    t0 = time.time()
    data = dashboard_business.summary()
    assert time.time() - t0 < 2 and data["totals"]["sales"] == 1  # answered from the last copy
    assert started.wait(2)
    dashboard_business.sync_soon()  # a second refresh does not start while one runs
    release.set()


def test_goals_can_carry_a_live_work_hub_project_label(biz, monkeypatch):
    dashboard_business, _, _ = biz
    projects = [{"project_id": "saas", "name": "SaaS app"}]
    monkeypatch.setattr("api.models.load_projects", lambda **_: projects)
    dashboard_business.add_goal({"metric": "sales", "period": "week", "target": 3, "project_id": "saas"})
    with pytest.raises(dashboard_business.SalesError):
        dashboard_business.add_goal({"metric": "sales", "period": "week", "target": 3, "project_id": "gone"})
    data = dashboard_business.summary()
    assert data["projects"] == [{"id": "saas", "name": "SaaS app"}]
    assert data["goals"][0]["project"] == "SaaS app"

    projects.append({"project_id": "kit", "name": "Kit"})  # a folder added in the Work Hub shows at once
    assert [p["name"] for p in dashboard_business.summary()["projects"]] == ["Kit", "SaaS app"]
    projects.clear()  # deleted: the goal stays, without a label
    data = dashboard_business.summary()
    assert data["projects"] == [] and data["goals"][0]["project"] is None


def test_goals_stop_at_the_limit_with_a_clear_reason(biz):
    dashboard_business, _, _ = biz
    for n in range(dashboard_business.GOAL_LIMIT):
        dashboard_business.add_goal({"metric": "sales", "period": "week", "target": n + 1})
    with pytest.raises(dashboard_business.SalesError) as full:
        dashboard_business.add_goal({"metric": "sales", "period": "week", "target": 99})
    assert full.value.status == 409 and "at most" in str(full.value)
    assert dashboard_business.summary()["goal_limit"] == dashboard_business.GOAL_LIMIT


def test_the_sales_poller_starts_once(biz, monkeypatch):
    dashboard_business, _, _ = biz
    monkeypatch.setattr(dashboard_business, "_POLLER", None)
    started = []
    monkeypatch.setattr(dashboard_business.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: started.append(kw["name"]), "is_alive": lambda self: True})())
    assert dashboard_business.start_poller() is True
    assert dashboard_business.start_poller() is False
    assert started == ["dashboard-sales-poller"]


def test_revenue_series_by_hour_today_and_by_day_this_week_and_month(biz):
    """The Revenue card's filter: today by hour, this week (Monday first) and
    this month by day, each slot from the sale's local date, the current one
    marked. Sales before this month count in none of them."""
    from datetime import date, datetime, timedelta

    dashboard_business, _, _ = biz
    today = date.today()
    dashboard_business.add_manual_sale({"amount": "10", "product": "Now"})
    dashboard_business.add_manual_sale({"amount": "5", "product": "Old", "date": (today.replace(day=1) - timedelta(days=3)).isoformat()})
    if today.day > 1:
        dashboard_business.add_manual_sale({"amount": "7", "product": "Earlier", "date": today.replace(day=1).isoformat()})
    series = dashboard_business.summary()["series"]
    hour = datetime.now().hour
    assert len(series["today"]) == 24 and series["today"][hour]["revenue"] == 1000 and series["today"][hour]["now"]
    assert sum(p["revenue"] for p in series["today"]) == 1000
    assert [p["label"] for p in series["week"]] == ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"] and series["week"][today.weekday()]["now"]
    month = series["month"]
    assert len(month) == ((today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
    assert month[today.day - 1]["now"] and month[today.day - 1]["revenue"] >= 1000
    assert sum(p["revenue"] for p in month) == 1000 + (700 if today.day > 1 else 0)  # last month's sale is in none


def test_revenue_compares_with_the_previous_period_up_to_the_same_point(biz):
    """Yesterday counts only up to this time of day; a sale later yesterday
    is not part of the comparison."""
    from datetime import datetime, timedelta

    dashboard_business, _, _ = biz
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    with dashboard_business._LOCK, dashboard_business._Conn() as conn:
        for i, (when, cents) in enumerate([(yesterday - timedelta(minutes=30), 1200), (yesterday + timedelta(minutes=30), 9900)]):
            conn.execute("INSERT INTO sales(id, platform, amount, currency, product, customer, refunded, recurring, test, created_at) "
                         "VALUES(?, 'manual', ?, 'USD', 'x', ?, 0, 0, 0, ?)", (f"manual:t{i}", cents, f"c{i}", when.timestamp()))
    if yesterday.date() != (yesterday - timedelta(minutes=30)).date() or yesterday.date() != (yesterday + timedelta(minutes=30)).date():
        pytest.skip("too close to midnight for this fixture")
    previous = dashboard_business.summary()["series_previous"]
    assert previous["today"] == 1200  # the 9900 sale came later in the day than now
    assert set(previous) == {"today", "week", "month"}
