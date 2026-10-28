"""Speech recognition settings for the WebUI's dictation.

The engine and the local Whisper model live in the active profile's
config.yaml (``stt.provider`` and ``stt.local.model``), the same keys the agent
reads, so a choice made here is the one ``transcribe_audio`` uses. Whether a
failed cloud request falls back to local Whisper is a WebUI preference
(``stt_local_fallback`` in settings.json), because that fallback lives in
``api/upload.py::handle_transcribe``.
"""
from __future__ import annotations

from api.config import (
    _cfg_lock,
    _get_config_path,
    _load_yaml_config_file,
    _save_yaml_config_file,
    load_settings,
    reload_config,
)

# Engines the Settings control offers. A config.yaml that names another
# provider keeps it until the user picks one of these.
STT_ENGINES = ("groq", "local")
# faster-whisper model names, smallest (fastest) to largest (most accurate).
LOCAL_MODELS = ("tiny.en", "base.en", "small.en", "medium.en", "tiny", "base", "small", "medium")


class _ConfigOverride:
    """The transcription module with a different stt config, for availability probes."""

    def __init__(self, stt, config):
        self._stt = stt
        self._config = config

    def __getattr__(self, name):
        return getattr(self._stt, name)

    def _load_stt_config(self):
        return self._config


def _availability(stt_config: dict) -> dict:
    """Which engines could run right now, without starting any install."""
    try:
        import tools.transcription_tools as stt
    except ImportError:
        return {"groq": False, "local": False}
    from api.upload import _stt_provider_capability_from_module

    groq_ready, _ = _stt_provider_capability_from_module(
        _ConfigOverride(stt, {**stt_config, "provider": "groq"}))
    return {"groq": bool(groq_ready), "local": bool(getattr(stt, "_HAS_FASTER_WHISPER", False))}


def get_stt_settings() -> dict:
    with _cfg_lock:
        config_data = _load_yaml_config_file(_get_config_path())
    stt_cfg = config_data.get("stt") if isinstance(config_data.get("stt"), dict) else {}
    local_cfg = stt_cfg.get("local") if isinstance(stt_cfg.get("local"), dict) else {}
    return {
        "provider": str(stt_cfg.get("provider") or ""),
        "local_model": str(local_cfg.get("model") or ""),
        "local_fallback": load_settings().get("stt_local_fallback", True) is not False,
        "engines": list(STT_ENGINES),
        "local_models": list(LOCAL_MODELS),
        "available": _availability(stt_cfg),
    }


def set_stt_settings(provider: str | None = None, local_model: str | None = None) -> dict:
    """Persist ``stt.provider`` and/or ``stt.local.model``. Raises ValueError on unknown values."""
    if provider is not None and provider not in STT_ENGINES:
        raise ValueError(f"provider must be one of: {', '.join(STT_ENGINES)}")
    if local_model is not None and local_model not in LOCAL_MODELS:
        raise ValueError(f"local_model must be one of: {', '.join(LOCAL_MODELS)}")
    if provider is None and local_model is None:
        return get_stt_settings()
    config_path = _get_config_path()
    with _cfg_lock:
        config_data = _load_yaml_config_file(config_path)
        stt_cfg = config_data.get("stt")
        if not isinstance(stt_cfg, dict):
            stt_cfg = {}
        if provider is not None:
            stt_cfg["provider"] = provider
        if local_model is not None:
            local_cfg = stt_cfg.get("local")
            if not isinstance(local_cfg, dict):
                local_cfg = {}
            local_cfg["model"] = local_model
            stt_cfg["local"] = local_cfg
        config_data["stt"] = stt_cfg
        _save_yaml_config_file(config_path, config_data)
    reload_config()
    return get_stt_settings()
