"""Safe metadata contract for Office integrations."""
from pathlib import Path

from api.office_integrations import gmail_integration_metadata, safe_integration_metadata


OFFICE_JS = (Path(__file__).resolve().parents[1] / "static" / "office" / "index.js").read_text(encoding="utf-8")
OFFICE_CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")


def test_gmail_starts_disconnected_with_only_the_approved_email_capabilities():
    gmail = gmail_integration_metadata()
    assert gmail == {
        "provider": "gmail",
        "floor": "emails",
        "status": "disconnected",
        "capabilities": ["search_read", "summarize", "draft_reply"],
        "send_requires_approval": True,
    }


def test_malformed_or_token_bearing_metadata_fails_closed_without_secrets():
    safe = safe_integration_metadata({
        "provider": "gmail", "floor": "emails", "status": "connected",
        "account_label": "owner@example.com", "access_token": "secret", "refresh_token": "secret",
    })
    assert safe["status"] == "disconnected"
    assert "account_label" not in safe
    assert "access_token" not in safe
    assert "refresh_token" not in safe


def test_integrations_use_the_original_static_themed_icons():
    assert "officeIcon('inbox', 'Gmail')" in OFFICE_JS
    assert "office-integration-provider-video" not in OFFICE_JS
    assert "office-integration-provider-media" not in OFFICE_CSS
    asset_root = Path(__file__).resolve().parents[1] / "static" / "office" / "integrations"
    assert not asset_root.exists()
