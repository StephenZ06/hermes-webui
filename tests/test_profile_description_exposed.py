"""Profile descriptions from ``profile.yaml`` must reach the profiles API.

Every profile already carries a written purpose in
``<profile>/profile.yaml`` (``description:``, usually written by
``description_auto``). Until now ``list_profiles_api()`` opened that file only
to read the ``visible`` flag and discarded the rest, so nothing downstream --
notably cross-profile delegation, which has to pick the profile that best fits
a subtask -- could see what a profile is actually for.

The row fields that come from ``profile.yaml`` are now produced by a single
parse (``_profile_meta_fields``) shared by every ``list_profiles_api()`` return
path, so a new meta-derived field cannot land in one path and be missing from
the other three.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def _profile_row(name: str, path: Path, *, is_default: bool = False):
    return SimpleNamespace(
        name=name,
        path=path,
        is_default=is_default,
        gateway_running=False,
        model=None,
        provider=None,
        has_env=False,
    )


@pytest.fixture(autouse=True)
def _clear_profile_rows_cache():
    import api.profiles as profiles

    profiles._LIST_PROFILES_CACHE = None
    yield
    profiles._LIST_PROFILES_CACHE = None


def _install_fake_hermes_profiles(monkeypatch, rows):
    hermes_cli = types.ModuleType("hermes_cli")
    profiles_mod = types.ModuleType("hermes_cli.profiles")
    profiles_mod.list_profiles = lambda: rows
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", profiles_mod)


def _make_profiles(tmp_path) -> dict[str, Path]:
    paths = {
        "frontend": "description: Builds and refines frontend experiences.\ndescription_auto: true\n",
        "no-meta": None,
        "empty-meta": "",
        "malformed": "description: [\n",
        "non-string": "description:\n  - a\n  - b\n",
        "padded": "description: '   Handles docs and GitHub workflows.  '\n",
        "hidden-but-described": "visible: false\ndescription: Worker profile for image generation.\n",
    }
    out = {}
    for name, body in paths.items():
        path = tmp_path / "profiles" / name
        path.mkdir(parents=True)
        if body is not None:
            (path / "profile.yaml").write_text(body, encoding="utf-8")
        out[name] = path
    return out


_EXPECTED = {
    "frontend": "Builds and refines frontend experiences.",
    "no-meta": "",
    "empty-meta": "",
    "malformed": "",
    "non-string": "",
    "padded": "Handles docs and GitHub workflows.",
    "hidden-but-described": "Worker profile for image generation.",
}


def test_slow_path_exposes_profile_description(monkeypatch, tmp_path):
    """The upstream ``list_profiles()`` fallback path carries the description."""
    import api.profiles as profiles

    made = _make_profiles(tmp_path)
    _install_fake_hermes_profiles(monkeypatch, [_profile_row(n, p) for n, p in made.items()])
    monkeypatch.setattr(profiles, "_get_profile_skills_stats", lambda _path: (0, 0))
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "frontend")
    # Force the slow path: the fast row builder is what we exercise separately.
    monkeypatch.setattr(profiles, "_build_profile_rows_fast", lambda: None)

    rows = profiles.list_profiles_api()

    assert {r["name"]: r["description"] for r in rows} == _EXPECTED


def test_fast_path_exposes_profile_description(monkeypatch, tmp_path):
    """The cached fast row builder carries the same description."""
    import api.profiles as profiles

    made = _make_profiles(tmp_path)
    profiles_root = tmp_path / "profiles"
    default_home = tmp_path / "default-home"
    default_home.mkdir()
    (default_home / "profile.yaml").write_text("description: Generalist.\n", encoding="utf-8")

    upstream = types.ModuleType("hermes_cli.profiles")
    upstream._get_default_hermes_home = lambda: default_home
    upstream._get_profiles_root = lambda: profiles_root
    upstream._read_config_model = lambda _home: (None, None)
    upstream._check_gateway_running = lambda _home: False
    upstream._PROFILE_ID_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9_-]*$")
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", upstream)
    monkeypatch.setattr(profiles, "_get_profile_skills_stats", lambda _path: (0, 0))

    rows = profiles._build_profile_rows_fast()

    assert rows is not None
    by_name = {r["name"]: r["description"] for r in rows}
    assert by_name["default"] == "Generalist."
    for name, expected in _EXPECTED.items():
        assert by_name[name] == expected, name
    assert set(made) <= set(by_name)


def test_default_profile_fallback_has_a_description_key(monkeypatch):
    """The hermes_cli-unavailable fallback dict keeps the row shape."""
    import api.profiles as profiles

    monkeypatch.setattr(profiles, "_get_profile_skills_stats", lambda _path: (0, 0))

    row = profiles._default_profile_dict()

    assert "description" in row
    assert isinstance(row["description"], str)


def test_meta_fields_are_read_in_a_single_parse(monkeypatch, tmp_path):
    """visible + description come from one profile.yaml read, not one each."""
    import api.profiles as profiles

    path = tmp_path / "p"
    path.mkdir()
    (path / "profile.yaml").write_text("visible: false\ndescription: X\n", encoding="utf-8")

    reads = []
    real_read_text = Path.read_text

    def _counting_read_text(self, *args, **kwargs):
        if self.name == "profile.yaml":
            reads.append(str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    fields = profiles._profile_meta_fields(path)

    assert fields == {"visible": False, "description": "X"}
    assert len(reads) == 1
