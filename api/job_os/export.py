"""Export tailored documents: Markdown, printable HTML (-> PDF), and DOCX.

Only the small Markdown subset tailoring produces is supported: '#'/'##'/'###'
headings, '- '/'* ' bullets, paragraphs, **bold**, *italic* and [links](url).
DOCX is written with the standard library (one simple, ATS-friendly column:
no tables, text boxes or images). PDF is the browser's own print-to-PDF of the
HTML page, which keeps the text selectable and parseable.

A resume is drawn in the master resume's own design (``resume_style.py``):
its page size, margins, font, colours and sizes, header alignment, heading
rules and bullet mark. Tailored Markdown keeps the master's layout:

    # Name
    **Headline**                      <- bold header line(s)
    City | phone | email              <- other header line(s)
    ## SECTION
    ### Title | Company | Place | Dates
    - bullet
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))")


def _default_style() -> dict:
    from api.job_os.resume_style import DEFAULT

    return DEFAULT


def _blocks(markdown: str):
    """Yield ("h1"|"h2"|"h3"|"li"|"p", text) from the supported Markdown subset."""
    para: list[str] = []
    for raw in str(markdown or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        bullet = re.match(r"^\s*[-*•▪●–]\s+(.*)$", line)
        if heading or bullet or not line.strip():
            if para:
                yield "p", " ".join(para)
                para = []
            if heading:
                yield f"h{len(heading.group(1))}", heading.group(2).strip()
            elif bullet:
                yield "li", bullet.group(1).strip()
        else:
            para.append(line.strip())
    if para:
        yield "p", " ".join(para)


def _roles(markdown: str, resume: bool):
    """Blocks with their role in the design: name, headline, contact, heading,
    entry, bullet or body. Header lines are the paragraphs between the name and
    the first section; a fully bold one is the headline."""
    in_header = False
    for kind, text in _blocks(markdown):
        if not resume:
            yield ("bullet" if kind == "li" else "body"), text
            continue
        if kind == "h1":
            in_header = True
            yield "name", text
        elif kind == "h2":
            in_header = False
            yield "heading", text
        elif kind == "h3":
            in_header = False
            yield "entry", text
        elif kind == "li":
            yield "bullet", text
        elif in_header:
            bold = re.fullmatch(r"\*\*(.+)\*\*", text)
            yield ("headline", bold.group(1)) if bold else ("contact", text)
        else:
            yield "body", text


def _split_entry(text: str) -> tuple[str, str]:
    """'Title | Company | Dates' -> ('Title', '| Company | Dates')."""
    match = re.match(r"^(.*?)\s+([|–—]\s.*)$", text)
    return (match.group(1), match.group(2)) if match else (text, "")


def _inline_html(text: str) -> str:
    out = []
    for part in _INLINE.split(text):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{html.escape(part[2:-2])}</strong>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{html.escape(part[1:-1])}</em>")
        elif part.startswith("[") and "](" in part:
            label, url = part[1:-1].split("](", 1)
            safe = url if re.match(r"^(https?://|mailto:)", url) else "#"
            out.append(f'<a href="{html.escape(safe)}">{html.escape(label)}</a>')
        else:
            out.append(html.escape(part))
    return "".join(out)


def _color(value: str, fallback: str = "#111111") -> str:
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "")) else fallback


def _css(style: dict) -> str:
    font = str(style.get("font") or "Helvetica Neue").replace("'", "").replace(";", "")[:60]
    fallback = 'Georgia, "Times New Roman", serif' if style.get("serif") else "Arial, Helvetica, sans-serif"
    stack = f"'{font}', {fallback}"
    page = "letter" if style.get("page") == "letter" else "A4"
    margin = float(style.get("margin_pt") or 45)
    align = "center" if style.get("align_header") == "center" else "left"

    def text_style(key, extra=""):
        s = style.get(key) or {}
        return (f"font-size:{float(s.get('size') or 10.5)}pt;color:{_color(s.get('color'))};"
                f"font-weight:{700 if s.get('bold') else 400};{extra}")
    heading = style.get("heading") or {}
    rule = f"border-bottom:.75pt solid {_color(heading.get('color'))};padding-bottom:2pt;" if heading.get("rule") else ""
    caps = "text-transform:uppercase;letter-spacing:.04em;" if heading.get("caps") else ""
    width = 612 if page == "letter" else 595
    return f"""
@page{{size:{page};margin:{min(margin, 40)}pt {margin}pt {min(margin, 40)}pt;}}
html{{background:#e8e9ee;}}
body{{font-family:{stack};{text_style('body')}line-height:1.34;margin:24px auto;padding:{min(margin, 40)}pt {margin}pt;
  width:{width}pt;max-width:calc(100% - 24px);box-sizing:border-box;background:#fff;box-shadow:0 2px 18px rgba(0,0,0,.18);}}
.name{{{text_style('name')}margin:0 0 3pt;text-align:{align};line-height:1.15;}}
.headline{{{text_style('headline')}margin:0 0 2pt;text-align:{align};}}
.contact{{{text_style('contact')}margin:0 0 2pt;text-align:{align};}}
h2{{{text_style('heading', caps + rule)}margin:11pt 0 5pt;}}
.entry{{margin:7pt 0 2pt;}}
.entry strong{{{text_style('entry')}}}
.entry span{{{text_style('entry_meta')}}}
p{{margin:0 0 4pt;}}
ul{{list-style:none;margin:0 0 4pt;padding:0;}}
li{{position:relative;padding-left:1.15em;margin:0 0 2pt;}}
li::before{{content:attr(data-mark);position:absolute;left:.2em;}}
a{{color:inherit;text-decoration:none;}}
@media print{{html{{background:none;}}body{{margin:0;padding:0;width:auto;max-width:none;box-shadow:none;}}}}
"""


def to_html(markdown: str, *, title: str, auto_print: bool = False, style: dict | None = None, resume: bool = True) -> str:
    style = style or _default_style()
    mark = html.escape(str(style.get("bullet") or "•")[:2])
    body, in_list = [], False
    for role, text in _roles(markdown, resume):
        if role == "bullet":
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f'<li data-mark="{mark}">{_inline_html(text)}</li>')
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if role == "name":
            body.append(f'<h1 class="name">{_inline_html(text)}</h1>')
        elif role == "heading":
            body.append(f"<h2>{_inline_html(text)}</h2>")
        elif role == "entry":
            head, rest = _split_entry(text)
            body.append(f'<h3 class="entry"><strong>{_inline_html(head)}</strong>{f" <span>{_inline_html(rest)}</span>" if rest else ""}</h3>')
        elif role in ("headline", "contact"):
            body.append(f'<p class="{role}">{_inline_html(text)}</p>')
        else:
            body.append(f"<p>{_inline_html(text)}</p>")
    if in_list:
        body.append("</ul>")
    script = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),150));</script>" if auto_print else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{_css(style)}</style></head><body>{''.join(body)}{script}</body></html>")


def text_markdown(text: str) -> str:
    """Plain resume text (as extracted from the upload) in the Markdown subset:
    the first line is the name, short all-capitals lines are sections, lines
    led by a bullet mark are bullets, "Title | Company" lines are entries, and
    lines before the first section are the header (the first of several is the
    headline). Lines the PDF wrapped are joined back up."""
    label = re.compile(r"^([A-Z][\w &/()+.-]{1,30}):\s+(.*)$")
    bullet = re.compile(r"^[-•▪●–*]\s+")

    def caps(line):
        letters = [c for c in line if c.isalpha()]
        return len(line) <= 48 and len(letters) >= 3 and all(c.isupper() for c in letters)
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    out = [f"# {lines[0]}"]
    i = 1
    header = []
    while i < len(lines) and not caps(lines[i]):
        header.append(lines[i])
        i += 1
    if len(header) > 1:
        out.append(f"\n**{header.pop(0)}**")
    out.extend(f"\n{line}" for line in header)
    kinds = ["header"] * len(out)
    for line in lines[i:]:
        prev = kinds[-1]
        if caps(line):
            out.append(f"\n## {line}")
            kinds.append("heading")
        elif bullet.match(line):
            out.append("- " + bullet.sub("", line))
            kinds.append("bullet")
        elif " | " in line and len(line) <= 140 and not line[0].islower():
            out.append(f"\n### {line}")
            kinds.append("entry")
        elif (match := label.match(line)):
            out.append(f"\n**{match.group(1)}:** {match.group(2)}")
            kinds.append("text")
        elif prev == "bullet" or (prev == "text" and not re.search(r"[.!?]$", out[-1])):
            out[-1] += " " + line  # a line the PDF wrapped
        else:
            out.append(f"\n{line}")
            kinds.append("text")
    return "\n".join(out)


def text_page(text: str, *, title: str, style: dict | None = None) -> str:
    """The master resume's text as a page in its design (for files a browser can't show)."""
    return to_html(text_markdown(text), title=title, style=style)


def _hex(value: str) -> str:
    return _color(value)[1:].upper()


def _rpr(style: dict, key: str, *, bold: bool | None = None, italic: bool = False, caps: bool = False) -> str:
    s = style.get(key) or {}
    weight = s.get("bold") if bold is None else bold
    font = xml_escape(str(style.get("font") or "Arial"))
    return (f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>{"<w:b/>" if weight else ""}{"<w:i/>" if italic else ""}'
            f'{"<w:caps/>" if caps else ""}<w:color w:val="{_hex(s.get("color"))}"/><w:sz w:val="{round(float(s.get("size") or 10.5) * 2)}"/></w:rPr>')


def _docx_runs(text: str, style: dict, key: str, *, caps: bool = False) -> str:
    runs = []
    for part in _INLINE.split(text):
        bold, italic, value = None, False, part
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            bold, value = True, part[2:-2]
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            italic, value = True, part[1:-1]
        elif part.startswith("[") and "](" in part:
            value = part[1:-1].split("](", 1)[0]
        if value:
            runs.append(f'<w:r>{_rpr(style, key, bold=bold, italic=italic, caps=caps)}<w:t xml:space="preserve">{xml_escape(value)}</w:t></w:r>')
    return "".join(runs)


def to_docx(markdown: str, *, style: dict | None = None, resume: bool = True) -> bytes:
    style = style or _default_style()
    heading = style.get("heading") or {}
    center = "<w:jc w:val=\"center\"/>" if style.get("align_header") == "center" else ""
    mark = str(style.get("bullet") or "•")[:2]
    paragraphs = []
    for role, text in _roles(markdown, resume):
        if role == "name":
            ppr, runs = f'<w:pPr><w:pStyle w:val="Title"/>{center}<w:spacing w:after="40"/></w:pPr>', _docx_runs(text, style, "name")
        elif role in ("headline", "contact"):
            ppr, runs = f'<w:pPr>{center}<w:spacing w:after="20"/></w:pPr>', _docx_runs(text, style, role)
        elif role == "heading":
            rule = f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{_hex(heading.get("color"))}"/></w:pBdr>' if heading.get("rule") else ""
            ppr = f'<w:pPr><w:pStyle w:val="Heading1"/>{rule}<w:spacing w:before="220" w:after="80"/></w:pPr>'
            runs = _docx_runs(text, style, "heading", caps=bool(heading.get("caps")))
        elif role == "entry":
            head, rest = _split_entry(text)
            ppr = '<w:pPr><w:pStyle w:val="Heading2"/><w:spacing w:before="140" w:after="30"/></w:pPr>'
            runs = _docx_runs(head, style, "entry") + (_docx_runs(" " + rest, style, "entry_meta") if rest else "")
        elif role == "bullet":
            ppr = '<w:pPr><w:pStyle w:val="ListBullet"/><w:spacing w:after="30"/></w:pPr>'
            runs = _docx_runs(f"{mark} {text}", style, "body")  # visible mark without a numbering part
        else:
            ppr, runs = '<w:pPr><w:spacing w:after="60"/></w:pPr>', _docx_runs(text, style, "body")
        paragraphs.append(f"<w:p>{ppr}{runs}</w:p>")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    width, height = (12240, 15840) if style.get("page") == "letter" else (11906, 16838)
    margin = round(float(style.get("margin_pt") or 50) * 20)
    top = min(margin, 800)
    font = xml_escape(str(style.get("font") or "Arial"))
    body = style.get("body") or {}
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>{"".join(paragraphs)}'
                f'<w:sectPr><w:pgSz w:w="{width}" w:h="{height}"/><w:pgMar w:top="{top}" w:right="{margin}" w:bottom="{top}" w:left="{margin}"/></w:sectPr>'
                "</w:body></w:document>")
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {ns}>'
              f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:color w:val="{_hex(body.get("color"))}"/>'
              f'<w:sz w:val="{round(float(body.get("size") or 10.5) * 2)}"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/></w:pPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:keepNext/></w:pPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:pPr><w:ind w:left="300" w:hanging="200"/></w:pPr></w:style>'
              "</w:styles>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
    return buffer.getvalue()


def safe_filename(text: str) -> str:
    return (re.sub(r"[^A-Za-z0-9]+", "-", text or "document").strip("-")[:60] or "document")
