"""Ephemeral source-file intake for Goal Planner.

Files live only in this process and are removed on consume, discard, or expiry.
They are deliberately not written to a chat, workspace, or Work Hub database.
"""
from __future__ import annotations

import io
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_SOURCE_CHARS = 200_000
SOURCE_TTL_SECONDS = 15 * 60
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf"}
_UPLOADS: dict[str, dict[str, Any]] = {}


class SourceError(ValueError):
    pass


def _purge_expired() -> None:
    now = time.time()
    for token, source in list(_UPLOADS.items()):
        if source["expires_at"] <= now:
            del _UPLOADS[token]


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_SOURCE_CHARS * 4:
                raise SourceError("DOCX source text is too large")
            xml = archive.read(info)
        root = ElementTree.fromstring(xml)
    except (KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise SourceError("DOCX file cannot be read") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise SourceError("Encrypted PDF files are not supported")
        if len(reader.pages) > 200:
            raise SourceError("PDF has too many pages")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError("PDF file cannot be read") from exc


def _extract_text(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        text = raw.decode("utf-8", errors="replace")
    elif suffix == ".docx":
        text = _extract_docx(raw)
    elif suffix == ".pdf":
        text = _extract_pdf(raw)
    else:
        raise SourceError("Unsupported source type. Use TXT, Markdown, DOCX, or PDF.")
    text = text.strip()
    if not text:
        raise SourceError("Source file contains no readable text")
    if len(text) > MAX_SOURCE_CHARS:
        raise SourceError("Source text is too large")
    return text


def store_upload(owner_id: str, filename: str, raw: bytes) -> dict[str, Any]:
    """Extract and retain one temporary source, returning its opaque token."""
    _purge_expired()
    if not isinstance(owner_id, str) or not owner_id:
        raise SourceError("Source owner is required")
    if not isinstance(raw, bytes) or not raw:
        raise SourceError("Source file is empty")
    if len(raw) > MAX_SOURCE_BYTES:
        raise SourceError("Source file is too large")
    safe_name = Path(str(filename)).name
    if Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise SourceError("Unsupported source type. Use TXT, Markdown, DOCX, or PDF.")
    text = _extract_text(safe_name, raw)
    token = uuid.uuid4().hex
    expires_at = time.time() + SOURCE_TTL_SECONDS
    _UPLOADS[token] = {"owner_id": owner_id, "name": safe_name, "text": text, "expires_at": expires_at}
    return {"token": token, "name": safe_name, "expires_at": expires_at}


def consume_uploads(owner_id: str, tokens: list[str]) -> list[dict[str, str]]:
    """Return sources once and remove every supplied token regardless of result."""
    if not isinstance(tokens, list) or len(tokens) > 8 or any(not isinstance(token, str) for token in tokens):
        raise SourceError("Invalid source uploads")
    selected = []
    owned_tokens = []
    try:
        for token in tokens:
            source = _UPLOADS.get(token)
            if source is None or source["owner_id"] != owner_id:
                raise SourceError("Source upload not found")
            owned_tokens.append(token)
            if source["expires_at"] <= time.time():
                raise SourceError("Source upload expired")
            selected.append({"name": source["name"], "text": source["text"]})
        return selected
    finally:
        for token in owned_tokens:
            _UPLOADS.pop(token, None)


def discard_uploads(owner_id: str, tokens: list[str]) -> None:
    _purge_expired()
    for token in tokens if isinstance(tokens, list) else []:
        source = _UPLOADS.get(token)
        if source and source["owner_id"] == owner_id:
            _UPLOADS.pop(token, None)
