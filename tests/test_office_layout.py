"""Behavioural tests for the office floor plan (phase 3).

`static/office/layout.js` is pure geometry — no three.js, no DOM — so node
runs the real thing, the same way tests/test_office_adapter.py runs the real
adapter.

The Projects outlet has no fixed departments: the floor plan is a function of
the live delegation tree. Two properties matter and neither is obvious from
reading the code, so they are pinned here — pods must not overlap, and the
office must not rearrange itself every time a subagent spawns.
"""
import json
import math
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
LAYOUT = REPO / "static" / "office" / "layout.js"
LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the office layout"
)

_DRIVER = r"""
const { computeLayout } = await import(process.argv[2]);
const desks = JSON.parse(process.argv[3] || '[]');
process.stdout.write(JSON.stringify(computeLayout(desks)));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-layout") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def layout(driver, desks):
    proc = subprocess.run(
        [NODE, str(driver), LAYOUT.as_uri(), json.dumps(desks)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office layout driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def desks(*specs):
    """`desks(("a", 0), ("b", 0))` -> desk records with cluster and index."""
    out = []
    for i, (cluster, _n) in enumerate(specs):
        out.append({
            "id": f"desk-{i}", "index": i,
            "workerId": f"w{i}", "cluster": cluster,
        })
    return out


def n_desks(count, cluster="__conductor__"):
    return [
        {"id": f"desk-{i}", "index": i, "workerId": f"w{i}", "cluster": cluster}
        for i in range(count)
    ]


# ── basics ───────────────────────────────────────────────────────────────────

def test_an_empty_office_has_no_pods(driver):
    out = layout(driver, [])
    assert out["pods"] == [] and out["seats"] == {}
    assert out["radius"] > 0, "the conductor still needs room at the centre"


def test_every_desk_gets_a_seat(driver):
    out = layout(driver, n_desks(7))
    assert len(out["seats"]) == 7
    assert {s["deskId"] for s in out["pods"][0]["seats"]} == set(out["seats"])


def test_desks_of_one_cluster_share_a_pod(driver):
    out = layout(driver, desks(("p1", 0), ("p1", 1), ("p2", 0)))
    clusters = [pod["cluster"] for pod in out["pods"]]
    assert clusters == ["p1", "p2"], "pods keep first-seen cluster order"
    assert len(out["pods"][0]["seats"]) == 2
    assert len(out["pods"][1]["seats"]) == 1


def test_seats_sit_inside_their_pod(driver):
    out = layout(driver, n_desks(5, cluster="p1"))
    pod = out["pods"][0]
    for seat in pod["seats"]:
        assert abs(seat["x"] - pod["x"]) <= pod["width"] / 2 + 0.001
        assert abs(seat["z"] - pod["z"]) <= pod["depth"] / 2 + 0.001


def test_workers_face_the_middle_of_the_office(driver):
    # A worker seen from the fixed isometric camera should be working into
    # the office, not off the edge of the floor.
    out = layout(driver, n_desks(1, cluster="p1"))
    seat = out["pods"][0]["seats"][0]
    facing = (math.sin(seat["rotationY"]), math.cos(seat["rotationY"]))
    # The seat's forward vector should point back toward the origin.
    to_origin = (-seat["x"], -seat["z"])
    length = math.hypot(*to_origin) or 1
    dot = facing[0] * to_origin[0] / length + facing[1] * to_origin[1] / length
    assert dot > 0.9, "desks face the conductor at the centre"


# ── packing ──────────────────────────────────────────────────────────────────

def _pod_clearance(a, b):
    """Centre distance minus the two half-extents — negative means overlap."""
    gap = math.hypot(a["x"] - b["x"], a["z"] - b["z"])
    reach_a = max(a["width"], a["depth"]) / 2
    reach_b = max(b["width"], b["depth"]) / 2
    return gap - reach_a - reach_b


@pytest.mark.parametrize("pod_count", [2, 6, 7, 13, 20])
def test_pods_never_overlap(driver, pod_count):
    records = []
    for c in range(pod_count):
        records.extend([
            {"id": f"desk-{c}-{i}", "index": i, "workerId": f"w{c}{i}",
             "cluster": f"p{c}"}
            for i in range(3)
        ])
    out = layout(driver, records)
    assert len(out["pods"]) == pod_count
    for i, a in enumerate(out["pods"]):
        for b in out["pods"][i + 1:]:
            assert _pod_clearance(a, b) > 0, (
                f"pods {a['cluster']} and {b['cluster']} overlap"
            )


def test_rings_fill_before_they_grow(driver):
    # Ring 1 takes 6 pods; the 7th starts ring 2, further out.
    records = []
    for c in range(7):
        records.append({"id": f"d{c}", "index": c, "workerId": f"w{c}", "cluster": f"p{c}"})
    out = layout(driver, records)
    rings = [pod["ring"] for pod in out["pods"]]
    assert rings == [1, 1, 1, 1, 1, 1, 2]
    ring1 = [p for p in out["pods"] if p["ring"] == 1]
    ring2 = [p for p in out["pods"] if p["ring"] == 2]
    r1 = math.hypot(ring1[0]["x"], ring1[0]["z"])
    r2 = math.hypot(ring2[0]["x"], ring2[0]["z"])
    assert r2 > r1


def test_radius_covers_the_outermost_pod(driver):
    out = layout(driver, [
        {"id": f"d{c}", "index": c, "workerId": f"w{c}", "cluster": f"p{c}"}
        for c in range(9)
    ])
    cx, cz = out["center"]["x"], out["center"]["z"]
    for pod in out["pods"]:
        reach = math.hypot(pod["x"] - cx, pod["z"] - cz) + max(pod["width"], pod["depth"]) / 2
        assert reach <= out["radius"] + 0.001, (
            "radius is what the camera frames with; a pod outside it is off screen"
        )


def test_the_camera_centre_follows_the_occupied_floor(driver):
    # A part-filled ring is lopsided — two pods out of six sit on one side of
    # the conductor. Framing on the origin would leave the office in a corner
    # with dead floor opposite it.
    empty = layout(driver, [])
    assert empty["center"] == {"x": 0, "z": 0}

    lopsided = layout(driver, [
        {"id": "d0", "index": 0, "workerId": "w0", "cluster": "p0"},
        {"id": "d1", "index": 1, "workerId": "w1", "cluster": "p1"},
    ])
    assert math.hypot(lopsided["center"]["x"], lopsided["center"]["z"]) > 1, (
        "the centre should move toward the pods that exist"
    )
    for pod in lopsided["pods"]:
        reach = (math.hypot(pod["x"] - lopsided["center"]["x"],
                            pod["z"] - lopsided["center"]["z"])
                 + max(pod["width"], pod["depth"]) / 2)
        assert reach <= lopsided["radius"] + 0.001


# ── stability ────────────────────────────────────────────────────────────────

def test_adding_a_subagent_does_not_move_the_existing_office(driver):
    # The office rearranging itself on every spawn is unreadable. A pod keeps
    # its ring slot as long as its cluster keeps existing.
    before = layout(driver, desks(("p1", 0), ("p2", 0)))
    after = layout(driver, desks(("p1", 0), ("p2", 0)) + [
        {"id": "desk-2", "index": 2, "workerId": "w2", "cluster": "p3"},
    ])
    for i in range(2):
        assert before["pods"][i]["x"] == after["pods"][i]["x"]
        assert before["pods"][i]["z"] == after["pods"][i]["z"]


def test_the_layout_is_deterministic(driver):
    records = n_desks(9, cluster="p1")
    assert layout(driver, records) == layout(driver, records)


def test_a_pod_grows_rows_rather_than_an_endless_line(driver):
    out = layout(driver, n_desks(9, cluster="p1"))
    pod = out["pods"][0]
    xs = {round(seat["x"], 4) for seat in pod["seats"]}
    zs = {round(seat["z"], 4) for seat in pod["seats"]}
    assert len(xs) == 3 and len(zs) == 3, "9 desks pack 3x3, not 9x1"


# ── purity ───────────────────────────────────────────────────────────────────

def test_the_layout_touches_no_browser_or_renderer_api():
    for forbidden in ("document.", "window.", "fetch(", "from 'three'"):
        assert forbidden not in LAYOUT_SRC, (
            f"layout.js must stay pure — found {forbidden!r}"
        )
