"""Warm the model catalog at server start.

The first request that needs the model list — the composer dropdown on page
load, or the model chip right after a profile switch — otherwise pays the full
``get_available_models()`` rebuild: per-provider probes, a Copilot token
exchange, endpoint ``/models`` fetches. On a cold process that measured ~2.5 s,
spent while the user waits on a spinning model chip.

``get_available_models()`` caches its result in memory (24 h TTL) and on disk
per profile (``models_cache.<profile>.json``, survives restarts), so this only
has to run once per process for the active profile — every later read, and
every read after the user has visited a profile once, is served warm.

Runs in a daemon thread; a failure here never touches startup. Only the active
profile is warmed: building another profile's catalog would mean mutating the
process-global config/home state a request could be reading.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def _warm() -> None:
    try:
        from api.config import get_available_models
    except Exception:
        return
    try:
        logger.info("Warming the model catalog…")
        get_available_models(force_refresh=True)
        logger.info("Model catalog ready.")
    except Exception as e:  # never let a warmup failure touch startup
        logger.debug("Model warmup skipped: %s", e, exc_info=True)


def start_model_warmup() -> bool:
    """Kick off the background warmup once. Returns True if a thread was started."""
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_warm, name="hermes-model-warmup", daemon=True).start()
    return True
