"""A repeat visit reuses the app files the browser already has.

The service worker used to fetch every shell script with ``cache: 'no-store'``,
which skips the HTTP cache, so each visit downloaded ~7.7 MB of JavaScript and
CSS again. It now revalidates (``no-cache``): unchanged files come back as 304.

Byte-range media (the dashboard's hero video) is only kept by the browser's
cache when its validator is strong; with a weak ETag it downloaded on every
visit.
"""

import json
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests._pytest_port import BASE

PORT = urlparse(BASE).port
LOG = Path(tempfile.gettempdir()) / f"hermes-webui-test-server-{PORT}.log"


def _rows_since(offset):
    with open(LOG, encoding="utf-8", errors="replace") as handle:
        handle.seek(offset)
        rows = []
        for line in handle:
            start = line.find("{")
            if start < 0 or '"path"' not in line:
                continue
            try:
                rows.append(json.loads(line[start:]))
            except ValueError:
                pass
        return rows


def test_a_second_visit_downloads_no_app_file_again():
    if not LOG.exists():
        pytest.skip("test server log not available")
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            first = context.new_page()
            first.goto(BASE + "/", wait_until="load")
            first.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            # The worker installs (and pre-caches) on the first visit; the
            # second visit is the one it serves.
            first.evaluate("async () => { await navigator.serviceWorker.ready; }")
            first.wait_for_timeout(1500)
            first.close()

            offset = LOG.stat().st_size
            second = context.new_page()
            second.goto(BASE + "/", wait_until="load")
            second.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            second.wait_for_timeout(1500)
            second.close()
        finally:
            browser.close()
    rows = _rows_since(offset)
    versioned = [r for r in rows if str(r.get("path", "")).startswith("/static/") and "?v=" in r["path"]]
    assert versioned, "the second visit made no request for app files at all"
    downloaded = sorted(r["path"].split("?")[0] for r in versioned if r.get("status") == 200)
    assert downloaded == [], f"downloaded again on a repeat visit: {downloaded}"


def test_range_served_media_has_a_strong_validator():
    request = urllib.request.Request(BASE + "/static/dashboard/characters/ascended.mp4", headers={"Range": "bytes=0-"})
    with urllib.request.urlopen(request, timeout=15) as response:
        assert response.status == 206
        etag = response.headers.get("ETag") or ""
    assert etag.startswith('"'), etag
