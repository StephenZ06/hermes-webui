"""Preview pictures for catalogued UI components.

For each component with a demo page, a headless browser (Playwright, when it
is installed) captures a 16:10 still and, for components that move, a ~3 s
animated WebP loop. Without Playwright, or when capture fails, the preview
falls back to the demo page's ``og:image``, then the library README's first
image. Results are summarised in ``previews/STATUS.json`` so the Libraries tab
can say when nothing could be captured. The user can replace any preview.
"""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from api import library_catalog as lc

WIDTH, HEIGHT = 1280, 800
LOOP_FRAMES, LOOP_STEP_MS = 12, 250
_MAX_IMAGE_BYTES = 6_000_000
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except Exception:
        return None


def _fetch(url: str, limit: int) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-webui-library-preview"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - the user's own catalog links
        return resp.read(limit + 1), resp.headers.get_content_type()


def _to_webp(data: bytes) -> bytes:
    """Re-encode any still image as a 16:10 WebP (cover crop)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.fit(img.convert("RGB"), (WIDTH // 2, HEIGHT // 2))
        out = io.BytesIO()
        img.save(out, "WEBP", quality=82)
        return out.getvalue()


def clear_preview(lib_dir: Path, slug: str) -> None:
    for old in (lib_dir / "previews").glob(f"{slug}.*"):
        old.unlink(missing_ok=True)


def save_still(lib_dir: Path, slug: str, data: bytes) -> Path:
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError("That image is too large (6 MB at most).")
    try:
        webp = _to_webp(data)
    except Exception as exc:
        raise ValueError("That file is not an image Hermes can read.") from exc
    previews = lib_dir / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    clear_preview(lib_dir, slug)
    path = previews / f"{slug}.webp"
    path.write_bytes(webp)
    return path


def _og_image(page_url: str) -> str:
    html, _ = _fetch(page_url, 2_000_000)
    text = html.decode("utf-8", "replace")
    match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', text, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', text, re.I)
    return urllib.parse.urljoin(page_url, match.group(1)) if match else ""


def readme_image(lib_dir: Path, source_link: str = "") -> bytes | None:
    """The first image the README shows: a file inside the source copy, or a URL."""
    src = lib_dir / "source"
    readme = next((p for p in sorted(src.glob("*")) if p.is_file() and p.name.lower().startswith("readme")), None) if src.is_dir() else None
    if not readme:
        return None
    text = readme.read_text(encoding="utf-8", errors="replace")
    for ref in re.findall(r'!\[[^\]]*\]\(([^)\s]+)|<img[^>]+src=["\']([^"\']+)', text):
        target = ref[0] or ref[1]
        if re.match(r"https?://", target):
            try:
                data, kind = _fetch(target, _MAX_IMAGE_BYTES)
            except Exception:
                continue
            if kind in IMAGE_TYPES and len(data) <= _MAX_IMAGE_BYTES:
                return data
            continue
        try:
            path = lc.safe_child(src, *[p for p in target.split("?")[0].split("/") if p and p != "."])
        except ValueError:
            continue
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            return path.read_bytes()[:_MAX_IMAGE_BYTES]
    return None


def _capture(pw_factory, url: str, moving: bool) -> tuple[bytes, list[bytes]]:
    with pw_factory() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(1200)
            still = page.screenshot(type="png")
            frames = []
            if moving:
                for _ in range(LOOP_FRAMES):
                    frames.append(page.screenshot(type="png"))
                    page.wait_for_timeout(LOOP_STEP_MS)
            return still, frames
        finally:
            browser.close()


def _save_loop(lib_dir: Path, slug: str, frames: list[bytes]) -> bool:
    from PIL import Image, ImageChops, ImageOps

    images = []
    for data in frames:
        with Image.open(io.BytesIO(data)) as img:
            images.append(ImageOps.fit(img.convert("RGB"), (WIDTH // 2, HEIGHT // 2)))
    if len(images) < 2 or all(ImageChops.difference(images[0], im).getbbox() is None for im in images[1:]):
        return False  # nothing moved: a loop would only cost bytes
    out = lib_dir / "previews" / f"{slug}.loop.webp"
    images[0].save(out, "WEBP", save_all=True, append_images=images[1:], duration=LOOP_STEP_MS, loop=0, quality=70)
    return True


def capture_library(root: Path, slug: str) -> dict:
    """Capture or fall back for every component of one library; writes STATUS.json."""
    lib_dir = lc.safe_child(root, lc.slugify(slug))
    [lib] = [l for l in lc.list_libraries(root) if l["slug"] == lib_dir.name] or [None]
    if lib is None:
        raise FileNotFoundError("No such library.")
    pw_factory = _playwright()
    fallback = readme_image(lib_dir, lib.get("source", ""))
    status = {"browser": bool(pw_factory), "captured": 0, "fallback": 0, "missing": 0}
    for comp in lib["components"]:
        if comp.get("preview"):
            continue  # keep what is there, including the user's own picture
        done = False
        if comp.get("demo") and pw_factory:
            try:
                still, frames = _capture(pw_factory, comp["demo"], comp.get("motion") not in ("", "none"))
                save_still(lib_dir, comp["slug"], still)
                if frames:
                    _save_loop(lib_dir, comp["slug"], frames)
                status["captured"] += 1
                done = True
            except Exception:
                done = False
        if not done and comp.get("demo"):
            try:
                og = _og_image(comp["demo"])
                if og:
                    data, kind = _fetch(og, _MAX_IMAGE_BYTES)
                    if kind in IMAGE_TYPES:
                        save_still(lib_dir, comp["slug"], data)
                        status["fallback"] += 1
                        done = True
            except Exception:
                done = False
        if not done and fallback:
            try:
                save_still(lib_dir, comp["slug"], fallback)
                status["fallback"] += 1
                done = True
            except ValueError:
                done = False
        if not done:
            status["missing"] += 1
    (lib_dir / "previews").mkdir(parents=True, exist_ok=True)
    (lib_dir / "previews" / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
    return status


def read_status(lib_dir: Path) -> dict | None:
    try:
        return json.loads((lib_dir / "previews" / "STATUS.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
