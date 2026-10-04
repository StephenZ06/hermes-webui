"""The live-chat scripts, in the order index.html loads them.

static/messages.js is being split into smaller files that load just before
it (stream_markdown.js, anchor_scene.js). Tests that inspect or execute the
chat code read this bundle, so a helper moving between those files does not
break them.
"""

import hashlib
import pathlib
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]

CHAT_JS_FILES = (
    REPO / "static" / "stream_markdown.js",
    REPO / "static" / "anchor_scene.js",
    REPO / "static" / "messages.js",
)


def chat_js_source() -> str:
    """The bundle's source text, files concatenated in load order."""
    return "\n".join(path.read_text(encoding="utf-8") for path in CHAT_JS_FILES)


def _cached_file(name: str, source: str) -> pathlib.Path:
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]
    path = pathlib.Path(tempfile.gettempdir()) / f"hermes-{name}-{digest}.js"
    if not path.exists():
        tmp = path.with_suffix(f".{digest}.tmp")
        tmp.write_text(source, encoding="utf-8")
        tmp.replace(path)
    return path


def chat_helpers_bundle_path() -> pathlib.Path:
    """The top-level helper files that load before messages.js, concatenated.

    For harnesses that evaluate only a slice of messages.js (e.g. the
    attachLiveStream closure): evaluate this first, as the browser does.
    """
    source = "\n".join(p.read_text(encoding="utf-8") for p in CHAT_JS_FILES[:-1])
    return _cached_file("chat-helpers", source)


def chat_js_bundle_path() -> pathlib.Path:
    """A file holding chat_js_source(), for Node harnesses that take a path.

    Keyed by content, so concurrent test processes never clobber each other.
    """
    return _cached_file("chat-bundle", chat_js_source())
