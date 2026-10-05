"""Export tailored documents: Markdown, printable HTML (-> PDF), and DOCX.

Only the small Markdown subset tailoring produces is supported: '#'/'##'/'###'
headings, '- '/'* ' bullets, paragraphs, **bold**, *italic* and [links](url).
DOCX is written with the standard library (one simple, ATS-friendly column:
no tables, text boxes or images). PDF is the browser's own print-to-PDF of the
HTML page, which keeps the text selectable and parseable.
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from xml.sax.saxutils import escape as xml_escape

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))")


def _blocks(markdown: str):
    """Yield ("h1"|"h2"|"h3"|"li"|"p", text) from the supported Markdown subset."""
    para: list[str] = []
    for raw in str(markdown or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        bullet = re.match(r"^\s*[-*•]\s+(.*)$", line)
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


def to_html(markdown: str, *, title: str, auto_print: bool = False) -> str:
    body, in_list = [], False
    for kind, text in _blocks(markdown):
        if kind == "li":
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_html(text)}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        tag = "p" if kind == "p" else kind
        body.append(f"<{tag}>{_inline_html(text)}</{tag}>")
    if in_list:
        body.append("</ul>")
    script = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),150));</script>" if auto_print else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
@page{{size:A4;margin:16mm 16mm 18mm;}}
body{{font:10.5pt/1.45 "Helvetica Neue",Arial,sans-serif;color:#111;max-width:180mm;margin:24px auto;padding:0 12px;}}
h1{{font-size:20pt;margin:0 0 2pt;}} h2{{font-size:11.5pt;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #999;padding-bottom:2pt;margin:14pt 0 6pt;}}
h3{{font-size:11pt;margin:9pt 0 3pt;}} p{{margin:0 0 6pt;}} ul{{margin:0 0 6pt 16pt;padding:0;}} li{{margin:0 0 2pt;}} a{{color:#111;}}
@media print{{body{{margin:0;}}}}
</style></head><body>{''.join(body)}{script}</body></html>"""


def _docx_runs(text: str) -> str:
    runs = []
    for part in _INLINE.split(text):
        props, value = "", part
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            props, value = "<w:b/>", part[2:-2]
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            props, value = "<w:i/>", part[1:-1]
        elif part.startswith("[") and "](" in part:
            value = part[1:-1].split("](", 1)[0]
        if value:
            runs.append(f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{xml_escape(value)}</w:t></w:r>')
    return "".join(runs)


def to_docx(markdown: str) -> bytes:
    paragraphs = []
    for kind, text in _blocks(markdown):
        style = {"h1": "Title", "h2": "Heading1", "h3": "Heading2", "li": "ListBullet"}.get(kind, "")
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        if kind == "li":
            text = "• " + text  # visible bullet without a numbering part
        paragraphs.append(f"<w:p>{ppr}{_docx_runs(text)}</w:p>")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>{"".join(paragraphs)}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1000" w:right="1000" w:bottom="1000" w:left="1000"/></w:sectPr>'
                "</w:body></w:document>")
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {ns}>'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="80"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:spacing w:before="240" w:after="80"/></w:pPr><w:rPr><w:b/><w:caps/><w:sz w:val="23"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:spacing w:before="160" w:after="40"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:pPr><w:ind w:left="360"/></w:pPr></w:style>'
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
