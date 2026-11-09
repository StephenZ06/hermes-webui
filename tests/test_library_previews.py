"""Component previews: captured stills and loops, og:image and README
fallbacks, the user's own picture, and the status the Libraries tab shows."""

import io
import json

import pytest
from PIL import Image

from api import library_catalog as lc
from api import library_previews as lp


def _png(color=(200, 30, 30), size=(320, 200)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "libraries"
    lc.save_library(root, "calm", {"name": "Calm", "kind": "npm", "frameworks": ["react"], "source": "https://x"},
                    [{"name": "Fade", "role": "text-effect", "style": ["minimal"], "motion": "subtle", "platform": ["web"], "demo": "https://demo/fade"},
                     {"name": "Card", "role": "cards", "style": ["bold"], "motion": "none", "platform": ["web"]}])
    return root


def test_a_still_is_stored_as_a_16_by_10_webp_and_bad_files_are_refused(lib):
    path = lp.save_still(lib / "calm", "fade", _png(size=(500, 500)))
    with Image.open(path) as img:
        assert img.format == "WEBP" and img.size == (lp.WIDTH // 2, lp.HEIGHT // 2)
    with pytest.raises(ValueError):
        lp.save_still(lib / "calm", "fade", b"not an image")
    with pytest.raises(ValueError):
        lp.save_still(lib / "calm", "fade", b"x" * (lp._MAX_IMAGE_BYTES + 1))


def test_a_loop_is_only_kept_when_something_moved(lib):
    (lib / "calm" / "previews").mkdir()
    same = [_png()] * 3
    assert lp._save_loop(lib / "calm", "fade", same) is False
    assert lp._save_loop(lib / "calm", "fade", [_png((i * 40, 0, 0)) for i in range(4)]) is True
    with Image.open(lib / "calm" / "previews" / "fade.loop.webp") as img:
        assert img.n_frames == 4


def test_without_a_browser_the_demo_og_image_then_the_readme_image_are_used(lib, monkeypatch):
    src = lib / "calm" / "source"
    (src / "docs").mkdir(parents=True)
    (src / "docs" / "shot.png").write_bytes(_png((0, 0, 200)))
    (src / "README.md").write_text("# Calm\n![escape](../../../etc/passwd)\n![shot](./docs/shot.png)\n")
    monkeypatch.setattr(lp, "_playwright", lambda: None)

    def fetch(url, limit):
        if url == "https://demo/fade":
            return b'<html><meta property="og:image" content="/og.png"></html>', "text/html"
        if url == "https://demo/og.png":
            return _png((0, 200, 0)), "image/png"
        raise OSError(url)
    monkeypatch.setattr(lp, "_fetch", fetch)
    status = lp.capture_library(lib, "calm")
    assert status == {"browser": False, "captured": 0, "fallback": 2, "missing": 0}
    comps = {c["slug"]: c for c in lc.list_libraries(lib)[0]["components"]}
    assert comps["fade"]["preview"] == "calm/previews/fade.webp"
    with Image.open(lib / "calm" / "previews" / "fade.webp") as img:
        assert img.convert("RGB").getpixel((10, 10))[1] > 150  # the green og:image
    with Image.open(lib / "calm" / "previews" / "card.webp") as img:
        assert img.convert("RGB").getpixel((10, 10))[2] > 150  # the blue README image
    assert lc.list_libraries(lib)[0]["preview_status"] == status


def test_existing_previews_are_kept_and_nothing_found_is_counted_missing(lib, monkeypatch):
    monkeypatch.setattr(lp, "_playwright", lambda: None)
    monkeypatch.setattr(lp, "_fetch", lambda url, limit: (_ for _ in ()).throw(OSError("offline")))
    lp.save_still(lib / "calm", "card", _png())
    before = (lib / "calm" / "previews" / "card.webp").read_bytes()
    status = lp.capture_library(lib, "calm")
    assert status["missing"] == 1 and status["fallback"] == 0
    assert (lib / "calm" / "previews" / "card.webp").read_bytes() == before


def test_previews_in_png_or_jpg_are_listed_too(lib):
    (lib / "calm" / "previews").mkdir()
    (lib / "calm" / "previews" / "card.png").write_bytes(_png())
    comps = {c["slug"]: c for c in lc.list_libraries(lib)[0]["components"]}
    assert comps["card"]["preview"] == "calm/previews/card.png"
