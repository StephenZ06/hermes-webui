"""Preload the local Whisper model at server start.

The first ``/api/transcribe`` call otherwise pays the full model load (and, on a
fresh container, the ~150 MB download) — 15-20 s while the user waits with the
mic showing "listening". Warming it in a background thread at boot moves that
cost off the critical path. Every later dictation reuses the cached model
(faster-whisper keeps it resident; ``stt.local.unload_after_idle_seconds``
defaults to 0 = never).

Only runs when faster-whisper is installed and STT is enabled — the local model
is also the transparent fallback for a configured-but-unreachable cloud
provider (see api/upload.py::handle_transcribe), so warming it is worthwhile
even when ``stt.provider`` is not ``local``.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _warm() -> None:
    try:
        import tools.transcription_tools as stt
    except Exception:
        return
    try:
        if not getattr(stt, "_HAS_FASTER_WHISPER", False):
            return
        load_cfg = getattr(stt, "_load_stt_config", None)
        cfg = load_cfg() if callable(load_cfg) else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        is_enabled = getattr(stt, "is_stt_enabled", None)
        if callable(is_enabled) and not is_enabled(cfg):
            return
        get_or_load = getattr(stt, "_get_or_load_local_model", None)
        if not callable(get_or_load):
            return
        local_cfg = cfg.get("local") if isinstance(cfg.get("local"), dict) else {}
        default_model = getattr(stt, "DEFAULT_LOCAL_MODEL", "base")
        model_name = str(local_cfg.get("model") or default_model)
        normalize = getattr(stt, "_normalize_local_model", None)
        if callable(normalize):
            try:
                model_name = normalize(model_name)
            except Exception:
                pass
        logger.info("Preloading local Whisper model %r for STT…", model_name)
        get_or_load(model_name, local_cfg)
        logger.info("Local Whisper model %r ready.", model_name)
    except Exception as e:  # never let a warmup failure touch startup
        logger.debug("STT warmup skipped: %s", e, exc_info=True)


def start_stt_warmup() -> bool:
    """Kick off the background warmup once. Returns True if a thread was started."""
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_warm, name="hermes-stt-warmup", daemon=True).start()
    return True
