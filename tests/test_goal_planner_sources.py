import io
import zipfile

import pytest

from api import goal_planner_sources as sources


@pytest.fixture(autouse=True)
def clear_sources():
    sources._UPLOADS.clear()


def test_text_upload_is_bound_to_owner_and_consumed_once():
    upload = sources.store_upload("profile-a", "brief.md", b"# Build the dashboard")

    with pytest.raises(sources.SourceError, match="not found"):
        sources.consume_uploads("profile-b", [upload["token"]])

    extracted = sources.consume_uploads("profile-a", [upload["token"]])
    assert extracted[0]["name"] == "brief.md"
    assert extracted[0]["text"] == "# Build the dashboard"
    with pytest.raises(sources.SourceError, match="not found"):
        sources.consume_uploads("profile-a", [upload["token"]])


def test_docx_upload_extracts_paragraph_text():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Frontend shell</w:t></w:r></w:p></w:body></w:document>')

    upload = sources.store_upload("profile-a", "phase.docx", raw.getvalue())
    assert sources.consume_uploads("profile-a", [upload["token"]])[0]["text"] == "Frontend shell"


def test_unsupported_or_expired_upload_is_rejected(monkeypatch):
    with pytest.raises(sources.SourceError, match="Unsupported"):
        sources.store_upload("profile-a", "malware.exe", b"x")
    upload = sources.store_upload("profile-a", "brief.txt", b"x")
    monkeypatch.setattr(sources.time, "time", lambda: upload["expires_at"] + 1)
    with pytest.raises(sources.SourceError, match="expired"):
        sources.consume_uploads("profile-a", [upload["token"]])
