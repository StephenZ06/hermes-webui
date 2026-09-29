"""Contracts for profile-scoped client interaction performance helpers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_performance_helper_has_profile_scoped_generation_and_marks():
    source = read("static/performance.js")

    assert "function begin(surface, identity)" in source
    assert "function isCurrent(ticket)" in source
    assert "performance.mark" in source
    assert "surface + ':' + profile" in source
