"""Quests and XP: quests are chosen Work Hub items shown with their live status;
finished work earns XP once (more for a quest), levels the character, and
counts towards the area its project belongs to."""

import pytest


@pytest.fixture()
def game(monkeypatch, tmp_path):
    from api import dashboard_game, work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr(dashboard_game, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda **_: [{"project_id": "saas", "name": "SaaS"}])
    monkeypatch.setattr(dashboard_game, "_sync_jobs", lambda conn: None)
    return dashboard_game, work_hub


def _item(work_hub, title, **fields):
    return work_hub.create_item({"title": title, **fields}, None)["item"]["id"]


def _finish(work_hub, item_id):
    work_hub.update_item(item_id, {"status": "done"}, work_hub.current_revision())


def test_a_quest_follows_its_work_hub_item_and_earns_bonus_xp(game):
    dashboard_game, work_hub = game
    phase10 = _item(work_hub, "Phase 10", priority="medium", project_id="saas")
    dashboard_game.add_quests([phase10])

    [quest] = dashboard_game.quests()
    assert (quest["title"], quest["status"], quest["done"], quest["xp"]) == ("Phase 10", "backlog", False, None)

    _finish(work_hub, phase10)  # in the Work Hub, or by a chat through the work_hub tool

    [quest] = dashboard_game.quests()
    assert quest["done"] and quest["xp"] == 45  # medium 30 x 1.5 for a quest
    assert dashboard_game.character()["quests_done"] == 1


def test_open_quests_come_first_and_clearing_hides_finished_ones(game):
    dashboard_game, work_hub = game
    a, b, c = (_item(work_hub, t) for t in ("A", "B", "C"))
    work_hub.update_item(c, {"status": "in_progress"}, work_hub.current_revision())
    dashboard_game.add_quests([a, b, c])
    _finish(work_hub, a)

    assert [q["title"] for q in dashboard_game.quests()] == ["C", "B", "A"]
    assert dashboard_game.clear_completed()["cleared"] == [a]
    assert [q["title"] for q in dashboard_game.quests()] == ["C", "B"]


def test_a_deleted_item_drops_out_of_quests(game):
    dashboard_game, work_hub = game
    gone = _item(work_hub, "Gone")
    dashboard_game.add_quests([gone])
    work_hub.delete_item(gone, work_hub.current_revision())

    assert dashboard_game.quests() == []
    assert dashboard_game.quest_ids() == []


def test_xp_is_awarded_once_and_survives_reopening(game):
    dashboard_game, work_hub = game
    item = _item(work_hub, "Ship it", priority="high")
    _finish(work_hub, item)
    assert dashboard_game.character()["total_xp"] == 50
    work_hub.update_item(item, {"status": "todo"}, work_hub.current_revision())
    _finish(work_hub, item)

    profile = dashboard_game.character()
    assert profile["total_xp"] == 50 and profile["tasks_done"] == 1


def test_project_category_decides_which_area_gets_the_xp(game):
    dashboard_game, work_hub = game
    _finish(work_hub, _item(work_hub, "Landing page", project_id="saas"))
    assert [a["xp"] for a in dashboard_game.character()["areas"]] == [20, 0, 0]

    dashboard_game.set_category("saas", "business")

    profile = dashboard_game.character()
    assert [a["xp"] for a in profile["areas"]] == [0, 0, 20]
    assert profile["stats"]["CHA"]["value"] > profile["stats"]["INT"]["value"]
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.set_category("saas", "hobby")


def test_levels_and_tiers():
    from api.dashboard_game import level_for

    assert level_for(0)["level"] == 1 and level_for(99)["level"] == 1
    assert level_for(100)["level"] == 2 and level_for(100)["into_level"] == 0
    assert level_for(225)["level"] == 3  # 100 + 125
    assert level_for(10_000)["tier_name"] in ("Astral", "Paragon")
    assert level_for(0)["next_tier"] == {"level": 5, "name": "Disciple"}


def test_streak_counts_consecutive_days_and_survives_until_today_ends():
    from api.dashboard_game import _streak

    assert _streak({"2026-10-14", "2026-10-15", "2026-10-16"}, "2026-10-16") == 3
    assert _streak({"2026-10-14", "2026-10-15"}, "2026-10-16") == 2
    assert _streak({"2026-10-13"}, "2026-10-16") == 0


def test_quest_input_is_validated(game):
    dashboard_game, _ = game
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.add_quests([])
    with pytest.raises(dashboard_game.GameError) as error:
        dashboard_game.add_quests(["nope"])
    assert error.value.status == 404


def test_a_habit_ticked_earns_vitality_once_a_day_and_unticking_takes_it_back(game):
    dashboard_game, _ = game
    habit = dashboard_game.create_habit({"name": "Gym", "cadence": "daily"})["habit"]

    dashboard_game.check_habit(habit["id"], "2026-10-15")
    dashboard_game.check_habit(habit["id"], "2026-10-15")  # twice the same day: once
    dashboard_game.check_habit(habit["id"], "2026-10-16")
    profile = dashboard_game.character()
    assert profile["total_xp"] == 20 and profile["stats"]["VIT"]["value"] > 1
    assert profile["stats"]["STR"]["value"] == 1  # habits count as vitality, not strength

    dashboard_game.check_habit(habit["id"], "2026-10-16", done=False)
    assert dashboard_game.character()["total_xp"] == 10


def test_daily_and_weekly_habit_streaks(game, monkeypatch):
    dashboard_game, _ = game
    import time as _time
    now = _time.mktime((2026, 10, 16, 12, 0, 0, 0, 0, -1))  # a Friday
    daily = dashboard_game.create_habit({"name": "Read", "cadence": "daily"})["habit"]
    weekly = dashboard_game.create_habit({"name": "Run", "cadence": "weekly", "target": 2})["habit"]
    for day in ("2026-10-14", "2026-10-15", "2026-10-16"):
        dashboard_game.check_habit(daily["id"], day)
    for day in ("2026-10-06", "2026-10-08", "2026-10-13"):  # last week twice, this week once
        dashboard_game.check_habit(weekly["id"], day)

    rows = {h["name"]: h for h in dashboard_game.habits(now)}
    assert (rows["Read"]["streak"], rows["Read"]["done"]) == (3, True)
    assert (rows["Run"]["week_count"], rows["Run"]["done"], rows["Run"]["streak"]) == (1, False, 1)
    assert len(rows["Read"]["recent"]) == 21 and rows["Read"]["recent"][-1] is True


def test_habit_validation_and_archive(game):
    dashboard_game, _ = game
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.create_habit({"name": "  "})
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.create_habit({"name": "Gym", "cadence": "daily", "target": 3})
    habit = dashboard_game.create_habit({"name": "Gym"})["habit"]
    dashboard_game.archive_habit(habit["id"])
    assert dashboard_game.habits() == []
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.check_habit(habit["id"])


def test_learning_counts_towards_its_area_and_can_be_removed(game):
    dashboard_game, _ = game
    entry = dashboard_game.add_learning({"title": "AZ-900", "kind": "certification", "area": "career"})["entry"]
    assert entry["xp"] == 100
    profile = dashboard_game.character()
    assert [a["xp"] for a in profile["areas"]] == [0, 100, 0]
    assert "AZ-900" in profile["log"][0]["title"]
    dashboard_game.remove_learning(entry["id"])
    assert dashboard_game.character()["total_xp"] == 0
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.add_learning({"title": "X", "kind": "vibes"})


def test_quests_carry_their_area(game):
    dashboard_game, work_hub = game
    item = _item(work_hub, "Pricing page", project_id="saas")
    dashboard_game.set_category("saas", "business")
    dashboard_game.add_quests([item])
    assert dashboard_game.quests()[0]["area"] == "business"


def test_achievements_unlock_once_and_pay_gold(game):
    dashboard_game, work_hub = game
    assert not any(a["unlocked_at"] for a in dashboard_game.character()["achievements"])
    item = _item(work_hub, "First thing")
    dashboard_game.add_quests([item])
    _finish(work_hub, item)

    profile = dashboard_game.character()
    unlocked = {a["key"]: a for a in profile["achievements"] if a["unlocked_at"]}
    assert {"first_task", "first_quest"} <= set(unlocked) and unlocked["first_quest"]["new"]
    # 30 XP (20 x 1.5 for a quest) -> 15 gold, plus 50 per achievement
    assert profile["shop"]["gold"]["balance"] == 15 + 50 * len(unlocked)
    again = dashboard_game.character()
    assert again["shop"]["gold"]["balance"] == profile["shop"]["gold"]["balance"]


def test_rewards_are_bought_with_gold_and_refused_when_short(game):
    dashboard_game, work_hub = game
    _finish(work_hub, _item(work_hub, "Thing", priority="high"))
    balance = dashboard_game.character()["shop"]["gold"]["balance"]  # 25 + 50
    cheap = dashboard_game.add_reward({"name": "Coffee", "cost": 20})["reward"]
    dear = dashboard_game.add_reward({"name": "New gear", "cost": 5000})["reward"]

    assert dashboard_game.redeem(cheap["id"])["gold"]["balance"] == balance - 20
    with pytest.raises(dashboard_game.GameError) as error:
        dashboard_game.redeem(dear["id"])
    assert error.value.status == 409 and "more gold" in str(error.value)
    assert dashboard_game.shop()["history"][0]["name"] == "Coffee"
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.add_reward({"name": "Free", "cost": 0})


def test_best_streak():
    from api.dashboard_game import _best_streak

    assert _best_streak({"2026-10-01", "2026-10-02", "2026-10-03", "2026-10-07", "2026-10-08"}) == 3
    assert _best_streak(set()) == 0


def test_skills_gained_earn_xp_once_unlock_badges_and_can_be_removed(game):
    dashboard_game, _ = game
    docker = dashboard_game.add_skill({"name": "Docker", "kind": "course"})["skill"]
    assert docker["xp"] == dashboard_game.SKILL_XP["course"]
    with pytest.raises(dashboard_game.GameError) as dup:
        dashboard_game.add_skill({"name": "  docker ", "kind": "self"})  # same skill, any case
    assert dup.value.status == 409
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.add_skill({"name": "Kubernetes", "kind": "wizardry"})
    dashboard_game.add_skill({"name": "AWS Cloud Practitioner", "kind": "certification"})

    data = dashboard_game.skills()
    assert data["total"] == 2 and [e["name"] for e in data["entries"]] == ["AWS Cloud Practitioner", "Docker"]
    assert sorted(dashboard_game.skill_names()) == ["AWS Cloud Practitioner", "Docker"]
    profile = dashboard_game.character()
    career = next(a["xp"] for a in profile["areas"] if a["key"] == "career")
    assert career == dashboard_game.SKILL_XP["course"] + dashboard_game.SKILL_XP["certification"]
    unlocked = {a["key"] for a in profile["achievements"] if a["unlocked_at"]}
    assert {"first_skill", "certified"} <= unlocked and "polymath" not in unlocked

    dashboard_game.remove_skill(docker["id"])
    assert dashboard_game.skill_names() == ["AWS Cloud Practitioner"]
    assert dashboard_game.character()["total_xp"] == profile["total_xp"] - dashboard_game.SKILL_XP["course"]


def test_a_quest_chosen_on_a_tab_shows_and_earns_there_whatever_its_project(game):
    dashboard_game, work_hub = game
    item = _item(work_hub, "Polish CV", priority="high")  # General: Personal by default
    with pytest.raises(dashboard_game.GameError):
        dashboard_game.add_quests([item], area="wizardry")
    dashboard_game.add_quests([item], area="career")

    [quest] = dashboard_game.quests()
    assert quest["area"] == "career"
    _finish(work_hub, item)
    areas = {a["key"]: a["xp"] for a in dashboard_game.character()["areas"]}
    assert areas["career"] == 75 and areas["personal"] == 0  # high 50 x 1.5, counted for Career

    other = _item(work_hub, "Plan trip")
    dashboard_game.add_quests([other])  # chosen from the Character page: follows its project
    assert {q["title"]: q["area"] for q in dashboard_game.quests()}["Plan trip"] == "personal"


def test_achievements_fill_whole_rows_and_each_one_is_unique():
    from api import dashboard_game

    keys = [a[0] for a in dashboard_game.ACHIEVEMENTS]
    assert len(keys) == len(set(keys)) == 24  # 24 tiles: whole rows of 2, 3, 4, 6 or 8


def test_the_treasury_tracks_gold_in_and_out(game):
    dashboard_game, work_hub = game
    item = _item(work_hub, "Ship it", priority="high")
    _finish(work_hub, item)  # 50 XP -> 25 gold, plus the First Steps achievement (50)
    dashboard_game.character()
    reward = dashboard_game.add_reward({"name": "Coffee", "cost": 30, "icon": "☕"})["reward"]
    dashboard_game.add_reward({"name": "Keyboard", "cost": 5000})
    dashboard_game.redeem(reward["id"])
    t = dashboard_game.treasury()
    assert t["gold"]["spent"] == 30 and t["gold"]["balance"] == t["gold"]["earned"] - 30
    assert t["stats"]["earned_today"] == t["gold"]["earned"] and t["stats"]["redeemed"] == 1
    assert t["saving_for"]["name"] == "Keyboard" and t["saving_for"]["short"] == 5000 - t["gold"]["balance"]
    kinds = [f["kind"] for f in t["ledger"]]
    assert "spend" in kinds and "achievement" in kinds and "earn" in kinds
    assert len(t["days"]) == 14 and t["days"][-1]["spent"] == 30


def test_achievements_say_which_ones_have_badge_art():
    from api import dashboard_game

    art = dashboard_game._achievement_art()
    assert {"first_task", "habit_month", "tasks_200"} <= art
    assert art <= {a[0] for a in dashboard_game.ACHIEVEMENTS}  # every art file belongs to an achievement
