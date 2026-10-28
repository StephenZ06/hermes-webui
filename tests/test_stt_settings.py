"""Settings → Speech recognition: engine/model in config.yaml, local fallback toggle."""
import types

import pytest
import yaml

import api.upload as upload
from api import stt_settings
from tests.test_voice_transcribe_endpoint import (
    _FakeHandler,
    _install_fake_transcription_tools,
    _multipart_body,
)


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"model": {"default": "x"}, "stt": {
        "enabled": True, "provider": "local", "local": {"language": "en", "model": "base.en"},
        "groq": {"model": "whisper-large-v3-turbo"}}}))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(path))
    return path


def test_engine_and_model_are_written_to_the_agent_stt_keys(config_path):
    stt_settings.set_stt_settings(provider="groq", local_model="small.en")
    saved = yaml.safe_load(config_path.read_text())
    assert saved["stt"]["provider"] == "groq"
    # Only the chosen keys change; the rest of the stt section and config stay.
    assert saved["stt"]["local"] == {"language": "en", "model": "small.en"}
    assert saved["stt"]["groq"] == {"model": "whisper-large-v3-turbo"}
    assert saved["model"] == {"default": "x"}
    status = stt_settings.get_stt_settings()
    assert (status["provider"], status["local_model"]) == ("groq", "small.en")


@pytest.mark.parametrize("kwargs", [{"provider": "openai"}, {"local_model": "../evil"}, {"provider": ""}])
def test_unknown_values_are_rejected_and_nothing_is_written(config_path, kwargs):
    before = config_path.read_text()
    with pytest.raises(ValueError):
        stt_settings.set_stt_settings(**kwargs)
    assert config_path.read_text() == before


def _transcribe(monkeypatch, fallback_setting):
    calls = []
    fake = types.ModuleType("tools.transcription_tools")
    fake.transcribe_audio = lambda path: {"success": False, "error": "Groq rate limit reached (429)"}

    def local(path):
        calls.append(path)
        return {"success": True, "transcript": "from local whisper"}

    fake.transcribe_audio_local_fallback = local
    _install_fake_transcription_tools(monkeypatch, fake)
    monkeypatch.setattr("api.config.load_settings", lambda: {"stt_local_fallback": fallback_setting})
    body, content_type = _multipart_body(files={"file": ("voice.webm", b"RIFFfakeaudio", "audio/webm")})
    handler = _FakeHandler(body, content_type)
    upload.handle_transcribe(handler)
    return handler, calls


def test_a_failed_cloud_request_falls_back_to_local_whisper_when_enabled(monkeypatch):
    handler, calls = _transcribe(monkeypatch, True)
    assert handler.status == 200 and handler.payload()["transcript"] == "from local whisper"
    assert len(calls) == 1


def test_turning_the_fallback_off_surfaces_the_cloud_error(monkeypatch):
    handler, calls = _transcribe(monkeypatch, False)
    assert handler.status == 400 and "rate limit" in handler.payload()["error"]
    assert calls == []
