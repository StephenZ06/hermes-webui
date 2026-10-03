"""Tests for cross-profile model aggregation used by the profile form."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import api.routes as routes


class _JSONHandler:
    def __init__(self):
        self.status = None
        self.response_headers = []
        self._body = bytearray()

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self

    def write(self, data):
        self._body.extend(data)


def _payload(handler: _JSONHandler) -> dict:
    return json.loads(handler._body.decode("utf-8"))


def test_cross_profile_models_endpoint_aggregates_providers(monkeypatch, tmp_path):
    from api import profiles as profiles_mod

    profiles = [
        {"name": "alpha", "path": str(tmp_path / "alpha")},
        {"name": "beta", "path": str(tmp_path / "beta")},
    ]
    monkeypatch.setattr(profiles_mod, "list_profiles_api", lambda: profiles)
    monkeypatch.setattr(profiles_mod, "get_hermes_home_for_profile", lambda name: {
        "alpha": tmp_path / "alpha",
        "beta": tmp_path / "beta",
    }.get(name, tmp_path / "default"))

    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "alpha" / "config.yaml").write_text(
        "model:\n  provider: openai\n  default: gpt-5.6-terra\nproviders:\n  openai:\n    api_key: sk-xxx\n"
    )
    (tmp_path / "beta" / "config.yaml").write_text(
        "model:\n  provider: neuralwatt\n  default: kimi-k3\nproviders:\n  neuralwatt:\n    api_key: nw-xxx\n"
    )

    handler = _JSONHandler()
    result = routes.handle_get(handler, SimpleNamespace(path="/api/models/cross_profile", query=""))

    assert result is not False
    assert handler.status == 200
    body = _payload(handler)
    groups = {g["provider_id"]: [m["id"] for m in g["models"]] for g in body["groups"]}

    assert "openai" in groups
    assert "neuralwatt" in groups
    assert "gpt-5.6-terra" in groups["openai"]
    assert "kimi-k3" in groups["neuralwatt"]


def test_cross_profile_models_include_known_providers_that_have_a_key(monkeypatch, tmp_path):
    """A known provider with a key but no profile config still contributes its catalog.

    The key probe used a name that was never imported into api.config, so the
    NameError was swallowed by the surrounding ``except Exception`` and no
    key-only provider ever appeared in the profile form's model picker.
    """
    from api import config as config_mod
    from api import profiles as profiles_mod
    from api import providers as providers_mod

    monkeypatch.setattr(profiles_mod, "list_profiles_api", lambda: [])
    monkeypatch.setattr(profiles_mod, "get_hermes_home_for_profile", lambda name: tmp_path / "default")
    keyed = next(pid for pid, models in config_mod._PROVIDER_MODELS.items() if models)
    monkeypatch.setattr(providers_mod, "_provider_has_key", lambda pid: pid == keyed)

    body = config_mod.get_available_models_across_profiles()
    groups = {g["provider_id"]: [m["id"] for m in g["models"]] for g in body["groups"]}

    assert keyed in groups
    assert groups[keyed]
