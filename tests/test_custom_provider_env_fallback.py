"""Generic fallback tests for lightweight custom providers.

A "lightweight" custom provider is configured only through
``model.provider: custom:<slug>`` + ``model.base_url`` without a full
``custom_providers`` block.  The WebUI should still resolve a key from a
provider-specific env var or the generic ``HERMES_API_KEY`` env var so chat
can start without requiring every profile to duplicate a full provider
configuration.
"""


def _make_model_cfg(provider: str, base_url: str, api_key: str = "") -> dict:
    return {
        "model": {
            "provider": provider,
            "base_url": base_url,
            "default": "some-model",
            "api_key": api_key,
        },
    }


def test_resolve_custom_provider_connection_uses_provider_specific_env_var(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _make_model_cfg("custom:my-provider", "https://api.example.com/v1"),
    )
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    # The POSIX-safe env var derived from custom:my-provider.
    monkeypatch.setenv("CUSTOM_MY_PROVIDER_API_KEY", "my-provider-key")

    api_key, base_url = config.resolve_custom_provider_connection("custom:my-provider")

    assert api_key == "my-provider-key"
    assert base_url == "https://api.example.com/v1"


def test_resolve_custom_provider_connection_falls_back_to_hermes_api_key(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _make_model_cfg("custom:another-provider", "https://api.example.com/v1"),
    )
    for var in ("CUSTOM_ANOTHER_PROVIDER_API_KEY",):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HERMES_API_KEY", "hermes-generic-key")

    api_key, base_url = config.resolve_custom_provider_connection("custom:another-provider")

    assert api_key == "hermes-generic-key"
    assert base_url == "https://api.example.com/v1"


def test_resolve_custom_provider_connection_prefers_provider_specific_env(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _make_model_cfg("custom:preferred", "https://api.example.com/v1"),
    )
    monkeypatch.setenv("CUSTOM_PREFERRED_API_KEY", "preferred-key")
    monkeypatch.setenv("HERMES_API_KEY", "hermes-generic-key")

    api_key, _ = config.resolve_custom_provider_connection("custom:preferred")

    assert api_key == "preferred-key"


def test_resolve_custom_provider_connection_no_env_key_returns_none_for_key(monkeypatch):
    import api.config as config

    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _make_model_cfg("custom:keyless", "https://api.example.com/v1"),
    )
    for var in ("KEYLESS_API_KEY", "HERMES_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    api_key, base_url = config.resolve_custom_provider_connection("custom:keyless")

    assert api_key is None
    assert base_url == "https://api.example.com/v1"
