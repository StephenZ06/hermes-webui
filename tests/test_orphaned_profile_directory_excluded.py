"""api/gateway_ticker.py's background heartbeat must never treat a bare
directory (no config.yaml) under profiles/ as a real profile.

Without this check, a profile whose gateway had ever run left an orphaned
directory behind after `hermes profile delete` (auth.lock/cache/cron/
gateway_state.json/webui_state, but no config.yaml -- the delete removes
the real profile content, not the gateway's own scratch files written by a
process that was live at deletion time). The ticker's 60s loop iterates
every directory under profiles/ unconditionally and calls
write_runtime_status() against each one, which re-creates a fresh
gateway_state.json inside it -- keeping the orphan looking perpetually
"alive" forever, and reappearing in the profile dropdown after every
restart even though `hermes profile delete` reported success.

(api/profiles.py's own profile listing intentionally stays permissive --
see tests/test_profile_description_exposed.py's "no-meta" case -- a bare
directory there is treated as a legitimately minimal/provisioning profile,
not necessarily an orphan. The ticker is the actual mechanism that keeps
an orphan alive indefinitely, so that's where this fix belongs.)
"""
from __future__ import annotations

from pathlib import Path


class TestGatewayTickerExcludesOrphans:
    def test_iter_profile_homes_skips_directory_without_config_yaml(self, tmp_path, monkeypatch):
        from api import gateway_ticker

        default_home = tmp_path / "default"
        default_home.mkdir()
        root = tmp_path / "profiles"
        root.mkdir()

        real = root / "backend"
        real.mkdir()
        (real / "config.yaml").write_text("model:\n  provider: openai\n", encoding="utf-8")

        orphan = root / "local"
        orphan.mkdir()
        (orphan / "gateway_state.json").write_text("{}", encoding="utf-8")

        monkeypatch.setattr("api.profiles._DEFAULT_HERMES_HOME", default_home)
        monkeypatch.setattr("api.profiles._profiles_root", lambda: root)

        homes = gateway_ticker._iter_profile_homes()
        assert default_home in homes
        assert real in homes
        assert orphan not in homes

    def test_iter_profile_homes_includes_every_real_profile(self, tmp_path, monkeypatch):
        from api import gateway_ticker

        default_home = tmp_path / "default"
        default_home.mkdir()
        root = tmp_path / "profiles"
        root.mkdir()
        for name in ("a", "b", "c"):
            d = root / name
            d.mkdir()
            (d / "config.yaml").write_text("model:\n  provider: openai\n", encoding="utf-8")

        monkeypatch.setattr("api.profiles._DEFAULT_HERMES_HOME", default_home)
        monkeypatch.setattr("api.profiles._profiles_root", lambda: root)

        homes = gateway_ticker._iter_profile_homes()
        assert set(homes) == {default_home, root / "a", root / "b", root / "c"}
