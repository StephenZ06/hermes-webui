"""NeuralWatt lightweight profile fallback for custom:api-nw."""
import pytest


def test_resolve_custom_provider_connection_falls_back_to_neuralwatt_env(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: {
            "model": {
                "provider": "custom:api-nw",
                "base_url": "https://api.neuralwatt.com/v1",
                "default": "deepseek-v4-flash",
                "api_key": "",
            },
        },
    )
    monkeypatch.setenv("NEURALWATT_API_KEY", "nw-fallback-key")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)

    api_key, base_url = config.resolve_custom_provider_connection("custom:api-nw")

    assert api_key == "nw-fallback-key"
    assert base_url == "https://api.neuralwatt.com/v1"


def test_resolve_custom_provider_connection_falls_back_to_hermes_api_key(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: {
            "model": {
                "provider": "custom:api-nw",
                "base_url": "https://api.neuralwatt.com/v1",
                "default": "kimi-k3",
                "api_key": "",
            },
        },
    )
    monkeypatch.delenv("NEURALWATT_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_API_KEY", "hermes-fallback-key")

    api_key, base_url = config.resolve_custom_provider_connection("custom:api-nw")

    assert api_key == "hermes-fallback-key"
    assert base_url == "https://api.neuralwatt.com/v1"


def test_resolve_custom_provider_connection_prefers_neuralwatt_over_hermes_key(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: {
            "model": {
                "provider": "custom:api-nw",
                "base_url": "https://api.neuralwatt.com/v1",
                "default": "kimi-k3",
                "api_key": "",
            },
        },
    )
    monkeypatch.setenv("NEURALWATT_API_KEY", "nw-fallback-key")
    monkeypatch.setenv("HERMES_API_KEY", "hermes-fallback-key")

    api_key, _ = config.resolve_custom_provider_connection("custom:api-nw")

    assert api_key == "nw-fallback-key"


def test_resolve_custom_provider_connection_no_neuralwatt_fallback_for_other_hosts(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: {
            "model": {
                "provider": "custom:other",
                "base_url": "https://api.example.com/v1",
                "default": "model-x",
                "api_key": "",
            },
        },
    )
    monkeypatch.setenv("NEURALWATT_API_KEY", "nw-fallback-key")
    monkeypatch.setenv("HERMES_API_KEY", "hermes-fallback-key")

    api_key, base_url = config.resolve_custom_provider_connection("custom:other")

    # NeuralWatt-specific env var must not leak into other providers, but the
    # generic HERMES_API_KEY fallback is available to any provider.
    assert api_key == "hermes-fallback-key"
    assert base_url == "https://api.example.com/v1"
