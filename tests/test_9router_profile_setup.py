"""Regression coverage for safe 9router profile setup."""

from pathlib import Path

import yaml

import api.profiles as profiles


NINE_ROUTER_MODELS = (
    "cc/claude-opus-5-5",
    "cc/claude-opus-5",
    "cc/claude-fable-5-1",
    "cc/claude-fable-5",
    "cc/claude-sonnet-5-5",
    "cc/claude-sonnet-5",
    "cc/claude-haiku-4-5-20251001",
)


def test_configure_9router_provider_preserves_custom_providers_and_uses_profile_key(tmp_path):
    """9router is a named OpenAI-compatible provider, not a Claude token proxy."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "custom_providers": [
                    {
                        "name": "Existing gateway",
                        "base_url": "https://gateway.example/v1",
                        "key_env": "EXISTING_GATEWAY_KEY",
                        "models": ["existing-model"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profiles._configure_9router_custom_provider(
        tmp_path,
        base_url="http://127.0.0.1:20128/v1",
        default_model="cc/claude-sonnet-5",
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["custom_providers"][0]["name"] == "Existing gateway"
    router = next(entry for entry in config["custom_providers"] if entry["name"] == "9router")
    assert router["base_url"] == "http://127.0.0.1:20128/v1"
    assert router["api_mode"] == "openai_compatible"
    assert router["key_env"] == "NINE_ROUTER_API_KEY"
    assert router["api_key"] == "${NINE_ROUTER_API_KEY}"
    assert router["models"] == list(NINE_ROUTER_MODELS)
    assert profiles._resolve_env_var_for_provider("custom:9router", tmp_path) == "NINE_ROUTER_API_KEY"


def test_unconfigured_9router_catalog_model_is_accepted_before_key_exists():
    """A new 9router profile can be saved before its first API key is stored."""
    profiles._validate_profile_model_selection(
        "cc/claude-haiku-4-5-20251001",
        "custom:9router",
        available_models={"groups": []},
    )


def test_profile_update_sets_up_9router_with_its_own_secret_key(monkeypatch, tmp_path):
    profile_dir = tmp_path / "profiles" / "research"
    profile_dir.mkdir(parents=True)
    row = {
        "name": "research",
        "path": str(profile_dir),
        "is_default": False,
        "is_active": False,
        "gateway_running": False,
    }
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "list_profiles_api", lambda: [row])
    monkeypatch.setattr(profiles, "_SKILLS_STATS_CACHE", {})
    monkeypatch.setattr(profiles, "_invalidate_list_profiles_cache", lambda: None)

    profiles.update_profile_api(
        "research",
        default_model="cc/claude-sonnet-5",
        model_provider="custom:9router",
        api_key="test-router-key",
    )

    config = yaml.safe_load((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert config["model"]["provider"] == "custom:9router"
    assert config["model"]["base_url"] == "http://127.0.0.1:20128/v1"
    assert config["custom_providers"][-1]["key_env"] == "NINE_ROUTER_API_KEY"
    env_text = (profile_dir / ".env").read_text(encoding="utf-8")
    assert "NINE_ROUTER_API_KEY=test-router-key" in env_text
    assert "HERMES_API_KEY=" not in env_text


def test_profile_picker_seeds_9router_instead_of_neuralwatt_catalog():
    panel_source = Path("static/panels.js").read_text(encoding="utf-8")
    assert "provider_id: 'custom:9router'" in panel_source
    assert "9router (local)" in panel_source
    picker = panel_source[
        panel_source.index("async function _populateProfileFormModelSelect"):
        panel_source.index("function cancelProfileForm")
    ]
    assert "provider_id: 'neuralwatt'" not in picker
    assert profiles._NINE_ROUTER_PROFILE_MODELS == NINE_ROUTER_MODELS
    for model in NINE_ROUTER_MODELS:
        assert model in picker
