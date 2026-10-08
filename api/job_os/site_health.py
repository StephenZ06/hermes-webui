"""Whether the job sites Scout reads itself still read correctly.

Scout reads remote.id's pages directly (remoteid.py), so a redesign of that
site would quietly break it. Each site's state is kept here:

- ``ok``: its pages parse.
- ``changed``: its pages load but Scout no longer understands them; the reader
  needs updating. Shown at once (Jobs Dashboard and Scout banner, the search
  cards, Settings) and emailed once when Jobs email is on.
- ``unreachable``: its pages did not load ``UNREACHABLE_AFTER`` checks in a
  row (one failed load is only noted: sites have bad minutes).

A Scout run reports what it saw (``record``); besides that, ``tick`` checks
every ``CHECK_EVERY`` seconds while a saved search uses the site, so a change
is found even between runs. ``check`` runs one now (Settings → Check now).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable

from api.job_os.paths import job_os_state_dir

logger = logging.getLogger(__name__)
CHECK_EVERY = 12 * 3600
UNREACHABLE_AFTER = 3
_lock = threading.Lock()


def _sites() -> dict[str, tuple[str, Callable]]:
    from api.job_os import remoteid

    return {remoteid.SITE: (remoteid.NAME, remoteid.health)}


def _path():
    return job_os_state_dir() / "site_health.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def record(site: str, state: str, detail: str = "", *, now: float | None = None, send: Callable | None = None) -> dict:
    """Note what a check or a run saw for a site; returns the site's entry."""
    now = int(time.time() if now is None else now)
    with _lock:
        data = _load()
        sites = data.setdefault("sites", {})
        entry = dict(sites.get(site) or {"state": "ok", "since": now})
        before = entry.get("state", "ok")
        if state == "unreachable":
            entry["failures"] = int(entry.get("failures") or 0) + 1
            entry["last_error"] = detail[:300]
            # One bad load is noted, not shown; a site already marked changed stays so.
            if entry["failures"] < UNREACHABLE_AFTER or before == "changed":
                state = before
        else:
            entry["failures"] = 0
        if state != before:
            entry.update({"state": state, "since": now, "notified": False})
        if state != "ok":
            entry["detail"] = (detail or entry.get("detail") or "")[:300]
        else:
            entry.pop("detail", None)
            if before != "ok":
                entry["recovered"] = now
        entry["checked"] = now
        sites[site] = entry
        _write(data)
        notify = state in ("changed", "unreachable") and not entry.get("notified")
    if notify and _email(site, entry, send):
        with _lock:
            data = _load()
            if data.get("sites", {}).get(site, {}).get("since") == entry["since"]:
                data["sites"][site]["notified"] = True
                _write(data)
    return entry


def _email(site: str, entry: dict, send: Callable | None) -> bool:
    """One email per problem, when Jobs email is set up. True once sent (or not wanted)."""
    from api import mailer
    from api.job_os import notify
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not notify._ready(settings):
        return True  # no email to send; the banner in Jobs still shows
    name = _sites().get(site, (site,))[0]
    if entry["state"] == "changed":
        subject = f"Scout can no longer read {name}"
        body = (f"{name} seems to have changed its pages: {entry.get('detail') or 'they no longer parse'}.\n\n"
                f"Until its reader is updated, {name} finds no jobs; your other job sites keep running. "
                f"Have the {name} reader updated (api/job_os/remoteid.py), then use Jobs -> Settings -> "
                "Connections -> Job sites -> Check now. The warning clears by itself once Scout reads the site again.")
    else:
        subject = f"Scout cannot reach {name}"
        body = (f"{name} did not load {UNREACHABLE_AFTER} times in a row ({entry.get('last_error') or 'no answer'}).\n\n"
                "It may be down for a while; Scout keeps trying on its schedule.")
    try:
        (send or mailer.send)(notify.CONTEXT, settings["notifications"]["to_address"], subject, body)
    except Exception as error:
        notify._log("site_health", "failed", subject, str(error))
        return False
    notify._log("site_health", "sent", subject, site)
    return True


def check(site: str | None = None, *, fetchers: dict | None = None, now: float | None = None) -> list[dict]:
    """Check one site (or all) now and record the result."""
    out = []
    for key, (name, probe) in _sites().items():
        if site and key != site:
            continue
        try:
            state, detail = (fetchers or {}).get(key, probe)()
        except Exception as error:  # a probe must never take the scheduler down
            state, detail = "unreachable", type(error).__name__
        out.append({"site": key, "name": name, **record(key, state, detail, now=now)})
    return out


def _sites_in_use() -> set[str]:
    from api.job_os.scout import list_searches

    return {s for search in list_searches() if search.get("enabled") for s in search["sites"]}


def tick(*, now: float | None = None) -> bool:
    """Check in the background when due and a saved search uses one of the sites."""
    now = time.time() if now is None else now
    if now - float(_load().get("checked") or 0) < CHECK_EVERY or _lock.locked():
        return False
    used = _sites_in_use() & set(_sites())
    with _lock:
        data = _load()
        data["checked"] = int(now)
        _write(data)
    if not used:
        return False
    threading.Thread(target=lambda: [check(s) for s in used], name="job-os-site-health", daemon=True).start()
    return True


def status() -> list[dict]:
    """Every site Scout reads itself, with its state (ok when never checked)."""
    sites = _load().get("sites", {})
    used = set()
    try:
        used = _sites_in_use()
    except Exception:
        pass
    return [{"site": key, "name": name, "in_use": key in used,
             **{"state": "ok", **{k: v for k, v in (sites.get(key) or {}).items() if k != "notified"}}}
            for key, (name, _probe) in _sites().items()]
