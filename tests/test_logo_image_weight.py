"""The logos shown inside pages are sized for where they are drawn.

The empty-chat logo (100px) and the login logo (56px) used to load the 512px
install icon, a 250 KB PNG; the tab icon (favicon.svg) wrapped a 512px PNG
for 341 KB. They now load a 200px WebP and a WebP-backed SVG.
"""

import re
import urllib.request

from tests._pytest_port import BASE


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as response:
        return response.read()


def _logo_src(html, marker):
    tag = re.search(marker + r'[^>]*?<img[^>]*src="([^"]+)"|<img[^>]*class="logo"[^>]*src="([^"]+)"', html)
    assert tag, f"no logo after {marker!r}"
    return "/" + (tag.group(1) or tag.group(2)).lstrip("/")


def test_the_empty_chat_logo_is_a_small_image():
    html = _get("/").decode("utf-8")
    body = _get(_logo_src(html, r'class="empty-logo">'))
    assert len(body) < 40_000, len(body)
    assert body[:4] == b"RIFF" and body[8:12] == b"WEBP"


def test_the_login_logo_is_a_small_image():
    html = _get("/login").decode("utf-8")
    src = re.search(r'<img class="logo" src="([^"]+)"', html)
    assert src, "login page has no logo"
    body = _get("/" + src.group(1).lstrip("/"))
    assert len(body) < 40_000, len(body)


def test_the_tab_icon_is_no_longer_a_wrapped_png():
    body = _get("/static/favicon.svg")
    assert len(body) < 200_000, len(body)
    assert b"data:image/webp;base64," in body
