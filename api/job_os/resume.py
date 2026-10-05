"""The master resume: the single source of truth every tailored resume comes from.

Uploaded once in Resume Studio (PDF, DOCX, Markdown or plain text, or pasted
text) and stored as extracted plain text plus the original file, in the
global Job OS state directory. Tailoring may only rephrase, reorder and
select from what is in this text -- never add facts.
"""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from api.job_os.paths import job_os_state_dir

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_TEXT = 40000
_KINDS = {".pdf": "pdf", ".docx": "docx", ".md": "text", ".markdown": "text", ".txt": "text"}


class ResumeError(ValueError):
    """A user-facing reason the resume could not be read or saved."""


def _dir() -> Path:
    path = job_os_state_dir() / "resume"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _docx_text(data: bytes) -> str:
    """Paragraph text from a .docx with the standard library (no python-docx)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as error:
        raise ResumeError("That .docx file could not be opened.") from error
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ElementTree.fromstring(xml)
    lines = []
    for paragraph in root.iter(f"{ns}p"):
        bullet = paragraph.find(f"{ns}pPr/{ns}numPr") is not None
        text = "".join(node.text or "" for node in paragraph.iter() if node.tag in (f"{ns}t",))
        text += "".join("\t" for _ in paragraph.iter(f"{ns}tab"))
        text = text.strip()
        if text:
            lines.append(("• " if bullet else "") + text)
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ResumeError("PDF reading is not available here; upload a .docx, .md or .txt instead.") from error
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as error:
        raise ResumeError("That PDF could not be read. Try exporting it again, or upload a .docx.") from error


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    kind = _KINDS.get(suffix)
    if kind is None:
        raise ResumeError("Upload a PDF, DOCX, Markdown or text file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeError("That file is larger than 5 MB.")
    if kind == "pdf":
        text = _pdf_text(data)
    elif kind == "docx":
        text = _docx_text(data)
    else:
        text = data.decode("utf-8", "replace")
    text = re.sub(r"[ \t]+\n", "\n", text.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) < 200:
        raise ResumeError("Very little text was found in that file. If it is a scanned PDF, upload a .docx or paste the text.")
    return text[:MAX_TEXT]


def load_resume() -> dict | None:
    try:
        meta = json.loads((_dir() / "master.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and meta.get("text") else None


def _write_private(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save_resume(*, filename: str, text: str, original: bytes | None = None) -> dict:
    text = str(text or "").strip()[:MAX_TEXT]
    if len(text) < 200:
        raise ResumeError("A resume needs at least a few paragraphs of text.")
    previous = load_resume() or {}
    meta = {
        "filename": Path(str(filename or "resume.txt")).name[:120] or "resume.txt",
        "text": text,
        "words": len(text.split()),
        "uploaded_at": int(time.time()),
        "revision": int(previous.get("revision", 0)) + 1,
    }
    folder = _dir()
    if original is not None:
        _write_private(folder / ("original" + Path(meta["filename"]).suffix.lower()), original)
    _write_private(folder / "master.json", json.dumps(meta).encode("utf-8"))
    return meta


def summary(meta: dict | None) -> dict | None:
    """The resume without its full text (for status payloads)."""
    if not meta:
        return None
    return {k: meta[k] for k in ("filename", "words", "uploaded_at", "revision") if k in meta}
