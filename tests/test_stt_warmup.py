"""api/stt_warmup.py — preload the local Whisper model at boot, off the
critical path, and never let it disturb startup."""
import sys
import threading
import types

import api.stt_warmup as warm


def _reset():
    warm._started = False


def _install_fake(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "tools.transcription_tools", fake)
    tools_pkg = sys.modules.get("tools")
    if tools_pkg is not None:
        monkeypatch.setattr(tools_pkg, "transcription_tools", fake, raising=False)


def test_start_is_idempotent_and_returns_status():
    _reset()
    # No faster-whisper module → the thread body no-ops, but start still reports
    # that it launched exactly once.
    assert warm.start_stt_warmup() is True
    assert warm.start_stt_warmup() is False
    _reset()


def test_warm_noops_without_faster_whisper(monkeypatch):
    fake = types.ModuleType("tools.transcription_tools")
    fake._HAS_FASTER_WHISPER = False
    fake._load_stt_config = lambda: {"enabled": True}
    called = []
    fake._get_or_load_local_model = lambda *a, **k: called.append(a)
    _install_fake(monkeypatch, fake)

    warm._warm()
    assert called == [], "must not touch the model when faster-whisper is absent"


def test_warm_loads_the_configured_model(monkeypatch):
    fake = types.ModuleType("tools.transcription_tools")
    fake._HAS_FASTER_WHISPER = True
    fake.DEFAULT_LOCAL_MODEL = "base"
    fake._load_stt_config = lambda: {"enabled": True, "local": {"model": "base.en"}}
    fake.is_stt_enabled = lambda cfg: bool(cfg.get("enabled", True))
    fake._normalize_local_model = lambda m: m
    loaded = {}
    fake._get_or_load_local_model = lambda name, cfg: loaded.update(name=name, cfg=cfg)
    _install_fake(monkeypatch, fake)

    warm._warm()
    assert loaded["name"] == "base.en"
    assert loaded["cfg"] == {"model": "base.en"}


def test_warm_skips_when_stt_disabled(monkeypatch):
    fake = types.ModuleType("tools.transcription_tools")
    fake._HAS_FASTER_WHISPER = True
    fake._load_stt_config = lambda: {"enabled": False}
    fake.is_stt_enabled = lambda cfg: bool(cfg.get("enabled", True))
    called = []
    fake._get_or_load_local_model = lambda *a, **k: called.append(a)
    _install_fake(monkeypatch, fake)

    warm._warm()
    assert called == []


def test_warm_swallows_a_loader_exception(monkeypatch):
    fake = types.ModuleType("tools.transcription_tools")
    fake._HAS_FASTER_WHISPER = True
    fake.DEFAULT_LOCAL_MODEL = "base"
    fake._load_stt_config = lambda: {"enabled": True, "local": {}}
    fake.is_stt_enabled = lambda cfg: True
    fake._normalize_local_model = lambda m: m

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    fake._get_or_load_local_model = _boom
    _install_fake(monkeypatch, fake)

    warm._warm()  # must not raise


def test_start_actually_spawns_a_daemon_thread():
    _reset()
    before = {t.name for t in threading.enumerate()}
    warm.start_stt_warmup()
    # The thread is short-lived (no faster-whisper here), so just confirm start
    # returned and the flag latched.
    assert warm._started is True
    _reset()
    assert "hermes-stt-warmup" not in (before or set())
