"""Dashboard: opened, its cards rise in as one movement, with their pictures.

Cards used to paint at once, then their pictures, the hero video and the party
bots each popped in on their own; a fresh reading landing right after a cached
paint swapped half-risen cards for still ones. Its data is now fetched in the
browser's quiet time before the page is first opened.
"""
from tests.test_dashboard_browser import _open, browser  # noqa: F401


def _cards(page):
    return page.evaluate("""() => [...document.querySelectorAll('.dash-body [data-enter]')].map(card => ({
      i: Number(card.style.getPropertyValue('--enter-i')), name: getComputedStyle(card).animationName,
      top: Math.round(card.getBoundingClientRect().top), left: Math.round(card.getBoundingClientRect().left)}))""")


def test_the_cards_rise_in_reading_order(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'character'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector(".dash-body.is-entering [data-enter]", state="attached", timeout=15000)
    cards = _cards(page)
    assert len(cards) >= 4, cards
    assert all(c["name"] == "dash-card-in" for c in cards), cards
    order = sorted(cards, key=lambda c: c["i"])
    # Reading order: down the page, left to right along a row.
    assert all((b["top"] - a["top"] > 24) or (abs(b["top"] - a["top"]) <= 24 and b["left"] >= a["left"]) for a, b in zip(order, order[1:])), order
    # No container rises as well (that doubled the movement).
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash-body')).animationName") == "none"


def test_a_fresh_reading_mid_entrance_carries_the_entrance_on(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'character'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector(".dash-body.is-entering [data-enter]", state="attached", timeout=15000)
    page.wait_for_timeout(150)
    # A repaint with new data while the cards are still rising.
    page.evaluate("() => { const st = HermesDashboard._state; st.data.character = {...st.data.character, total_xp: (st.data.character.total_xp || 0) + 1}; }")
    page.evaluate("() => { const st = HermesDashboard._state; st.painted.signature = 'changed'; }")
    page.evaluate("() => HermesDashboard.select('character')")
    out = page.evaluate("""() => { const body = document.querySelector('.dash-body');
      return {entering: body.classList.contains('is-entering'), shift: parseFloat(body.style.getPropertyValue('--enter-shift')) || 0,
        cards: body.querySelectorAll('[data-enter]').length}; }""")
    assert out["entering"] and out["shift"] < -100 and out["cards"] >= 4, out


def test_the_page_data_is_fetched_before_it_is_first_opened(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'character'); } catch (_) {} }")
    page.wait_for_function("() => window.HermesDashboard && HermesDashboard._state.data.character", polling=200, timeout=20000)
    asked = []
    page.on("request", lambda r: asked.append(r.url) if "/api/dashboard/" in r.url else None)
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    # It paints from what is already here, in the same moment: no page loader.
    assert page.evaluate("() => !!document.querySelector('#dashboardRoot .dash-body') && !document.querySelector('#dashboardRoot > .dash-loader.is-page:not(.is-leaving)')")


def test_a_prefetched_page_opens_without_a_loader(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'character'); } catch (_) {} }")
    page.wait_for_function("() => window.HermesDashboard && HermesDashboard._state.data.character", polling=200, timeout=20000)
    # Watch every frame from the click until the cards are in: the page's
    # "Loading..." never shows, since there is nothing left to wait for.
    seen = page.evaluate("""() => new Promise(resolve => {
      const host = document.getElementById('dashboardRoot'); const seen = []; const t0 = performance.now();
      const tick = () => {
        const loader = host.querySelector('.dash-loader.is-page');
        if (loader && loader.getBoundingClientRect().width) seen.push(Math.round(performance.now() - t0));
        if (performance.now() - t0 < 900) requestAnimationFrame(tick); else resolve(seen);
      };
      requestAnimationFrame(tick);
      switchPanel('dashboard');
    })""")
    assert seen == [], seen
    assert page.evaluate("() => document.querySelectorAll('#dashboardRoot .dash-body [data-enter]').length") >= 4


def test_leaving_the_page_stops_its_refreshes_and_effects(browser):
    page = _open(browser, viewport={"width": 1470, "height": 956})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'character'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .dash-body [data-enter]", state="attached", timeout=15000)
    page.wait_for_timeout(1500)
    page.evaluate("async () => { await switchPanel('chat'); }")
    asked = []
    # /api/dashboard/status is the agent dashboard link's own probe, not this page.
    page.on("request", lambda r: asked.append(r.url) if "/api/dashboard/" in r.url and "/api/dashboard/status" not in r.url else None)
    # Coming back to the tab is what wakes the dashboard's refresh; it is not
    # showing, so nothing is fetched and nothing keeps drawing behind chat.
    page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(800)
    assert asked == [], asked
    assert page.evaluate("() => document.querySelectorAll('#dashboardRoot [data-ld-on], #dashboardRoot canvas, #dashboardRoot video').length") == 0
    # Back again, the cards rise in afresh.
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .dash-body.is-entering [data-enter]", state="attached", timeout=15000)
