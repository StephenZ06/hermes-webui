"""Scoring weights: how much each dimension counts towards a job's fit score.

The defaults follow ai-job-search's evaluation rubric (skills 30, experience
25, culture 15, career 30). Calibration from outcomes can tune them; the
current set lives in ``calibration.json`` in the profile's Job OS state.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json

from api.job_os.paths import job_os_state_dir

DIMENSIONS = ("skills", "experience", "culture", "career")
DEFAULT_WEIGHTS = {"skills": 30, "experience": 25, "culture": 15, "career": 30}


def _path():
    return job_os_state_dir() / "calibration.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def weights() -> dict:
    """The weights in use: the accepted calibration's, else the defaults."""
    current = (load().get("current") or {}).get("weights")
    if isinstance(current, dict) and all(isinstance(current.get(k), int) and 0 <= current[k] <= 100 for k in DIMENSIONS) \
            and sum(current.values()) > 0:
        return {k: current[k] for k in DIMENSIONS}
    return dict(DEFAULT_WEIGHTS)


def guidance() -> str:
    """A short note from calibration added to the scoring prompt (or "")."""
    return str((load().get("current") or {}).get("guidance") or "")[:600]


def weighted_score(dimensions: dict, weights_: dict | None = None) -> int | None:
    """The fit score from the dimension scores: a weighted average, with a
    missing culture score's weight shared out over the others."""
    weights_ = weights_ or weights()
    parts = [(dimensions.get(k), weights_[k]) for k in DIMENSIONS]
    present = [(v, w) for v, w in parts if isinstance(v, int)]
    total = sum(w for _v, w in present)
    if not present or total <= 0 or any(not isinstance(dimensions.get(k), int) for k in ("skills", "experience", "career")):
        return None
    return round(sum(v * w for v, w in present) / total)
