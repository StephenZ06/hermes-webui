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
    assert level_for(10_000)["tier_name"] in ("Sorcerer", "Archmage")
    assert level_for(0)["next_tier"] == {"level": 5, "name": "Adept"}


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
