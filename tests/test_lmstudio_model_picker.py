"""Regression tests for LM Studio model picker visibility.

LM Studio (and similar self-hosted providers) is configured through
``providers.lmstudio.api`` by the Settings UI. The model picker must:

1. Treat ``api`` as a valid base_url key.
2. Include LM Studio models when only ``providers.lmstudio.api`` is set.
3. Inherit route-bearing providers from ``~/.hermes/config.yaml`` for profiles
   that do not define them locally.
"""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest

import api.config as config
import api.profiles as profiles


_API_KEY_ENV_VARS = (
    "LM_API_KEY",
    "LMSTUDIO_API_KEY",
)


class _ModelsResponse:
    def __init__(self, model_ids: list[str]):
        self._model_ids = model_ids

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps({"data": [{"id": mid} for mid in self._model_ids]}).encode()


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    old_cfg_ref = config.cfg
    old_cfg = dict(config.cfg)
    old_mtime = config._cfg_mtime
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    for var in _API_KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    config.invalidate_models_cache()
    yield
    config.cfg = old_cfg_ref
    config.cfg.clear()
    config.cfg.update(old_cfg)
    config._cfg_mtime = old_mtime
    config.invalidate_models_cache()


def _write_config(tmp_path, monkeypatch, text: str) -> None:
    cfgfile = tmp_path / "config.yaml"
    cfgfile.write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "_get_config_path", lambda: cfgfile)
    config.reload_config()
    config.invalidate_models_cache()


def _write_root_config(default_home: Path, text: str) -> None:
    default_home.mkdir(parents=True, exist_ok=True)
    (default_home / "config.yaml").write_text(text, encoding="utf-8")


def _mock_model_discovery(monkeypatch, model_ids: list[str], resolved_ip: str) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _ModelsResponse(model_ids),
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, 0))
        ],
    )


def _groups_by_id() -> dict[str, dict]:
    return {group["provider_id"]: group for group in config.get_available_models()["groups"]}


def test_provider_base_url_reads_api_key():
    config.cfg = {
        "providers": {
            "lmstudio": {
                "api_key": "no-key-required",
                "api": "http://172.28.16.1:1235/v1",
            }
        },
        "model": {},
    }
    assert config._get_provider_base_url("lmstudio") == "http://172.28.16.1:1235/v1"


def test_provider_base_url_prefers_base_url_over_api():
    config.cfg = {
        "providers": {
            "lmstudio": {
                "base_url": "http://base-url.example/v1",
                "api": "http://api.example/v1",
            }
        },
        "model": {},
    }
    assert config._get_provider_base_url("lmstudio") == "http://base-url.example/v1"


def test_lmstudio_api_key_only_shows_models(tmp_path, monkeypatch):
    _write_config(
        tmp_path,
        monkeypatch,
        """
providers:
  lmstudio:
    api_key: no-key-required
    api: http://172.28.16.1:1235/v1
""",
    )
    _mock_model_discovery(
        monkeypatch,
        ["glm-4.7-flash-heretic-cyber", "second-model"],
        "172.28.16.1",
    )

    groups = _groups_by_id()
    assert "lmstudio" in groups
    model_ids = {model["id"] for model in groups["lmstudio"]["models"]}
    assert {"glm-4.7-flash-heretic-cyber", "second-model"} <= model_ids


def test_lmstudio_inherited_from_root_profile(tmp_path, monkeypatch):
    # Active profile has no providers; root config has LM Studio.
    root_home = tmp_path / "root_hermes"
    monkeypatch.setattr(config, "_DEFAULT_HERMES_HOME", root_home)
    # The root config is read from the base home as api.profiles resolves it.
    monkeypatch.setattr("api.profiles._DEFAULT_HERMES_HOME", root_home)
    _write_root_config(
        root_home,
        """
providers:
  lmstudio:
    api_key: no-key-required
    api: http://172.28.16.1:1235/v1
""",
    )
    _write_config(
        tmp_path,
        monkeypatch,
        """
model:
  provider: lmstudio
  default: glm-4.7-flash-heretic-cyber
""",
    )
    _mock_model_discovery(
        monkeypatch,
        ["glm-4.7-flash-heretic-cyber"],
        "172.28.16.1",
    )

    groups = _groups_by_id()
    assert "lmstudio" in groups
    assert any(
        model["id"] == "glm-4.7-flash-heretic-cyber"
        for model in groups["lmstudio"]["models"]
    )


def test_active_profile_overrides_root_provider(tmp_path, monkeypatch):
    root_home = tmp_path / "root_hermes"
    monkeypatch.setattr(config, "_DEFAULT_HERMES_HOME", root_home)
    # The root config is read from the base home as api.profiles resolves it.
    monkeypatch.setattr("api.profiles._DEFAULT_HERMES_HOME", root_home)
    _write_root_config(
        root_home,
        """
providers:
  lmstudio:
    api_key: no-key-required
    api: http://root.example:1235/v1
""",
    )
    _write_config(
        tmp_path,
        monkeypatch,
        """
providers:
  lmstudio:
    api_key: no-key-required
    api: http://active.example:1235/v1
""",
    )

    base_url = config._get_provider_base_url("lmstudio")
    assert base_url == "http://active.example:1235/v1"
