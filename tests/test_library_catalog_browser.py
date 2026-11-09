"""Skills page Libraries tab: catalog listing, tag editing, import review."""

import json
import shutil

import urllib.error
import urllib.request

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

LIBROOT = TEST_STATE_DIR / "libraries"


def _call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


@pytest.fixture
def catalog():
    shutil.rmtree(LIBROOT, ignore_errors=True)
    d = LIBROOT / "calm-ui"
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text("---\nname: Calm UI\nsource: https://github.com/x/calm\nlicense: MIT\nkind: npm\nframeworks: [react]\ntailwind: false\ninstall: npm i calm-ui\n---\n")
    (d / "components" / "fade.md").write_text("---\nname: Fade\nrole: text-effect\nstyle: [minimal]\nmotion: subtle\nplatform: [web]\n---\n")
    (d / "components" / "loose.md").write_text("---\nname: Loose\n---\n")
    yield LIBROOT
    shutil.rmtree(LIBROOT, ignore_errors=True)


def test_libraries_api_lists_vocab_and_edits_tags(catalog):
    _, data = _call("/api/libraries")
    assert data["vocab"]["styles"][0] == "minimal"
    [lib] = data["libraries"]
    assert [c["slug"] for c in lib["components"]] == ["fade", "loose"]
    code, out = _call("/api/libraries/component", {"library": "calm-ui", "component": "loose",
                      "fields": {"role": "cards", "style": ["bold"], "motion": "expressive", "platform": ["web"]}})
    assert code == 200 and out["component"]["needs_details"] is False
    code, _ = _call("/api/libraries/component", {"library": "../x", "component": "a", "fields": {}})
    assert code in (400, 404)


def test_save_refuses_an_existing_slug_without_replace(catalog):
    body = {"slug": "calm-ui", "library": {"name": "Calm UI", "kind": "npm", "frameworks": ["react"]}, "components": []}
    assert _call("/api/libraries/save", body)[0] == 409
    assert _call("/api/libraries/save", {**body, "replace": True})[0] == 200
