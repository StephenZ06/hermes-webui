"""Regression tests for LM Studio base URL defaulting on profile create/edit."""

from pathlib import Path

import pytest


def _with_root_cfg(tmp_path: Path, provider_block: dict):
    """Set up a temporary Hermes home whose root config has the LM Studio block."""
    from api import config

    cfg = {
        "providers": {"lmstudio": provider_block},
        "model": {"provider": "openai", "default": "gpt-4"},
    }
    root = tmp_path / "hermes_home"
    root.mkdir()
    import yaml

    (root / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")

    old_cfg = dict(config.cfg)
    old_mtime = getattr(config, "_cfg_mtime", 0)
    config.cfg.clear()
    config.cfg.update(cfg)
    try:
        config._cfg_mtime = config.Path(str(root / "config.yaml")).stat().st_mtime
    except Exception:
        config._cfg_mtime = 0.0
    return root, old_cfg, old_mtime


def _restore_cfg(old_cfg, old_mtime):
    from api import config

    config.cfg.clear()
    config.cfg.update(old_cfg)
    config._cfg_mtime = old_mtime


def test_lmstudio_base_url_from_config_prefers_root_provider_api(monkeypatch, tmp_path):
    from api import config, profiles

    root, old_cfg, old_mtime = _with_root_cfg(
        tmp_path,
        {
            "api": "http://172.28.16.1:1235/v1",
            "api_key": "no-key-required",
            "transport": "chat_completions",
        },
    )
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", root)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: root)
    try:
        url = profiles._lmstudio_base_url_from_config()
        assert url == "http://172.28.16.1:1235/v1"
    finally:
        _restore_cfg(old_cfg, old_mtime)


def test_create_profile_lmstudio_defaults_base_url_from_root_config(monkeypatch, tmp_path):
    from api import config, profiles

    root, old_cfg, old_mtime = _with_root_cfg(
        tmp_path,
        {
            "api": "http://172.28.16.1:1235/v1",
            "api_key": "no-key-required",
            "transport": "chat_completions",
        },
    )
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", root)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: root)
    monkeypatch.setattr(profiles, "_validate_profile_model_selection", lambda *a, **k: None)
    try:
        result = profiles.create_profile_api(
            "lmtest_lmbase",
            clone_config=False,
            default_model="glm-4",
            model_provider="lmstudio",
        )
        profile_dir = Path(result.get("path", root / "profiles" / "lmtest_lmbase"))
        import yaml

        cfg = yaml.safe_load((profile_dir / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "lmstudio"
        assert cfg["model"]["base_url"] == "http://172.28.16.1:1235/v1"
        assert result.get("base_url") == "http://172.28.16.1:1235/v1"
    finally:
        _restore_cfg(old_cfg, old_mtime)


def test_update_profile_lmstudio_sets_base_url_from_config(monkeypatch, tmp_path):
    from api import config, profiles

    root, old_cfg, old_mtime = _with_root_cfg(
        tmp_path,
        {
            "api": "http://172.28.16.1:1235/v1",
            "api_key": "no-key-required",
            "transport": "chat_completions",
        },
    )
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", root)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: root)
    monkeypatch.setattr(profiles, "_validate_profile_model_selection", lambda *a, **k: None)
    try:
        profiles.create_profile_api("lmtest_edit", clone_config=False)
        result = profiles.update_profile_api(
            "lmtest_edit",
            default_model="glm-4",
            model_provider="lmstudio",
        )
        profile_dir = Path(result.get("path", root / "profiles" / "lmtest_edit"))
        import yaml

        cfg = yaml.safe_load((profile_dir / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "lmstudio"
        assert cfg["model"]["base_url"] == "http://172.28.16.1:1235/v1"
    finally:
        _restore_cfg(old_cfg, old_mtime)
