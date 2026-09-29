"""Behavioural tests for the Business outlet's roster (phase 5).

Business and Projects are one engine. `static/office/roster.js` returns a desk
list in exactly the shape the adapter produces, so `computeLayout` and the
scene never learn which outlet is showing — the outlet is a desk-assignment
policy, not a second orchestrator.

The standing caveat is pinned here too: hermes-webui has no department-scoped
agent library yet, so departments are inferred from the persona's own words
and anything unrecognised lands on the visible overflow floor rather than
being forced into a department it does not belong to.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
ROSTER = REPO / "static" / "office" / "roster.js"
ROSTER_SRC = ROSTER.read_text(encoding="utf-8")
# Comment-free view, for assertions about what the code *does*: the prose here
# necessarily talks about delegation, which is exactly what it must not do.
ROSTER_CODE = re.sub(r"//[^\n]*|/\*.*?\*/", "", ROSTER_SRC, flags=re.S)
OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the office roster"
)

_DRIVER = r"""
const rosterApi = await import(process.argv[2]);
const { buildRoster, businessView, departmentFor, colorForDepartment } = rosterApi;
const input = JSON.parse(process.argv[3] || '{}');

const roster = buildRoster(input.personalities || []);
const view = businessView(input.state || { workers: [] }, roster);
const matched = (input.probe || []).map(text => {
  const dept = departmentFor(text);
  return [text, dept ? dept.key : null];
});
const routed = (input.routeProbe || []).map(text => [text,
  rosterApi.officeFor ? rosterApi.officeFor(text) : null]);
const businessIds = rosterApi.businessWorkerIds
  ? [...rosterApi.businessWorkerIds((input.state || {}).workers || [])].sort()
  : [];
const colorLookup = (input.colorProbe || []).map(key => [key, colorForDepartment(key)]);

process.stdout.write(JSON.stringify({ roster, view, matched, routed, businessIds, colorLookup }));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-roster") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, **payload):
    proc = subprocess.run(
        [NODE, str(driver), ROSTER.as_uri(), json.dumps(payload)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office roster driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def worker(wid, goal, status="running", spawned=1000):
    return {"id": wid, "goal": goal, "label": goal, "status": status,
            "spawnedAt": spawned, "pose": "work"}


def desks_by_cluster(view):
    out = {}
    for desk in view["desks"]:
        out.setdefault(desk["cluster"], []).append(desk)
    return out


# ── the standing floor ───────────────────────────────────────────────────────

def test_all_six_departments_stand_even_with_no_personas(driver):
    out = run(driver)
    keys = [d["key"] for d in out["roster"]["departments"]]
    assert keys[:6] == ["marketing", "emails", "sales", "operations", "finance", "delivery"]
    for dept in out["roster"]["departments"][:6]:
        assert dept["seats"], "an empty department still gets its desk"
        assert dept["seats"][0]["placeholder"] is True


def test_department_order_is_fixed(driver):
    # An office whose rooms move when someone is hired is not an office.
    empty = run(driver)
    staffed = run(driver, personalities=[{"name": "invoice_clerk", "description": ""}])
    assert ([d["key"] for d in empty["roster"]["departments"]]
            == [d["key"] for d in staffed["roster"]["departments"]])


def test_personas_are_filed_by_their_own_words(driver):
    out = run(driver, personalities=[
        {"name": "newsletter_writer", "description": "drafts the weekly send"},
        {"name": "invoice_clerk", "description": "raises invoices"},
        {"name": "qa_reviewer", "description": "checks the build"},
    ])
    by_key = {d["key"]: d for d in out["roster"]["departments"]}
    assert [s["persona"] for s in by_key["marketing"]["seats"]] == ["newsletter_writer"]
    assert [s["persona"] for s in by_key["finance"]["seats"]] == ["invoice_clerk"]
    assert [s["persona"] for s in by_key["delivery"]["seats"]] == ["qa_reviewer"]


def test_an_unrecognised_persona_lands_on_the_visible_floor(driver):
    # Forcing it into a department would make the floor plan lie.
    out = run(driver, personalities=[{"name": "zzz_widget", "description": "does a thing"}])
    floor = next(d for d in out["roster"]["departments"] if d["key"] == "floor")
    assert [s["persona"] for s in floor["seats"]] == ["zzz_widget"]


def test_seat_labels_are_readable_names(driver):
    out = run(driver, personalities=[{"name": "newsletter_writer", "description": ""}])
    marketing = next(d for d in out["roster"]["departments"] if d["key"] == "marketing")
    assert marketing["seats"][0]["label"] == "Newsletter Writer"


# ── matching ─────────────────────────────────────────────────────────────────

def test_the_best_matching_department_wins_not_the_first_declared(driver):
    out = run(driver, probe=[
        "reconcile the invoice ledger",
        "draft the launch campaign",
        "reply to the vendor email thread",
        "run the regression tests",
        "vacuum the carpet",
    ])
    assert dict(out["matched"]) == {
        "reconcile the invoice ledger": "finance",
        "draft the launch campaign": "marketing",
        "reply to the vendor email thread": "emails",
        "run the regression tests": "delivery",
        "vacuum the carpet": None,
    }


# ── seating live workers ─────────────────────────────────────────────────────

def test_workers_sit_in_the_department_their_goal_names(driver):
    out = run(driver,
              personalities=[{"name": "invoice_clerk", "description": ""}],
              state={"workers": [worker("w1", "raise the October invoices")]})
    seated = [d for d in out["view"]["desks"] if d["workerId"] == "w1"]
    assert len(seated) == 1 and seated[0]["cluster"] == "finance"


def test_an_unmatched_worker_goes_to_the_floor_not_a_wrong_department(driver):
    out = run(driver, state={"workers": [worker("w1", "plan the company offsite")]})
    seated = next(d for d in out["view"]["desks"] if d["workerId"] == "w1")
    assert seated["cluster"] == "floor"


def test_scheduled_agent_and_script_jobs_are_seated_on_the_business_floor(driver):
    """Runtime scheduled rows belong on THE FLOOR, never a guessed department."""
    out = run(driver, state={"workers": [
        {"id": "scheduled:business:agent-1", "label": "Scheduled Task",
         "goal": "Prepare the monthly invoice", "status": "running",
         "spawnedAt": 10, "scheduledTask": True, "scheduledMode": "agent"},
        {"id": "scheduled:business:script-1", "label": "Scheduled Task",
         "goal": "Database backup", "status": "running",
         "spawnedAt": 20, "scheduledTask": True, "scheduledMode": "script"},
    ]})
    floor = [desk for desk in out["view"]["desks"] if desk["cluster"] == "floor"]
    assert {desk["workerId"] for desk in floor} == {
        "scheduled:business:agent-1", "scheduled:business:script-1",
    }


def test_coding_and_personal_work_stay_out_of_the_business_office(driver):
    out = run(driver,
              routeProbe=["debug the React checkout API", "plan a personal reading list"],
              state={"workers": [
                  worker("code", "debug the React checkout API"),
                  worker("personal", "plan a personal reading list"),
                  worker("business", "reconcile the vendor invoices"),
              ]})
    assert dict(out["routed"]) == {
        "debug the React checkout API": "projects",
        "plan a personal reading list": "projects",
    }
    seated = {desk["workerId"] for desk in out["view"]["desks"] if desk["workerId"]}
    assert seated == {"business"}, "Business must not show coding or personal delegates"


def test_a_business_branch_stays_together_when_its_child_is_coding_work(driver):
    # The child is part of a business delegation even though its own work is
    # code. Keeping its lineage together prevents a split animation where the
    # parent is in Business and its live child is only on Projects.
    out = run(driver, state={"workers": [
        worker("campaign", "launch the customer acquisition campaign"),
        dict(worker("site", "implement the campaign landing page"), parentId="campaign"),
    ]})
    assert out["businessIds"] == ["campaign", "site"]
    seated = {desk["workerId"] for desk in out["view"]["desks"] if desk["workerId"]}
    assert seated == {"campaign", "site"}


def test_running_workers_are_seated_before_finished_ones(driver):
    # One Finance desk, two candidates: the live one should be the one on the
    # floor, not whichever spawned first.
    out = run(driver,
              state={"workers": [
                  worker("done", "invoice run", status="completed", spawned=1),
                  worker("live", "invoice run", status="running", spawned=9),
              ]})
    finance = desks_by_cluster(out["view"])["finance"]
    assert finance[0]["workerId"] == "live"


def test_a_full_office_grows_rather_than_dropping_a_worker(driver):
    # Every department seat and the floor taken: Hermes really is running
    # these, so the floor gains desks rather than losing workers.
    workers = [worker(f"w{i}", "plan the company offsite") for i in range(5)]
    out = run(driver, state={"workers": workers})
    seated = {d["workerId"] for d in out["view"]["desks"] if d["workerId"]}
    assert seated == {w["id"] for w in workers}


def test_the_business_view_keeps_the_rest_of_the_state_untouched(driver):
    out = run(driver, state={
        "workers": [worker("w1", "invoice run")],
        "conductor": {"id": "__conductor__", "status": "orchestrating"},
        "spawnPaused": True,
    })
    assert out["view"]["conductor"]["status"] == "orchestrating"
    assert out["view"]["spawnPaused"] is True


def test_desks_carry_a_seat_label_so_empty_departments_read_as_a_company(driver):
    out = run(driver)
    labels = {d["seatLabel"] for d in out["view"]["desks"]}
    assert "Marketing Lead" in labels and "Finance Lead" in labels
    assert "desk.seatLabel || 'Empty desk'" in SCENE_SRC, (
        "the scene must show a roster desk's name before anyone sits at it"
    )


def test_business_desks_carry_their_department_name_for_the_floor_sign(driver):
    out = run(driver, personalities=[{"name": "invoice_clerk", "description": ""}])
    labels = {d["cluster"]: d.get("clusterLabel") for d in out["view"]["desks"]}
    assert labels["finance"] == "Finance"
    assert labels["marketing"] == "Marketing"


def test_each_department_carries_its_own_floor_colour(driver):
    out = run(driver, personalities=[{"name": "invoice_clerk", "description": ""}])
    colors = {d["cluster"]: d.get("clusterColor") for d in out["view"]["desks"]}
    for key in ("marketing", "emails", "sales", "operations", "finance", "delivery"):
        assert colors[key], f"{key} must carry a floor colour"
    assert len({colors[k] for k in colors if k in (
        "marketing", "emails", "sales", "operations", "finance", "delivery")}) == 6, (
        "every department's floor colour must be distinct"
    )


def test_color_for_department_answers_a_hex_colour_or_null(driver):
    out = run(driver, colorProbe=["marketing", "floor", "__conductor__", "nonsense"])
    lookup = dict(out["colorLookup"])
    assert lookup["marketing"].startswith("#")
    assert lookup["floor"] is None
    assert lookup["__conductor__"] is None
    assert lookup["nonsense"] is None


def test_the_overflow_floor_carries_no_department_colour(driver):
    # "The Floor" is explicitly not a department (see roster.js's OVERFLOW
    # comment) -- tinting it would claim otherwise.
    out = run(driver, state={"workers": [worker("w1", "plan the company offsite")]})
    floor_desks = [d for d in out["view"]["desks"] if d["cluster"] == "floor"]
    assert floor_desks, "the probe goal must actually miss every department"
    assert all(not d.get("clusterColor") for d in floor_desks)


def test_business_desks_match_the_adapter_desk_shape(driver):
    # This is what lets one layout and one scene serve both outlets.
    out = run(driver, state={"workers": [worker("w1", "invoice run")]})
    for desk in out["view"]["desks"]:
        assert set(desk) >= {"id", "index", "workerId", "cluster"}


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_outlet_choice_is_remembered():
    assert "'hermes-webui-office-mode'" in OFFICE_INDEX_SRC
    # Blocked site data throws on access, not just on a missing key.
    read_at = OFFICE_INDEX_SRC.index("function readOutlet()")
    assert "catch" in OFFICE_INDEX_SRC[read_at:read_at + 400]


def test_business_is_a_desk_policy_not_a_second_engine():
    assert "businessView(scheduledState, _roster) : projectsFloorView(state)" in OFFICE_INDEX_SRC, (
        "the outlet must rewrite desks and hand the scene the same shape "
        "Projects does -- projectsFloorView() only filters that same state, "
        "it doesn't invent a second one"
    )
    for forbidden in ("delegate", "broadcast", "/api/agents/run"):
        assert forbidden not in ROSTER_CODE, (
            f"roster.js must not orchestrate — found {forbidden!r}"
        )


def test_the_roster_stays_pure():
    for forbidden in ("document.", "window.", "fetch(", "from 'three'"):
        assert forbidden not in ROSTER_CODE, (
            f"roster.js must stay pure — found {forbidden!r}"
        )
