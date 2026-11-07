"""Files: previews drawn from the file, live space status, the filter row and the empty inspector."""

import io

from PIL import Image

from tests.test_chat_optical_alignment_browser import _ink, browser, pytestmark, real_2x  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved
from tests.test_pages_round11_browser import _open

ENTRIES = [
    {"name": "photo.png", "path": "photo.png", "type": "file", "size": 2048},
    {"name": "clip.mp4", "path": "clip.mp4", "type": "file", "size": 4096},
    {"name": "song.mp3", "path": "song.mp3", "type": "file", "size": 4096},
    {"name": "paper.pdf", "path": "paper.pdf", "type": "file", "size": 4096},
    {"name": "blob.bin", "path": "blob.bin", "type": "file", "size": 99},
    {"name": "notes.md", "path": "notes.md", "type": "file", "size": 6},
]


def _png(width, height):
    out = io.BytesIO()
    Image.new("RGB", (width, height), (40, 160, 90)).save(out, "PNG")
    return out.getvalue()


def _space(page, spaces=None):
    """One space with an image, media, a PDF, a binary and a text file; records what the page asked for."""
    asked = {"read": [], "raw": []}
    state = {"spaces": spaces or [{"id": "a", "name": "Home", "available": True}, {"id": "b", "name": "Pi", "available": False}]}
    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": state["spaces"]}))
    page.route("**/api/file-manager/list*", lambda route: route.fulfill(json={"path": ".", "entries": ENTRIES}))

    def read(route):
        asked["read"].append(route.request.url)
        if "blob.bin" in route.request.url:
            return route.fulfill(json={"path": "blob.bin", "size": 99, "preview_kind": "binary"})
        return route.fulfill(json={"path": "notes.md", "content": "hello\n", "size": 6, "lines": 2})
    page.route("**/api/file-manager/read*", read)

    def raw(route):
        asked["raw"].append(route.request.url)
        if "photo.png" in route.request.url:
            return route.fulfill(body=_png(64, 48), content_type="image/png")
        return route.fulfill(status=200, body=b"", content_type="application/octet-stream")
    page.route("**/api/file-manager/raw*", raw)
    return asked, state


def _pick(page, name):
    page.click(f".files-row[data-file-path='{name}']")
    page.wait_for_selector(".files-inspector-header")
    page.wait_for_timeout(300)


def test_an_image_opens_as_the_picture_with_its_pixel_size(real_2x):
    page = real_2x
    asked, _ = _space(page)
    _open(page, "files", ".files-row")
    _pick(page, "photo.png")
    page.wait_for_selector(".files-media-image img.is-loaded")
    out = page.evaluate("""() => { const img = document.querySelector('.files-media-image img');
      return {w: img.naturalWidth, h: img.naturalHeight, editor: !!document.querySelector('.files-editor'),
        meta: document.querySelector('.files-inspector-meta').textContent}; }""")
    assert out == {"w": 64, "h": 48, "editor": False, "meta": "2 KB · Image · 64 × 48"}, out
    assert asked["read"] == []
    assert "path=photo.png" in asked["raw"][0] and "download=1" not in asked["raw"][0]


def test_video_audio_and_pdf_open_in_their_players(real_2x):
    page = real_2x
    asked, _ = _space(page)
    _open(page, "files", ".files-row")
    for name, selector in (("clip.mp4", ".files-media-video video[controls]"), ("song.mp3", ".files-media-audio audio[controls]"),
                           ("paper.pdf", ".files-media-pdf iframe")):
        _pick(page, name)
        src = page.eval_on_selector(selector, "e => e.getAttribute('src')")
        assert src.startswith("/api/file-manager/raw?") and f"path={name}" in src, (name, src)
    assert asked["read"] == []


def test_a_binary_file_offers_a_download_instead_of_characters(real_2x):
    page = real_2x
    _space(page)
    _open(page, "files", ".files-row")
    _pick(page, "blob.bin")
    out = page.evaluate("""() => ({editor: !!document.querySelector('.files-editor'),
      text: document.querySelector('.files-preview-unavailable').textContent,
      download: !!document.querySelector('.files-preview-unavailable [data-action=download]')})""")
    assert out["editor"] is False and out["download"] is True, out
    assert "not text" in out["text"], out
    _pick(page, "notes.md")
    assert page.eval_on_selector(".files-editor", "e => e.value") == "hello\n"


def test_downloads_stream_the_whole_file(real_2x):
    page = real_2x
    _space(page)
    _open(page, "files", ".files-row")
    _pick(page, "photo.png")
    with page.expect_download() as info:
        page.click(".files-inspector-actions [data-action=download]")
    # Straight from the stream, so a file of any size downloads (the old route read it whole, 400 KB at most).
    assert info.value.suggested_filename == "photo.png"
    assert "/api/file-manager/raw?" in info.value.url and "download=1" in info.value.url, info.value.url


def test_space_dots_are_green_online_red_offline_and_follow_the_status(real_2x):
    page = real_2x
    _, state = _space(page)
    _open(page, "files", "#filesSidebarHost .files-workspace")
    colour = lambda wid: page.eval_on_selector(f"#filesSidebarHost [data-workspace-id='{wid}'] .files-workspace-dot",
                                               "e => [getComputedStyle(e).backgroundColor, getComputedStyle(e).boxShadow !== 'none']")
    green, glow = colour("a")
    red, _ = colour("b")
    r, g, b = [int(v) for v in green[green.index("(") + 1:green.index(")")].split(",")[:3]]
    assert g > r + 40 and g > b + 20 and glow, green
    r, g, b = [int(v) for v in red[red.index("(") + 1:red.index(")")].split(",")[:3]]
    assert r > g + 60 and r > b + 40, red
    # The space drops off: the page notices on its own, here when the tab comes back into view.
    state["spaces"] = [{"id": "a", "name": "Home", "available": False}, {"id": "b", "name": "Pi", "available": True}]
    page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_selector("#filesSidebarHost [data-workspace-id='a'] .files-workspace-dot.is-offline")
    page.wait_for_selector("#filesSidebarHost [data-workspace-id='b'] .files-workspace-dot.is-online")


def test_the_dots_sit_a_pixel_lower(real_2x):
    page = real_2x
    _space(page)
    _open(page, "files", "#filesSidebarHost .files-workspace")
    dot = "#filesSidebarHost [data-workspace-id='a'] .files-workspace-dot"
    now = page.eval_on_selector(dot, "e => e.getBoundingClientRect().top")
    handle = page.add_style_tag(content=".files-workspace-dot{top:0!important}")
    before = page.eval_on_selector(dot, "e => e.getBoundingClientRect().top")
    handle.evaluate("e => e.remove()")
    assert now - before == 1


def test_the_filter_sits_under_the_divider_with_equal_room_and_reads_filter(real_2x):
    page = real_2x
    _space(page)
    _open(page, "files", ".files-row")
    page.mouse.move(5, 900)
    out = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect(), path = document.querySelector('.files-path');
      const input = r('.files-search input');
      return {divider: getComputedStyle(path).borderBottomStyle, toolbarRule: getComputedStyle(document.querySelector('.files-list-toolbar')).borderBottomStyle,
        above: input.top - path.getBoundingClientRect().bottom, below: r('.files-row').top - input.bottom,
        placeholder: document.querySelector('.files-search input').placeholder}; }""")
    assert out == {"divider": "solid", "toolbarRule": "none", "above": 10, "below": 10, "placeholder": "Filter"}, out
    shift = _moved(page, ".files-search input", "text", ".files-search input{padding-bottom:0!important}")
    assert shift == -0.5, shift


def test_select_a_file_has_equal_room_above_and_below(real_2x):
    page = real_2x
    _space(page)
    _open(page, "files", ".files-inspector-empty")
    icon = _ink(page, ".files-inspector-empty", "icon")
    title = _ink(page, ".files-inspector-empty strong", "text")
    line = _ink(page, ".files-inspector-empty span", "text")
    assert abs((title["top"] - icon["bottom"]) - (line["top"] - title["bottom"])) <= .5, (icon, title, line)


def test_the_raw_route_streams_a_real_file_with_ranges(real_2x):
    """End to end against the test server's own space: upload bytes, read them back whole and in part."""
    import base64

    from tests._pytest_port import BASE
    page = real_2x
    spaces = page.request.get(BASE + "/api/file-manager/workspaces").json()["workspaces"]
    space = next(item for item in spaces if item["available"] and not item["read_only"])
    data = _png(8, 8) + b"\x00" * 600_000  # past the 400 KB text-read limit
    upload = page.request.post(BASE + "/api/file-manager/upload", data={
        "workspace_id": space["id"], "path": ".", "filename": "zz-raw-probe.png", "data_base64": base64.b64encode(data).decode()})
    assert upload.ok, upload.text()
    try:
        url = f"{BASE}/api/file-manager/raw?workspace_id={space['id']}&path=zz-raw-probe.png"
        whole = page.request.get(url)
        assert whole.status == 200 and whole.headers["content-type"] == "image/png" and whole.body() == data
        assert whole.headers["content-disposition"].startswith("inline")
        part = page.request.get(url, headers={"Range": "bytes=0-7"})
        assert part.status == 206 and part.body() == data[:8]
        assert page.request.get(url + "&download=1").headers["content-disposition"].startswith("attachment")
        missing = page.request.get(f"{BASE}/api/file-manager/raw?workspace_id={space['id']}&path=../etc/passwd")
        assert missing.status == 400
    finally:
        page.request.post(BASE + "/api/file-manager/delete", data={"workspace_id": space["id"], "path": "zz-raw-probe.png"})
