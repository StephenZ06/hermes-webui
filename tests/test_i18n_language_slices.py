"""The page loads i18n.js for its own language only (api/i18n_bundle.py).

static/i18n.js holds every language (about 2 MB, 540 KB gzipped); the page now
gets English, its own language and a one-line stub per other language, and
fetches a stubbed language when the user picks it.
"""

import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from api import i18n_bundle
from tests._pytest_port import BASE

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as response:
        return response.read().decode("utf-8")


def _locales_in_node(*sources):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to evaluate the bundles")
    script = (
        "const vm=require('vm');const ctx={localStorage:{getItem(){return null},setItem(){}},"
        "document:{documentElement:{},querySelectorAll(){return []}},window:{},console};vm.createContext(ctx);"
        "let src='';process.stdin.on('data',d=>src+=d).on('end',()=>{vm.runInContext(src+';this.__L=LOCALES;',ctx);"
        "process.stdout.write(JSON.stringify(ctx.__L));});"
    )
    out = subprocess.run(["node", "-e", script], input="\n".join(sources), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[:500]
    return json.loads(out.stdout)


def test_every_language_is_sliced_from_the_source():
    codes = i18n_bundle.known_codes(SOURCE)
    assert codes[0] == "en" and len(codes) == len(set(codes)) >= 15
    assert set(re.findall(r"^  '?([A-Za-z][\w-]*)'?: \{\s*$", SOURCE, re.M)) == set(codes)


def test_a_page_bundle_plus_a_patch_gives_the_same_strings_as_the_whole_file():
    full = _locales_in_node(SOURCE)
    page = i18n_bundle.page_bundle(SOURCE, "de")
    sliced = _locales_in_node(page, i18n_bundle.locale_patch(SOURCE, "zh-Hant"))
    assert list(sliced) == list(full)
    for code in ("en", "de", "zh-Hant"):
        assert sliced[code] == full[code], code
    assert sliced["ja"] == {"_label": full["ja"]["_label"], "_lazy": True}
    assert len(page.encode()) < len(SOURCE.encode()) / 4


def test_an_unexpected_layout_serves_the_whole_file():
    assert i18n_bundle.page_bundle("const LOCALES = {\n  en: {\n    a: 'b',\n  }\n};\n", "en") is None
    assert i18n_bundle.page_bundle(SOURCE.replace("const LOCALES = {", "var LOCALES = {"), "en") is None
    assert i18n_bundle.locale_patch(SOURCE, "xx") is None
    assert i18n_bundle.locale_patch(SOURCE, "de'); alert(1); ('") is None


def test_the_server_serves_each_slice_and_the_whole_file():
    whole = _get("/static/i18n.js")
    assert whole == SOURCE
    page = _get("/static/i18n.js?lang=ja")
    assert page == i18n_bundle.page_bundle(SOURCE, "ja")
    patch = _get("/static/i18n.js?locale=fr")
    assert patch.startswith("Object.assign(LOCALES, {\n  fr: {")
    with pytest.raises(urllib.error.HTTPError) as missing:
        _get("/static/i18n.js?locale=xx")
    assert missing.value.code == 404


def test_the_page_asks_for_its_own_language():
    html = _get("/")
    src = re.search(r'src="(static/i18n\.js\?[^"]+)"', html).group(1)
    assert "&amp;lang=" in src, src
