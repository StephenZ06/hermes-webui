"""Browser-facing contracts represented through the real Jobs client source."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_jobs_client_exposes_mount_refresh_unmount_and_manual_import():
    """The client owns cleanup, profile refresh, deep links, and inline import errors."""
    source = (ROOT / "static" / "job-os" / "index.js").read_text(encoding="utf-8")
    api = (ROOT / "static" / "job-os" / "api.js").read_text(encoding="utf-8")

    for contract in ("mount", "refresh", "unmount", "openJob", "job-os-import-error"):
        assert contract in source
    assert "/api/job-os/jobs" in api
