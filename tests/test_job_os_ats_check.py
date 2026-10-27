"""Resume parse check: the export read back as hiring software reads it."""

from __future__ import annotations

import io
import json

from api.job_os import ats_check, export
from tests.test_job_os_tailor import MASTER, store  # noqa: F401 - shared fixture

RESUME = ("# Jane Doe\njane@example.com · +60 12-345 6789\n## Experience\n### Engineer | Acme | KL | 2020-2024\n"
          "- Built Python services on AWS.\n## Skills\n- Python, AWS, Kafka\n")
CONTACT = {"full_name": "Jane Doe", "email": "jane@example.com", "phone": "+60 12 345 6789"}


def test_docx_and_print_page_text_round_trip():
    text = ats_check.docx_text(export.to_docx(RESUME, resume=True))
    assert "Jane Doe" in text and "jane@example.com" in text and "Built Python services on AWS." in text
    page = ats_check.html_text(export.to_html(RESUME, title="Resume", resume=True))
    assert "Experience" in page and "<" not in page


def test_all_four_checks_pass_on_a_clean_resume():
    text = ats_check.docx_text(export.to_docx(RESUME, resume=True))
    out = ats_check.check(text, contact=CONTACT, headings=["Experience", "Skills"], must_haves=["Python", "AWS", "Go"])
    assert out["passed"] == 4 and out["total"] == 4
    assert out["missing_terms"] == ["Go"]
    assert next(c for c in out["checks"] if c["key"] == "keywords")["label"] == "2 of 3 key terms"


def test_a_missing_email_and_garbled_text_fail():
    out = ats_check.check("Jane Doe\n� Experience\nSkills", contact=CONTACT, headings=["Experience", "Skills"],
                          must_haves=[])
    failed = {c["key"] for c in out["checks"] if not c["ok"]}
    assert failed == {"contact", "glyphs"}
    assert "email" in next(c for c in out["checks"] if c["key"] == "contact")["label"]


def test_sections_out_of_order_fail():
    out = ats_check.check("Jane Doe jane@example.com 60123456789\nSkills\nExperience", contact=CONTACT,
                          headings=["Experience", "Skills"], must_haves=[])
    assert not next(c for c in out["checks"] if c["key"] == "order")["ok"]


def test_pdf_text_is_skipped_without_pypdf(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_pypdf(name, *a, **kw):
        if name == "pypdf":
            raise ImportError(name)
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    assert ats_check.pdf_text(b"%PDF-1.4") is None


def test_pdf_text_reads_a_pdf():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    assert ats_check.pdf_text(buf.getvalue()) == ""


def test_tailoring_stores_the_parse_check(store):  # noqa: F811
    from api.job_os import tailor
    from tests.test_job_os_tailor import _shortlisted

    job = _shortlisted()
    tailor.request_tailoring(job.id, start_worker=False)
    ats = tailor.tailor_one(job.id)["resume"]["notes"]["ats"]
    assert ats["total"] == 4 and set(ats["formats"]) == {"docx", "pdf"}
    assert next(c for c in ats["checks"] if c["key"] == "contact")["ok"]  # name and email from the master
