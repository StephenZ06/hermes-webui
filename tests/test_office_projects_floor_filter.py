"""Business-classified work is held back from the Projects floor.

Asked directly: a delegated task that would land in a Business department
should show live *only* on the Business floor, not on Projects too.
`projectsFloorView()` (static/office/index.js) filters `state.desks` before
handing them to the scene -- it and `descendantsOf()` are pure, so they are
lifted out and run on their own (the same approach
tests/test_office_sidebar_live.py and tests/test_office_task_status.py use),
against the real `departmentFor()` from roster.js rather than a stand-in, so
"would this land in a department" stays answered identically to what
businessView() itself would decide.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
OFFICE_INDEX = REPO / "static" / "office" / "index.js"
OFFICE_SRC = OFFICE_INDEX.read_text(encoding="utf-8")
ROSTER = REPO / "static" / "office" / "roster.js"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
import { readFileSync } from 'node:fs';
const { departmentFor, businessWorkerIds } = await import(process.argv[2]);
globalThis.departmentFor = departmentFor;
globalThis.businessWorkerIds = businessWorkerIds;

const src = readFileSync(process.argv[3], 'utf8');
function lift(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing function: ' + name);
  let i = src.indexOf('{', start), depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { i++; break; } }
  }
  return src.slice(start, i);
}

const body = lift('descendantsOf') + '\n' + lift('projectsFloorView');
const api = new Function(body + '\nreturn { projectsFloorView };')();
const input = JSON.parse(process.argv[4] || '{}');
process.stdout.write(JSON.stringify(api.projectsFloorView(input)));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-projects-floor") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, state):
    proc = subprocess.run(
        [NODE, str(driver), ROSTER.as_uri(), str(OFFICE_INDEX), json.dumps(state)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office projects-floor driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def worker(id_, goal, parent_id=None):
    w = {"id": id_, "goal": goal, "label": goal, "status": "running"}
    if parent_id is not None:
        w["parentId"] = parent_id
    return w


def desk(id_, worker_id, cluster="__conductor__"):
    return {"id": id_, "workerId": worker_id, "cluster": cluster}


def test_a_business_classified_worker_is_dropped_from_the_projects_floor(driver):
    state = {
        "workers": [worker("w1", "reconcile the monthly invoice")],
        "desks": [desk("d1", "w1")],
    }
    out = run(driver, state)
    assert out["desks"] == []


def test_a_personal_task_stays_on_the_projects_floor(driver):
    state = {
        "workers": [worker("w1", "write a short poem about the ocean")],
        "desks": [desk("d1", "w1")],
    }
    out = run(driver, state)
    assert len(out["desks"]) == 1
    assert out["desks"][0]["id"] == "d1"


def test_a_coding_task_stays_on_the_projects_floor(driver):
    state = {
        "workers": [worker("w1", "debug the React checkout API")],
        "desks": [desk("d1", "w1")],
    }
    out = run(driver, state)
    assert [desk_["id"] for desk_ in out["desks"]] == ["d1"]


def test_descendants_of_a_business_worker_are_hidden_too(driver):
    # A generic-sounding leaf ("read this file") delegated *by* business work
    # is still part of that business branch, not re-classified on its own.
    state = {
        "workers": [
            worker("parent", "update the budget and reconcile invoices"),
            worker("child", "read api/routes.py", parent_id="parent"),
        ],
        "desks": [desk("d-parent", "parent"), desk("d-child", "child", cluster="parent")],
    }
    out = run(driver, state)
    assert out["desks"] == []


def test_only_the_business_branch_is_hidden_not_unrelated_work(driver):
    state = {
        "workers": [
            worker("biz", "process the vendor payment"),
            worker("other", "write a short poem about the ocean"),
        ],
        "desks": [desk("d-biz", "biz"), desk("d-other", "other")],
    }
    out = run(driver, state)
    ids = {d["id"] for d in out["desks"]}
    assert ids == {"d-other"}


def test_a_desk_with_no_worker_yet_is_kept_rather_than_guessed_at(driver):
    state = {"workers": [], "desks": [desk("d1", None)]}
    out = run(driver, state)
    assert len(out["desks"]) == 1


def test_other_state_fields_pass_through_unchanged(driver):
    state = {"workers": [], "desks": [], "conductor": {"status": "orchestrating"}}
    out = run(driver, state)
    assert out["conductor"] == {"status": "orchestrating"}
