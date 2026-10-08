"""Primary Office navigation uses the supplied city mark."""
import pathlib
import hashlib


REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
SERVICE_WORKER = (REPO / "static" / "sw.js").read_text(encoding="utf-8")


def test_primary_office_navigation_uses_the_custom_mark_in_desktop_and_mobile():
    # The rail and the mobile nav; the chat Workspace panel's Office tab reuses it.
    assert INDEX.count('class="office-nav-mark"') == 3
    assert (REPO / "static" / "office-nav-mark.png").is_file()
    assert 'mask-image:url("office-nav-mark.png")' in CSS
    assert '-webkit-mask-image:url("office-nav-mark.png")' in CSS
    assert "'./static/office-nav-mark.png'," in SERVICE_WORKER


def test_office_navigation_uses_the_selected_people_mark_asset():
    asset = REPO / "static" / "office-nav-mark.png"
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == "b55ba95b1b80c524ac1f5eda52c17fea49d7727a0a9e7a084d22d4e8575d89aa"
