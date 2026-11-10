"""Serve static/i18n.js one language at a time.

static/i18n.js holds every UI language (about 2 MB, 540 KB gzipped) and is the
single source the tests and translators edit. Loading all of it on every visit
costs more than any other file on the page, while a visitor reads one language.

The file is not rewritten. At request time the server slices it:

* ``i18n.js?lang=xx`` -- the page's copy: English (the fallback for every
  missing key), the language ``xx``, and a stub for every other language that
  carries only its ``_label`` (so the language picker still lists it) and
  ``_lazy: true``. Selecting a stubbed language makes i18n.js load it.
* ``i18n.js?locale=xx`` -- one language's block, merged into ``LOCALES``.
* ``i18n.js`` without either -- the whole file, unchanged.

Slicing relies on the file's layout: ``const LOCALES = {``, then one block per
language that opens with a two-space-indented ``code: {`` line, then the
closing ``};``. If that layout is not found, the variants return None and the
caller serves the whole file (fail closed: the page still gets every string).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

_OPEN = "const LOCALES = {\n"
_BLOCK_START = re.compile(r"^  (?:'([A-Za-z][\w-]*)'|([A-Za-z][\w-]*)): \{\s*$")
_LABEL = re.compile(r"^\s{4}_label:\s*('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")\s*,", re.M)
_CODE = re.compile(r"^[A-Za-z][\w-]{0,15}$")


@dataclass(frozen=True)
class _Split:
    head: str            # everything up to and including "const LOCALES = {\n"
    blocks: dict         # code -> the block's source lines, "  code: {" through its "},"
    labels: dict         # code -> its _label literal, as written in the source
    tail: str            # from the "};" that closes LOCALES to the end of the file


_lock = threading.Lock()
_cache: dict = {}


def _split(text: str) -> _Split | None:
    start = text.find(_OPEN)
    if start < 0:
        return None
    body_start = start + len(_OPEN)
    close = re.compile(r"^\};\s*$", re.M).search(text, body_start)
    if not close:
        return None
    lines = text[body_start:close.start()].splitlines(keepends=True)
    starts = []
    for index, line in enumerate(lines):
        match = _BLOCK_START.match(line)
        if match:
            starts.append((index, match.group(1) or match.group(2)))
    if not starts or starts[0][0] != 0 and any(l.strip() for l in lines[:starts[0][0]]):
        return None
    blocks, labels = {}, {}
    for position, (index, code) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        # A block ends at its last "}," line; what follows before the next
        # block may only be blank lines or // comments (they are dropped).
        last = end - 1
        while last > index and (not lines[last].strip() or lines[last].lstrip().startswith("//")):
            last -= 1
        block = "".join(lines[index:last + 1]).rstrip() + "\n"
        if code in blocks or lines[last].strip() != "},":
            return None
        label = _LABEL.search(block)
        if not label:
            return None
        blocks[code] = block
        labels[code] = label.group(1)
    if "en" not in blocks:
        return None
    return _Split(text[:body_start], blocks, labels, text[close.start():])


def _split_cached(text: str, signature) -> _Split | None:
    with _lock:
        hit = _cache.get("split")
        if hit and hit[0] == signature:
            return hit[1]
    split = _split(text)
    with _lock:
        _cache["split"] = (signature, split)
    return split


def _key(code: str) -> str:
    return code if re.match(r"^[A-Za-z_]\w*$", code) else f"'{code}'"


def page_bundle(text: str, lang: str, signature=None) -> str | None:
    """English, ``lang`` and a stub for every other language; None to serve the whole file."""
    split = _split_cached(text, signature) if signature is not None else _split(text)
    if split is None:
        return None
    keep = {"en", lang} if lang in split.blocks else {"en"}
    parts = [split.head]
    for code, block in split.blocks.items():
        if code in keep:
            parts.append(block)
        else:
            parts.append(f"  {_key(code)}: {{ _label: {split.labels[code]}, _lazy: true }},\n")
    parts.append(split.tail)
    return "".join(parts)


def locale_patch(text: str, code: str, signature=None) -> str | None:
    """One language's block, merged into LOCALES; None when there is no such language."""
    if not _CODE.match(code or ""):
        return None
    split = _split_cached(text, signature) if signature is not None else _split(text)
    if split is None or code not in split.blocks:
        return None
    return ("Object.assign(LOCALES, {\n" + split.blocks[code] + "});\n"
            f"if (typeof _i18nLocaleArrived === 'function') _i18nLocaleArrived({_key_literal(code)});\n")


def _key_literal(code: str) -> str:
    return "'" + code.replace("\\", "\\\\").replace("'", "\\'") + "'"


def known_codes(text: str) -> list[str]:
    split = _split(text)
    return list(split.blocks) if split else []
