"""The master resume's design: read from the uploaded PDF or DOCX, kept with the
resume, and used to export tailored versions; the tailoring prompt keeps the
master's layout and returns the method's report."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from api.job_os import export, llm, resume, resume_style, tailor
from tests.test_job_os_tailor import _shortlisted, store  # noqa: F401 - shared fixture


def _pdf(lines: list[tuple[str, str, float, tuple, float, float]], rules: list[float] = ()) -> bytes:
    """A one-page Letter PDF: (text, font F1|F2, size, rgb, x, y) per line."""
    ops = []
    for text, font, size, rgb, x, y in lines:
        ops.append(f"BT {rgb[0]} {rgb[1]} {rgb[2]} rg /{font} {size} Tf 1 0 0 1 {x} {y} Tm ({text}) Tj ET")
    for y in rules:
        ops.append(f"0.5 w {43} {y} m {569} {y} l S")
    stream = "\n".join(ops).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+LiberationSans >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+LiberationSans-Bold >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets))
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


DARK, TEAL, GREY = (0.14, 0.14, 0.14), (0.16, 0.49, 0.5), (0.31, 0.31, 0.31)
RESUME_LINES = [
    ("JANE DOE", "F2", 19, DARK, 230, 734), ("Junior SOC Analyst | Graduate", "F2", 10, TEAL, 220, 720),
    ("Doha, Qatar | jane@example.com", "F1", 8.5, GREY, 240, 708),
    ("PROFESSIONAL SUMMARY", "F2", 10.5, TEAL, 43, 685), ("Security graduate with internship experience in monitoring.", "F1", 9, DARK, 43, 669),
    ("WORK EXPERIENCE", "F2", 10.5, TEAL, 43, 640), ("Network Analyst Intern", "F2", 9.5, DARK, 43, 624),
    ("| Acme | Doha", "F1", 9, GREY, 150, 624), ("- Assessed LAN infrastructure with Wireshark.", "F1", 9, DARK, 48, 611),
    ("- Wrote reports for directors on findings and fixes.", "F1", 9, DARK, 48, 598),
    ("EDUCATION", "F2", 10.5, TEAL, 43, 570), ("MSc Cyber Security", "F2", 9.5, DARK, 43, 554), ("| UWL | London", "F1", 9, GREY, 140, 554),
]


def test_the_design_is_read_from_a_pdf():
    pytest.importorskip("pypdf")
    data = _pdf(RESUME_LINES, rules=[680, 635, 565])
    style = resume_style.extract_profile("cv.pdf", data, "JANE DOE\n- Assessed LAN")
    assert style["source"] == "file" and style["page"] == "letter" and style["align_header"] == "center"
    assert style["font"] == "Arial"  # Liberation Sans, by its metric-compatible name
    assert style["name"] == {"size": 19.0, "color": "#242424", "bold": True}
    assert style["headline"]["color"] == "#297d80" and style["contact"]["size"] == 8.5
    assert style["heading"] == {"size": 10.5, "color": "#297d80", "bold": True, "caps": True, "rule": True}
    assert style["entry"]["size"] == 9.5 and style["entry_meta"]["color"] == "#4f4f4f"
    assert style["body"] == {"size": 9.0, "color": "#242424", "bold": False} and style["bullet"] == "-"
    assert round(style["margin_pt"]) == 43


def test_the_design_is_read_from_a_docx_and_defaults_otherwise():
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def para(text, size, color="111111", bold=False, center=False):
        ppr = '<w:pPr><w:jc w:val="center"/></w:pPr>' if center else ""
        return (f'<w:p>{ppr}<w:r><w:rPr><w:rFonts w:ascii="Calibri"/>{"<w:b/>" if bold else ""}<w:color w:val="{color}"/>'
                f'<w:sz w:val="{int(size * 2)}"/></w:rPr><w:t>{text}</w:t></w:r></w:p>')
    body = "".join([para("JANE DOE", 20, bold=True, center=True), para("jane@example.com | Doha", 9, "555555", center=True),
                    para("EXPERIENCE", 12, "1F4E79", True), para("Built dashboards for operations.", 10.5),
                    para("Ran the weekly report.", 10.5), para("EDUCATION", 12, "1F4E79", True), para("MSc Security", 10.5)])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", f'<w:document {w}><w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                   '<w:pgMar w:left="1080"/></w:sectPr></w:body></w:document>')
    style = resume_style.extract_profile("cv.docx", buffer.getvalue(), "")
    assert style["font"] == "Calibri" and style["page"] == "a4" and style["align_header"] == "center"
    assert style["heading"]["color"] == "#1f4e79" and style["heading"]["size"] == 12 and style["body"]["size"] == 10.5
    assert style["contact"] == {"size": 9.0, "color": "#555555", "bold": False} and style["margin_pt"] == 54
    assert resume_style.extract_profile("cv.txt", b"", "Jane\n• Did things")["bullet"] == "•"
    assert resume_style.extract_profile("cv.pdf", b"not a pdf", "")["source"] == "default"


def test_tailored_markdown_exports_in_the_master_design():
    style = {**resume_style.DEFAULT, "page": "letter", "font": "Arial", "align_header": "center", "bullet": "-",
             "heading": {"size": 10.5, "color": "#287e80", "bold": True, "caps": True, "rule": True}}
    md = ("# Jane Doe\n\n**Junior SOC Analyst**\n\nDoha | jane@example.com\n\n## WORK EXPERIENCE\n"
          "### Network Analyst Intern | Acme | Doha\n- Monitored alerts in the SIEM.\n")
    page = export.to_html(md, title="Resume", style=style)
    assert "size:letter" in page and "'Arial'" in page and "text-align:center" in page and "#287e80" in page
    assert '<p class="headline">Junior SOC Analyst</p>' in page and '<p class="contact">Doha | jane@example.com</p>' in page
    assert "<strong>Network Analyst Intern</strong> <span>| Acme | Doha</span>" in page and 'data-mark="-"' in page
    with zipfile.ZipFile(io.BytesIO(export.to_docx(md, style=style))) as z:
        doc = z.read("word/document.xml").decode()
    assert 'w:w="12240"' in doc and '<w:jc w:val="center"/>' in doc and 'w:color="287E80"' in doc and "<w:caps/>" in doc
    assert "- Monitored alerts in the SIEM." in doc and '<w:pBdr><w:bottom' in doc
    letter = export.to_html("Dear team,\n\nI would like to apply.", title="Letter", style=style, resume=False)
    assert "<p>Dear team,</p>" in letter and "class=\"name\"" not in letter


def test_plain_resume_text_becomes_the_markdown_layout():
    text = ("JANE DOE\nJunior SOC Analyst | Graduate\nDoha | jane@example.com\nPROFESSIONAL SUMMARY\nSecurity graduate with\n"
            "internship experience.\nCORE SKILLS\nTools: Wireshark, Nmap,\nKali Linux\nWORK EXPERIENCE\n"
            "Network Analyst Intern | Acme | Doha\n- Assessed LAN infrastructure\nwith Wireshark.\n- Wrote reports.")
    md = export.text_markdown(text)
    assert md.splitlines()[0] == "# JANE DOE" and "**Junior SOC Analyst | Graduate**" in md and "\nDoha | jane@example.com" in md
    assert "Security graduate with internship experience." in md and "**Tools:** Wireshark, Nmap, Kali Linux" in md
    assert "### Network Analyst Intern | Acme | Doha" in md and "- Assessed LAN infrastructure with Wireshark." in md


def test_tailoring_sends_the_master_layout_and_keeps_the_report(store, monkeypatch):  # noqa: F811
    seen = {}
    store.update({"profile": {"core": ["SIEM monitoring", 7], "valued": ["Python"], "terms": [{"from": "alerts", "to": "events"}, "bad"]},
                  "mapping": {"direct": 3, "transferable": "2", "adjacent": None, "gaps": 500},
                  "reframings": [{"original": "Built services", "reframed": "Built Python services", "why": "Same work"}],
                  "gaps": [{"need": "Kubernetes", "advice": "Mention learning it in the letter"}],
                  "questions": ["Have you run a SIEM at home?"]})

    def transport(**kw):
        seen.setdefault("user", kw["user"])
        return json.dumps(store)
    monkeypatch.setattr(llm, "_transport", transport)
    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    report = tailor.tailor_one(job.id)["resume"]["notes"]["report"]
    assert "# Jane Doe" in seen["user"] and "## Experience" in seen["user"]
    assert report["core"] == ["SIEM monitoring", "7"] and report["terms"] == [{"from": "alerts", "to": "events"}]
    assert report["mapping"] == {"direct": 3, "transferable": 2, "adjacent": 0, "gaps": 99}
    assert report["gaps"][0]["need"] == "Kubernetes" and report["questions"] == ["Have you run a SIEM at home?"]
    assert "Layout" in tailor.SYSTEM and "same '## ' section headings" in tailor.SYSTEM


def test_the_style_is_kept_with_the_resume(store):  # noqa: F811
    pytest.importorskip("pypdf")
    meta = resume.save_resume(filename="cv.pdf", text="JANE DOE\n" + "Security graduate. " * 20, original=_pdf(RESUME_LINES, rules=[680]))
    assert meta["style"]["source"] == "file" and resume.style_profile()["heading"]["color"] == "#297d80"
    assert resume.original_file()[1] == "cv.pdf"
    pasted = resume.save_resume(filename="pasted.txt", text="Jane Doe\n" + "Analyst. " * 40)
    assert pasted["style"]["source"] == "default" and resume.original_file() is None


def test_routes_serve_the_original_a_preview_and_automate(store, monkeypatch):  # noqa: F811
    from urllib.parse import urlparse

    from api import routes
    from tests.test_job_os_tailor import _H

    pytest.importorskip("pypdf")
    data = _pdf(RESUME_LINES, rules=[680])
    resume.save_resume(filename="My CV.pdf", text="JANE DOE\nPROFESSIONAL SUMMARY\n" + "Security graduate. " * 20, original=data)
    info = _H()
    routes.handle_get(info, urlparse("/api/job-os/resume"))
    assert json.loads(info.wfile.getvalue())["original"] == "pdf"
    # A resume stored before designs were read gets one when it is next asked for.
    stored = json.loads((resume._dir() / "master.json").read_text())
    stored.pop("style")
    (resume._dir() / "master.json").write_text(json.dumps(stored))
    again = _H()
    routes.handle_get(again, urlparse("/api/job-os/resume"))
    assert json.loads(again.wfile.getvalue())["resume"]["style"]["heading"]["color"] == "#297d80"
    pdf = _H()
    routes.handle_get(pdf, urlparse("/api/job-os/resume/original"))
    assert pdf.status == 200 and pdf.sent["Content-Type"] == "application/pdf" and pdf.wfile.getvalue() == data
    assert "Content-Disposition" not in pdf.sent  # shown inline
    page = _H()
    routes.handle_get(page, urlparse("/api/job-os/resume/preview"))
    html = page.wfile.getvalue().decode()
    assert page.status == 200 and "default-src 'none'" in page.sent["Content-Security-Policy"]
    assert '<h1 class="name">JANE DOE</h1>' in html and "#297d80" in html
    monkeypatch.setattr(tailor, "ensure_worker", lambda: None)
    job = _shortlisted()
    bad = _H({"job_ids": []})
    routes.handle_post(bad, urlparse("/api/job-os/automate"))
    auto = _H({"job_ids": [job.id]})
    routes.handle_post(auto, urlparse("/api/job-os/automate"))
    assert bad.status == 400 and auto.status == 200
    assert json.loads(auto.wfile.getvalue())["automate"]["scoring"] == 1
