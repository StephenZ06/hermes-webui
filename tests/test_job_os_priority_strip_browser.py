"""The top four on the Jobs Dashboard and Scout read as one summary strip:
one outlined panel, cells divided by hairlines, not four separate cards."""

import os

import pytest

from tests._pytest_port import BASE


def _open(page, hash_):
    page.goto(BASE + "/" + hash_, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); await switchPanel('jobs'); }")


@pytest.mark.parametrize("hash_,strip,cell", [("#jobs/dashboard", ".job-os-metrics", ".job-os-metric"),
                                              ("#jobs/scout", ".scout-overview", ".scout-tile")])
@pytest.mark.parametrize("width", [1440, 900, 390])
def test_the_top_four_are_one_strip(hash_, strip, cell, width):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            _open(page, hash_)
            page.wait_for_selector(f"{strip} {cell}", timeout=15000)
            page.wait_for_timeout(500)
            info = page.evaluate("""([strip, cell]) => { const s = document.querySelector(strip); const cs = getComputedStyle(s);
              const cells = [...s.querySelectorAll(':scope > ' + cell)].map(c => { const g = getComputedStyle(c); const r = c.getBoundingClientRect();
                return {border: g.borderTopWidth, radius: g.borderTopLeftRadius, w: r.width, l: r.left, r: r.right}; });
              const box = s.getBoundingClientRect();
              return {gap: cs.columnGap, border: cs.borderTopWidth, cells, left: box.left, right: box.right, page: document.documentElement.scrollWidth}; }""",
                                 [strip, cell])
            if os.environ.get("JOB_OS_SHOTS"):
                page.screenshot(path=os.path.join(os.environ["JOB_OS_SHOTS"], f"strip{hash_.split('/')[-1]}-{width}.png"))
        finally:
            browser.close()
    assert info["gap"] == "0px" and info["border"] == "1px"
    assert len(info["cells"]) == 4
    assert all(c["border"] == "0px" and c["radius"] == "0px" for c in info["cells"])
    assert info["page"] <= width  # no sideways scroll on a phone
