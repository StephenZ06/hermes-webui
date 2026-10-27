"""Posting guard: postings are text from strangers, so clean and check them.

Every posting Job OS saves passes through here before Luna reads it next to
your resume. The guard removes text a person reading the page would never see
(hidden HTML, comments, script and style blocks, zero-width and bidi control
characters, Unicode tag characters) and flags text that looks aimed at an AI
agent rather than a candidate: instruction-shaped lines, words that mix Latin
with Cyrillic or Greek look-alike letters, and links that only exist in hidden
text.

It advises and never blocks: a flagged job is still saved and scored, and
visible text is never removed, only quoted in the findings.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import html
import re
import unicodedata
from html.parser import HTMLParser

EXCERPTS = 3
EXCERPT_CHARS = 160

# Characters a reader never sees. Zero-width joiners are only removed between
# Latin letters, where they can only be hiding something (scripts such as
# Persian or Devanagari need them).
_INVISIBLE = {"​", "⁠", "﻿", "­", "᠎", "⁡", "⁢", "⁣", "⁤"}
_JOINERS = {"‌", "‍"}
_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F, 0x061C)}
_OVERRIDES = {"‭", "‮"}
_TAG_RANGE = range(0xE0000, 0xE0080)

_INSTRUCTIONS = [re.compile(p, re.I) for p in (
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|any|your)\b.{0,30}"
    r"\b(instructions?|prompts?|rules|directions|guidelines)\b",
    r"\bif you are (an? )?(ai|a\.i\.|llm|bot|language model|assistant|gpt|chatbot|automated)\b",
    r"\b(dear|attention|note to( the)?|hey)\b,? (ai|llm|language model|assistant|chatgpt|gpt|claude|recruit\w* bot)\b",
    r"\byou are (now )?(an? )?(ai|assistant|language model|chatgpt|gpt|claude|llm)\b",
    r"\bsystem prompt\b",
    r"\b(rate|score|rank|mark|evaluate)\b.{0,30}\b(this|the|every|each)\b.{0,15}\b(candidate|applicant|resume|cv)\b"
    r".{0,40}\b(highly|100|top|10/10|perfect|best|strong(est)?)\b",
    r"\b(include|mention|add|write|insert)\b.{0,40}\b(the (word|phrase|code)|this (word|phrase|code))\b",
    r"\bnew instructions?\b",
)]
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d]*[1-9])|"
                           r"opacity\s*:\s*0(?![.\d]*[1-9])|(?:^|;)\s*color\s*:\s*transparent", re.I)
_DROP_BLOCKS = {"script", "style", "template", "noscript"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_LINK = re.compile(r"https?://[^\s<>\"']+", re.I)
_WORD = re.compile(r"\w{2,}", re.U)


def _empty() -> dict:
    return {"hidden_html": 0, "hidden_links": 0, "invisible": 0, "bidi": 0, "tag_chars": 0,
            "instructions": 0, "mixed_script": 0}


def _excerpt(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS - 1] + "…"


class _Stripper(HTMLParser):
    """Re-emits markup without hidden elements, comments or script blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.hidden: list[str] = []  # open tags inside the current hidden element
        self.hidden_text: list[str] = []
        self.hidden_elements = 0
        self._block = False

    @staticmethod
    def _is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in _DROP_BLOCKS:
            return True
        values = {k.lower(): (v or "") for k, v in attrs}
        if "hidden" in values or values.get("aria-hidden", "").lower() == "true":
            return True
        if tag == "input" and values.get("type", "").lower() == "hidden":
            return True
        return bool(_HIDDEN_STYLE.search(values.get("style", "")))

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag not in _VOID:
                self.hidden.append(tag)
            return
        if self._is_hidden(tag, attrs):
            if tag not in _DROP_BLOCKS:
                self.hidden_elements += 1
            if tag not in _VOID:
                self.hidden.append(tag)
            self._block = tag in _DROP_BLOCKS
            return
        self.out.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self.hidden or self._is_hidden(tag, attrs):
            return
        self.out.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag in self.hidden:
                while self.hidden and self.hidden.pop() != tag:
                    pass
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.hidden:
            if not self._block:
                self.hidden_text.append(data)
            return
        self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        if not self.hidden and _LINK.search(data or ""):
            self.hidden_text.append(data)


def strip_hidden_html(markup: str) -> tuple[str, dict]:
    """Remove hidden elements, comments and script/style/template blocks from
    HTML before it becomes text. Returns ``(markup, findings)``."""
    findings = {"counts": _empty(), "excerpts": []}
    raw = str(markup or "")
    if "<" not in raw:
        return raw, findings
    parser = _Stripper()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:  # malformed markup: fall back to the caller's own tag stripping
        return raw, findings
    hidden = " ".join(t.strip() for t in parser.hidden_text if t.strip())
    counts = findings["counts"]
    if hidden:
        counts["hidden_html"] = max(1, parser.hidden_elements)
        counts["hidden_links"] = len(_LINK.findall(hidden))
        findings["excerpts"].append("Hidden: " + _excerpt(hidden))
    return "".join(parser.out), findings


def _script(ch: str) -> str:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(script):
            return script
    return ""


def _mixed_script(word: str) -> bool:
    scripts = {_script(ch) for ch in word if ch.isalpha()} - {""}
    return "LATIN" in scripts and len(scripts) > 1


def guard_text(text: str, hidden: dict | None = None) -> tuple[str, dict]:
    """Clean one posting's text and report what was found.

    Returns ``(clean_text, findings)`` where ``findings`` is
    ``{"verdict": "clean"|"flagged", "counts": {...}, "excerpts": [...]}``.
    ``hidden`` carries findings from ``strip_hidden_html`` on the same posting.
    """
    counts = _empty()
    excerpts: list[str] = []
    if hidden:
        for key, value in (hidden.get("counts") or {}).items():
            if key in counts:
                counts[key] += int(value or 0)
        excerpts.extend(hidden.get("excerpts") or [])
    source = str(text or "")
    out: list[str] = []
    tagged: list[str] = []
    for index, ch in enumerate(source):
        code = ord(ch)
        if code in _TAG_RANGE:
            counts["tag_chars"] += 1
            if 0xE0020 <= code <= 0xE007E:
                tagged.append(chr(code - 0xE0000))
            continue
        if tagged:
            excerpts.append("Tag characters: " + _excerpt("".join(tagged)))
            tagged = []
        if ch in _INVISIBLE:
            counts["invisible"] += 1
            continue
        if ch in _JOINERS:
            before = source[index - 1] if index else ""
            after = source[index + 1] if index + 1 < len(source) else ""
            if before.isascii() and before.isalpha() and after.isascii() and after.isalpha():
                counts["invisible"] += 1
                continue
        if ch in _BIDI:
            counts["bidi"] += 1 if ch not in _OVERRIDES else 2
            continue
        out.append(ch)
    if tagged:
        excerpts.append("Tag characters: " + _excerpt("".join(tagged)))
    clean = "".join(out)
    hidden_words = source != clean and _hides_inside_words(source)
    for line in clean.splitlines():
        if any(p.search(line) for p in _INSTRUCTIONS):
            counts["instructions"] += 1
            excerpts.append(_excerpt(line))
    for word in _WORD.findall(clean):
        if _mixed_script(word):
            counts["mixed_script"] += 1
            if counts["mixed_script"] == 1:
                excerpts.append("Look-alike letters: " + _excerpt(word))
    flagged = bool(counts["instructions"] or counts["tag_chars"] or counts["mixed_script"] or counts["hidden_html"]
                   or counts["bidi"] >= 2 or hidden_words)
    findings = {"verdict": "flagged" if flagged else "clean",
                "counts": {k: v for k, v in counts.items() if v},
                "excerpts": list(dict.fromkeys(excerpts))[:EXCERPTS]}
    return clean, findings


def _hides_inside_words(text: str) -> bool:
    """A zero-width character between two letters splits a word to dodge filters."""
    for index in range(1, len(text) - 1):
        ch = text[index]
        if (ch in _INVISIBLE or ch in _JOINERS) and text[index - 1].isascii() and text[index - 1].isalpha() \
                and text[index + 1].isascii() and text[index + 1].isalpha():
            return True
    return False


def summary(findings: dict | None) -> str:
    """One line for a chip's tooltip or the drawer."""
    if not findings or findings.get("verdict") != "flagged":
        return ""
    counts = findings.get("counts") or {}
    parts = []
    if counts.get("instructions"):
        parts.append(f"{counts['instructions']} instruction-like line{'s' if counts['instructions'] != 1 else ''}")
    if counts.get("hidden_html"):
        parts.append("hidden text")
    if counts.get("tag_chars"):
        parts.append("invisible tag characters")
    if counts.get("mixed_script"):
        parts.append("look-alike letters")
    if counts.get("bidi"):
        parts.append("direction overrides")
    if counts.get("invisible") and not parts:
        parts.append("characters hidden inside words")
    return "Found " + ", ".join(parts) if parts else "Hidden content found"


def public(findings: dict | None) -> dict | None:
    """What the page sees: only a flagged posting carries its findings."""
    if not findings or findings.get("verdict") != "flagged":
        return None
    return {"verdict": "flagged", "summary": summary(findings), "excerpts": list(findings.get("excerpts") or [])[:EXCERPTS]}
