"""Primary Chat navigation uses the supplied dual-message mark."""
import pathlib


REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
SERVICE_WORKER = (REPO / "static" / "sw.js").read_text(encoding="utf-8")


def test_primary_chat_navigation_uses_the_custom_mark_in_desktop_and_mobile():
    assert INDEX.count('class="chat-nav-mark"') == 2
    assert (REPO / "static" / "chat-nav-mark.png").is_file()
    assert 'mask-image:url("chat-nav-mark.png")' in CSS
    assert '-webkit-mask-image:url("chat-nav-mark.png")' in CSS
    assert "'./static/chat-nav-mark.png'," in SERVICE_WORKER
