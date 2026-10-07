"""How the master resume looks, so tailored versions come out in the same design.

Read once from the uploaded file (PDF through pypdf's text visitor, DOCX from
its run properties) into a small profile: page size and margin, font family,
and the size/colour/weight of the name, headline, contact line, section
headings, entry lines and body text, plus the bullet mark and whether section
headings carry a rule. ``export.py`` renders tailored Markdown with it.

Every field has a default, so a plain-text master (or a file this can't read)
still exports cleanly in the previous neutral design.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from xml.etree import ElementTree

DEFAULT = {
    "source": "default",
    "page": "a4",
    "margin_pt": 45,
    "font": "Helvetica Neue",
    "serif": False,
    "align_header": "left",
    "bullet": "•",
    "name": {"size": 20, "color": "#111111", "bold": True},
    "headline": {"size": 11, "color": "#111111", "bold": True},
    "contact": {"size": 9.5, "color": "#444444", "bold": False},
    "heading": {"size": 11.5, "color": "#111111", "bold": True, "caps": True, "rule": True},
    "entry": {"size": 11, "color": "#111111", "bold": True},
    "entry_meta": {"size": 10, "color": "#444444", "bold": False},
    "body": {"size": 10.5, "color": "#111111", "bold": False},
}
_SERIF = ("times", "serif", "garamond", "georgia", "cambria", "palatino", "book antiqua", "baskerville")
# Metric-compatible names Word and browsers know.
VERSION = 1  # bump to re-read every stored profile after changing the reader
_FONT_ALIASES = {"liberation sans": "Arial", "liberation serif": "Times New Roman", "carlito": "Calibri",
                 "caladea": "Cambria", "arimo": "Arial", "tinos": "Times New Roman", "dejavu sans": "Verdana"}


def _family(base_font: str) -> str:
    """'/BAAAAA+LiberationSans-Bold' -> 'Liberation Sans'."""
    name = str(base_font or "").lstrip("/")
    name = name.split("+", 1)[-1]
    name = re.split(r"[-,]", name)[0]
    name = re.sub(r"(MT|PS|Std|Pro)$", "", name)
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()
    return name or DEFAULT["font"]


def _hex(rgb) -> str:
    try:
        r, g, b = (max(0, min(255, round(float(c) * 255))) for c in rgb)
    except (TypeError, ValueError):
        return "#111111"
    return f"#{r:02x}{g:02x}{b:02x}"


def _caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _style(seg: dict) -> dict:
    return {"size": round(float(seg["size"]) * 2) / 2, "color": seg["color"], "bold": bool(seg["bold"])}


def _bullet(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^\s*([-•▪●◦‣*–])\s+\S", line)
        if match:
            return "•" if match.group(1) in "*" else match.group(1)
    return DEFAULT["bullet"]


def profile_from_lines(lines: list[dict], *, page_w: float, page_h: float, text: str) -> dict:
    """The profile from the document's lines, in reading order. Each line:
    ``{"text", "x", "segments": [{"text", "size", "color", "bold", "font"}]}``."""
    lines = [ln for ln in lines if ln.get("segments") and ln["text"].strip()]
    if len(lines) < 5:
        return dict(DEFAULT)
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    out["source"] = "file"
    out["page"] = "letter" if abs(page_w - 612) < 8 and abs(page_h - 792) < 8 else "a4"
    weight = Counter()
    for ln in lines:
        for seg in ln["segments"]:
            weight[(round(seg["size"] * 2) / 2, seg["color"], seg["bold"])] += len(seg["text"])
    body_size, body_color, _ = next((k for k, _ in weight.most_common() if not k[2]), weight.most_common(1)[0][0])
    out["body"] = {"size": body_size, "color": body_color, "bold": False}
    xs = [ln["x"] for ln in lines if ln.get("x") is not None]
    margin = min(xs) if xs else DEFAULT["margin_pt"]
    out["margin_pt"] = round(max(18.0, min(90.0, margin)), 1)
    fonts = Counter(seg.get("font") or "" for ln in lines for seg in ln["segments"])
    family = _family(fonts.most_common(1)[0][0]) if fonts else DEFAULT["font"]
    out["font"] = _FONT_ALIASES.get(family.lower(), family)
    out["serif"] = any(word in family.lower() for word in _SERIF)

    first_seg = lambda ln: ln["segments"][0]  # noqa: E731
    name_line = max(lines[:4], key=lambda ln: first_seg(ln)["size"])
    out["name"] = _style(first_seg(name_line))
    centered = name_line.get("x") is not None and name_line["x"] > margin + 24
    out["align_header"] = "center" if centered else "left"

    # Section headings: short lines in capitals (or bold and larger than the body)
    # that recur down the page.
    def heading_like(ln):
        seg = first_seg(ln)
        short = len(ln["text"]) <= 48 and len(ln["segments"]) <= 2
        return short and ln is not name_line and seg["bold"] and (_caps(ln["text"]) or seg["size"] > body_size + 0.4)
    headings = [ln for ln in lines if heading_like(ln)]
    capital = [ln for ln in headings if _caps(ln["text"])]
    headings = capital if len(capital) >= 2 else headings  # a bold headline isn't a section
    if len(headings) >= 2:
        style = Counter((first_seg(h)["size"], first_seg(h)["color"]) for h in headings).most_common(1)[0][0]
        out["heading"] = {"size": style[0], "color": style[1], "bold": True,
                          "caps": sum(_caps(h["text"]) for h in headings) * 2 >= len(headings),
                          "rule": any(h.get("rule") for h in headings)}
    first_heading = lines.index(headings[0]) if headings else len(lines)

    # Between the name and the first heading: a bold headline, then the contact line(s).
    header = lines[lines.index(name_line) + 1:first_heading][:4]
    headline_found = False
    for ln in header:
        seg = first_seg(ln)
        if seg["bold"] and not headline_found:
            out["headline"] = _style(seg)
            headline_found = True
        elif not seg["bold"]:
            out["contact"] = _style(seg)
            break

    # Entry lines: bold, not headings, at the margin, often followed by a lighter
    # "| Company | Place" part on the same line.
    entries = [ln for ln in lines[first_heading:] if first_seg(ln)["bold"] and ln not in headings and not _caps(ln["text"])
               and len(ln["segments"]) >= 2]
    # "Title | Company | Place" lines, not "Skills: ..." labels, when there are any.
    entries = [e for e in entries if re.match(r"^\s*[|–—•·@]", e["segments"][1]["text"])] or entries
    if entries:
        size, color = Counter((first_seg(e)["size"], first_seg(e)["color"]) for e in entries).most_common(1)[0][0]
        out["entry"] = {"size": round(size * 2) / 2, "color": color, "bold": True}
        metas = [e["segments"][1] for e in entries if not e["segments"][1]["bold"]]
        if metas:
            out["entry_meta"] = _style(metas[0])
    out["bullet"] = _bullet(text)
    return out


# ---- PDF -------------------------------------------------------------------------
def _page_lines(page) -> list[dict]:
    """One PDF page's text lines (chunks on one baseline), with the fill colour
    in force for each chunk and whether a horizontal rule sits just under it."""
    chunks: list[dict] = []
    rules: list[float] = []
    state = {"color": (0.07, 0.07, 0.07), "move": None}

    def before(op, args, cm, tm):
        try:
            if op == b"rg" and len(args) == 3:
                state["color"] = tuple(float(a) for a in args)
            elif op == b"g" and len(args) == 1:
                state["color"] = (float(args[0]),) * 3
            elif op == b"re" and len(args) == 4:
                x, y, w, h = (float(a) for a in args)
                if abs(h) < 2.5 and abs(w) > 120:
                    rules.append(cm[3] * y + cm[5])
            elif op == b"m" and len(args) == 2:
                state["move"] = (float(args[0]), float(args[1]))
            elif op == b"l" and len(args) == 2 and state["move"]:
                x0, y0 = state["move"]
                x1, y1 = float(args[0]), float(args[1])
                if abs(y1 - y0) < 1 and abs(x1 - x0) > 120:
                    rules.append(cm[3] * y0 + cm[5])
        except (TypeError, ValueError):
            pass

    def visit(text, cm, tm, font, size):
        if not text or not text.strip():
            return
        scale = abs(tm[0]) or 1
        base = (font or {}).get("/BaseFont", "") if hasattr(font, "get") else ""
        chunks.append({"text": text.strip(), "size": float(size) * scale, "color": _hex(state["color"]),
                       "bold": bool(re.search(r"bold|black|heavy|semibold", str(base), re.I)),
                       "font": str(base), "x": float(tm[4]) * (cm[0] or 1) + cm[4], "y": float(tm[5]) * (cm[3] or 1) + cm[5]})

    page.extract_text(visitor_text=visit, visitor_operand_before=before)
    chunks.sort(key=lambda c: (-round(c["y"]), c["x"]))
    lines: list[dict] = []
    for chunk in chunks:
        if lines and abs(lines[-1]["y"] - chunk["y"]) < 2.5:
            lines[-1]["segments"].append(chunk)
            lines[-1]["text"] += " " + chunk["text"]
            continue
        lines.append({"text": chunk["text"], "x": chunk["x"], "y": chunk["y"], "segments": [chunk]})
    for ln in lines:
        if any(0 < ln["y"] - r < 16 for r in rules):
            ln["rule"] = True
    return lines


def _pdf_lines(data: bytes) -> tuple[list[dict], float, float]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = reader.pages[:3]
    if not pages:
        return [], 612, 792
    box = pages[0].mediabox
    return [ln for page in pages for ln in _page_lines(page)], float(box.width), float(box.height)


# ---- DOCX ------------------------------------------------------------------------
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_lines(data: bytes) -> tuple[list[dict], float, float]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        try:
            styles = ElementTree.fromstring(archive.read("word/styles.xml"))
        except KeyError:
            styles = None
    default_size, default_font = 11.0, ""
    if styles is not None:
        rpr = styles.find(f"{_W}docDefaults/{_W}rPrDefault/{_W}rPr")
        if rpr is not None:
            sz = rpr.find(f"{_W}sz")
            if sz is not None:
                default_size = float(sz.get(f"{_W}val", 22)) / 2
            fonts = rpr.find(f"{_W}rFonts")
            if fonts is not None:
                default_font = fonts.get(f"{_W}ascii") or ""
    page_w, page_h = 595.0, 842.0
    pg = root.find(f".//{_W}sectPr/{_W}pgSz")
    if pg is not None:
        page_w, page_h = float(pg.get(f"{_W}w", 11906)) / 20, float(pg.get(f"{_W}h", 16838)) / 20
    margin = 72.0
    mar = root.find(f".//{_W}sectPr/{_W}pgMar")
    if mar is not None:
        margin = float(mar.get(f"{_W}left", 1440)) / 20
    lines = []
    for para in root.iter(f"{_W}p"):
        segments = []
        for run in para.iter(f"{_W}r"):
            text = "".join(t.text or "" for t in run.iter(f"{_W}t"))
            if not text.strip():
                continue
            rpr = run.find(f"{_W}rPr")
            size, color, bold, font = default_size, "#111111", False, default_font
            if rpr is not None:
                sz = rpr.find(f"{_W}sz")
                if sz is not None:
                    size = float(sz.get(f"{_W}val", size * 2)) / 2
                col = rpr.find(f"{_W}color")
                if col is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", col.get(f"{_W}val", "")):
                    color = "#" + col.get(f"{_W}val").lower()
                b = rpr.find(f"{_W}b")
                bold = b is not None and b.get(f"{_W}val", "true") not in ("0", "false")
                fonts = rpr.find(f"{_W}rFonts")
                if fonts is not None and fonts.get(f"{_W}ascii"):
                    font = fonts.get(f"{_W}ascii")
            segments.append({"text": text.strip(), "size": size, "color": color, "bold": bold, "font": font})
        if not segments:
            continue
        jc = para.find(f"{_W}pPr/{_W}jc")
        centered = jc is not None and jc.get(f"{_W}val") == "center"
        border = para.find(f"{_W}pPr/{_W}pBdr/{_W}bottom") is not None
        lines.append({"text": " ".join(s["text"] for s in segments), "x": margin + (60 if centered else 0),
                      "segments": segments, "rule": border})
    return lines, page_w, page_h


def extract_profile(filename: str, data: bytes, text: str) -> dict:
    """The look of the uploaded resume; the default design if it can't be read."""
    suffix = str(filename or "").lower().rsplit(".", 1)[-1]
    try:
        if suffix == "pdf":
            lines, w, h = _pdf_lines(data)
        elif suffix == "docx":
            lines, w, h = _docx_lines(data)
        else:
            return {**DEFAULT, "bullet": _bullet(text)}
        return profile_from_lines(lines, page_w=w, page_h=h, text=text)
    except Exception:  # an unreadable layout only costs the design, never the upload
        return {**DEFAULT, "bullet": _bullet(text)}
