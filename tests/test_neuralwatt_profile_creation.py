"""NeuralWatt can be selected while creating a newly configured profile."""

from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlparse


def test_neuralwatt_profile_creation_accepts_curated_model_without_existing_key():
    """The new-profile picker must work before its API key has been saved."""
    from api import profiles

    profiles._validate_profile_model_selection(
        "glm-5.3", "neuralwatt", {"groups": []}
    )


def test_neuralwatt_profile_key_uses_its_runtime_environment_variable():
    from api import profiles

    assert profiles._resolve_env_var_for_provider("neuralwatt") == "NEURALWATT_API_KEY"


def test_neuralwatt_has_a_curated_profile_picker_catalog():
    from api import config

    assert config._PROVIDER_DISPLAY["neuralwatt"] == "NeuralWatt Basic"
    assert {model["id"] for model in config._PROVIDER_MODELS["neuralwatt"]} >= {
        "glm-5.3",
        "kimi-k2.7-code",
        "kimi-k3",
    }


def test_profile_catalog_scope_uses_the_profile_being_edited(monkeypatch, tmp_path):
    """Opening one profile's editor must not read the active profile's catalog."""
    from api import profiles

    profile_home = tmp_path / "profiles" / "neural"
    profile_home.mkdir(parents=True)
    (profile_home / ".env").write_text("NEURALWATT_API_KEY=profile-key\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", tmp_path)
    monkeypatch.setattr(profiles, "_is_root_profile", lambda name: name == "default")
    profiles.set_request_profile("codex")
    try:
        with profiles.profile_catalog_scope("neural"):
            assert profiles.get_active_profile_name() == "neural"
    finally:
        profiles.clear_request_profile()


def test_models_route_scopes_the_catalog_to_the_requested_profile(monkeypatch):
    """The profile picker endpoint forwards its explicit profile scope."""
    from api import routes

    seen = {}

    @contextmanager
    def fake_scope(name, **_kwargs):
        seen["profile"] = name
        yield

    monkeypatch.setattr("api.profiles.profile_catalog_scope", fake_scope)
    monkeypatch.setattr(routes, "get_available_models", lambda: {"groups": []})
    monkeypatch.setattr(
        routes, "j", lambda _handler, payload, status=200: {"status": status, "payload": payload}
    )

    response = routes.handle_get(SimpleNamespace(), urlparse("/api/models?profile=neural"))

    assert response == {"status": 200, "payload": {"groups": []}}
    assert seen["profile"] == "neural"


def test_named_custom_provider_key_uses_its_configured_key_variable(tmp_path):
    """API-NW keys entered in Profile editing stay usable by API-NW."""
    from api import profiles

    (tmp_path / "config.yaml").write_text(
        "custom_providers:\n- name: API-NW\n  key_env: HERMES_CUSTOM_API_NEURALWATT_COM_API_KEY\n",
        encoding="utf-8",
    )

    assert profiles._resolve_env_var_for_provider("custom:api-nw", tmp_path) == (
        "HERMES_CUSTOM_API_NEURALWATT_COM_API_KEY"
    )


def test_legacy_neuralwatt_custom_profile_saves_to_the_neuralwatt_key(tmp_path):
    """Endpoint-backed legacy profiles must not save future keys as generic HERMES_API_KEY."""
    from api import profiles

    (tmp_path / "config.yaml").write_text(
        "model:\n  provider: custom:api-nw\n  base_url: https://api.neuralwatt.com/v1\n",
        encoding="utf-8",
    )

    assert profiles._resolve_env_var_for_provider("custom:api-nw", tmp_path) == "NEURALWATT_API_KEY"
