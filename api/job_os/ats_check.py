"""Resume parse check: read an exported resume the way hiring software does.

Hiring systems (ATS) read the text layer of the file you upload, not what it
looks like. After tailoring, after edits and on every DOCX export, the
tailored resume is exported and its text is extracted again: DOCX through its
XML (standard library), the print page that becomes the PDF through its
markup, and a PDF file through ``pypdf``. Four checks:

1. **Contact details**: the name, email and phone appear as literal text.
2. **No garbled glyphs**: no replacement or private-use characters.
3. **Reading order**: the section headings come out in the master's order.
4. **Keyword coverage**: the posting's must-haves found in the text. Missing
   ones are listed as gaps, never inserted.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from xml.etree import ElementTree

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_GARBLED = re.compile("[�-\x00-\x08\x0b\x0c\x0e-\x1f]")


def docx_text(data: bytes) -> str:
    """Paragraph text of a DOCX, one paragraph per line."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    lines = []
    for paragraph in root.iter(f"{_W}p"):
        lines.append("".join(node.text or "" for node in paragraph.iter() if node.tag in (f"{_W}t", f"{_W}tab")))
    return "\n".join(line for line in lines if line.strip())


def html_text(markup: str) -> str:
    """The text a browser prints from the PDF page (its body, without styles)."""
    body = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", "", markup or "")
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-6]|li|tr|header|section)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def pdf_text(data: bytes) -> str | None:
    """A PDF's text layer, or None when ``pypdf`` isn't installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def check(text: str, *, contact: dict, headings: list[str], must_haves: list[str]) -> dict:
    """Run the four checks on extracted text."""
    from api.job_os.tailor import keyword_coverage

    flat = _normal(text)
    missing_contact = []
    for label, value in (("name", contact.get("full_name")), ("email", contact.get("email"))):
        if value and _normal(value).strip() not in flat:
            missing_contact.append(label)
    phone = _digits(contact.get("phone") or "")
    if len(phone) >= 6 and phone not in _digits(text):
        missing_contact.append("phone")
    garbled = sorted(set(_GARBLED.findall(text or "")))
    positions = []
    for heading in headings:
        at = flat.find(_normal(heading).strip())
        positions.append(at)
    found = [p for p in positions if p >= 0]
    order_ok = bool(headings) and len(found) == len(headings) and found == sorted(found)
    coverage = keyword_coverage(text, must_haves or [])
    checks = [
        {"key": "contact", "ok": not missing_contact,
         "label": "Contact details are readable" if not missing_contact else f"Not found as text: {', '.join(missing_contact)}"},
        {"key": "glyphs", "ok": not garbled,
         "label": "No garbled characters" if not garbled else f"{len(garbled)} unreadable character(s)"},
        {"key": "order", "ok": order_ok,
         "label": "Sections read in order" if order_ok else "Sections are missing or out of order"},
        {"key": "keywords", "ok": coverage["score"] is None or coverage["score"] >= 60,
         "label": (f"{len(coverage['found'])} of {len(coverage['found']) + len(coverage['missing'])} key terms"
                   if coverage["score"] is not None else "No key terms to check")},
    ]
    return {"passed": sum(c["ok"] for c in checks), "total": len(checks), "checks": checks,
            "missing_terms": coverage["missing"][:12], "found_terms": len(coverage["found"])}


def check_document(doc: dict, job, *, contact: dict, master_text: str, must_haves: list[str]) -> dict:
    """Export a tailored resume as DOCX and as the PDF print page, read each
    back, and check both. The worse of the two is the one reported."""
    from api.job_os.export import text_markdown, to_docx, to_html
    from api.job_os.resume import style_profile

    style = style_profile()
    headings = [line[3:].strip() for line in text_markdown(master_text).splitlines() if line.startswith("## ")]
    if not contact.get("full_name"):
        first = next((line for line in (master_text or "").splitlines() if line.strip()), "")
        contact = {**contact, "full_name": re.sub(r"^#+\s*", "", first.strip())[:120]}
    results = {}
    results["docx"] = check(docx_text(to_docx(doc["content"], style=style, resume=True)),
                            contact=contact, headings=headings, must_haves=must_haves)
    results["pdf"] = check(html_text(to_html(doc["content"], title="Resume", style=style, resume=True)),
                           contact=contact, headings=headings, must_haves=must_haves)
    worst = min(results.values(), key=lambda r: r["passed"])
    return {**worst, "formats": {k: v["passed"] for k, v in results.items()}}


def run_for(doc_id: str) -> dict | None:
    """Check one tailored resume and store the result in its notes."""
    import json
    import time

    from api.job_os.analysis import get_analysis
    from api.job_os.db import connect_job_os
    from api.job_os.repository import get_job
    from api.job_os.resume import load_resume
    from api.job_os.settings import load_settings
    from api.job_os.tailor import get_document

    doc = get_document(doc_id)
    if doc is None or doc["kind"] != "resume" or not doc["content"]:
        return None
    master = load_resume() or {}
    result = check_document(doc, get_job(doc["job_id"]), contact=load_settings()["applicant"],
                            master_text=master.get("text", ""),
                            must_haves=(get_analysis(doc["job_id"]) or {}).get("must_haves") or [])
    result["checked_at"] = int(time.time())
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT notes_json FROM job_documents WHERE id=?", (doc_id,)).fetchone()
        notes = json.loads(row["notes_json"] or "{}") if row else {}
        notes["ats"] = result
        conn.execute("UPDATE job_documents SET notes_json=? WHERE id=?", (json.dumps(notes), doc_id))
        conn.commit()
    finally:
        conn.close()
    return result
