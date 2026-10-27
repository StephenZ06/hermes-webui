"""Job OS email: new-match alerts, a daily digest, and reply-to-proceed.

Everything is sent from the connected Gmail under the "Hermes Jobs" name to
Jobs -> Settings -> Notifications -> Send to. Each job in a match alert comes
with short single-use codes ("TAILOR 7F3A9C21"); replying with one from the
Send-to address starts that step. A reply is acted on only when all of these
hold, otherwise it is ignored and logged:

* it arrived in the sender account's inbox after polling was set up,
* its From address is the Send-to address and Gmail's own
  Authentication-Results header (the topmost one) reports ``dmarc=pass``,
* the code is in the reply's own text (quoted lines are ignored), unused,
  unexpired, and was issued for that action.

Codes are stored only as SHA-256 hashes and expire after a week.
"""

from __future__ import annotations

import email
import email.policy
import hashlib
import imaplib
import json
import logging
import re
import secrets
import ssl
import threading
import time
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api import mailer
from api.job_os.db import connect_job_os
from api.job_os.paths import job_os_state_dir

logger = logging.getLogger(__name__)
CONTEXT = "jobs"
CODE_TTL = 7 * 86400
MATCH_WINDOW = 3 * 86400  # analyses older than this never trigger an alert (no backlog flood)
MAX_PER_ALERT = 10
REPLY_ACTIONS = ("tailor", "skip")  # offered in match alerts
ACCEPTED_ACTIONS = ("tailor", "skip")
_COMMAND = re.compile(r"\b(TAILOR|SKIP)\s+([0-9A-F]{8})\b", re.I)
_send_lock = threading.Lock()
_poll_lock = threading.Lock()


# ---- state ---------------------------------------------------------------

def _state_path():
    return job_os_state_dir() / "notify.json"


def load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(**updates) -> dict:
    state = {**load_state(), **updates}
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)
    return state


def _log(kind: str, status: str, subject: str = "", detail: str = "") -> None:
    conn = connect_job_os()
    try:
        conn.execute("INSERT INTO email_log (id, kind, status, subject, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), kind, status, subject[:200], detail[:500], int(time.time())))
        conn.execute("DELETE FROM email_log WHERE id NOT IN (SELECT id FROM email_log ORDER BY created_at DESC LIMIT 200)")
        conn.commit()
    finally:
        conn.close()


def recent_log(limit: int = 20) -> list[dict]:
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT kind, status, subject, detail, created_at FROM email_log ORDER BY created_at DESC, rowid DESC LIMIT ?",
                            (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _event(conn, job_id: str, event_type: str, payload: dict) -> None:
    conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), job_id, event_type, json.dumps(payload, separators=(",", ":")), int(time.time())))


def _ready(settings: dict, *flags: str) -> bool:
    n = settings["notifications"]
    address, password = mailer.credentials()
    return bool(n["email_enabled"] and n["to_address"] and address and password and all(n[f] for f in flags))


# ---- reply codes ---------------------------------------------------------

def _hash(code: str) -> str:
    return hashlib.sha256(code.upper().encode()).hexdigest()


def issue_code(conn, job_id: str, action: str, now: int) -> str:
    code = secrets.token_hex(4).upper()
    conn.execute("INSERT INTO reply_codes (code_hash, job_id, action, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                 (_hash(code), job_id, action, now, now + CODE_TTL))
    return code


def redeem_code(action: str, code: str, *, now: int | None = None) -> str | None:
    """Use a code once. Returns its job id, or None if unknown/used/expired/wrong action."""
    now = int(time.time()) if now is None else now
    conn = connect_job_os()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT job_id FROM reply_codes WHERE code_hash=? AND action=? AND used_at IS NULL AND expires_at>?",
                           (_hash(code), action, now)).fetchone()
        if row is None:
            conn.rollback()
            return None
        conn.execute("UPDATE reply_codes SET used_at=? WHERE code_hash=?", (now, _hash(code)))
        conn.execute("DELETE FROM reply_codes WHERE expires_at < ?", (now - CODE_TTL,))
        conn.commit()
        return row["job_id"]
    finally:
        conn.close()


# ---- new-match alerts ----------------------------------------------------

def pending_matches(settings: dict, *, now: int | None = None) -> list[dict]:
    now = int(time.time()) if now is None else now
    conn = connect_job_os()
    try:
        rows = conn.execute(
            "SELECT j.id, j.title, j.company, j.location, j.workplace, j.salary_text, j.canonical_url, a.fit_score, a.data_json"
            " FROM jobs j JOIN job_analyses a ON a.job_id=j.id"
            " WHERE a.status='done' AND a.fit_score>=? AND a.finished_at>=? AND j.status='analyzed'"
            " AND NOT EXISTS (SELECT 1 FROM job_events e WHERE e.job_id=j.id AND e.event_type IN ('match_notified', 'match_released'))"
            " ORDER BY a.fit_score DESC, a.finished_at DESC",
            (settings["notifications"]["min_fit_score"], now - MATCH_WINDOW)).fetchall()
        return [{**dict(r), "summary": json.loads(r["data_json"] or "{}").get("summary", "")} for r in rows
                if not _held(r)]
    finally:
        conn.close()


def _held(row) -> bool:
    """A job whose gate failed (and wasn't ignored) is never announced as a good match."""
    from api.job_os.checks import held_by
    from api.job_os.repository import get_job

    job = get_job(row["id"])
    return job is None or bool(held_by(job, {"status": "done", **json.loads(row["data_json"] or "{}")}))


def _job_block(job: dict, codes: dict[str, str] | None) -> str:
    where = " · ".join(x for x in (job.get("company"), job.get("location"), job.get("workplace"), job.get("salary_text")) if x)
    lines = [f"{job['title']} — fit {job['fit_score']}/100", where, job.get("summary") or "", job["canonical_url"]]
    if codes:
        lines.append("Reply: " + "   or   ".join(f"{action.upper()} {code}" for action, code in codes.items()))
    return "\n".join(line for line in lines if line)


def _release_due(settings: dict, waiting: int, now: int) -> tuple[bool, str | None]:
    """(release now?, today's date when it is the cut-off release)."""
    from api.job_os.scheduler import _zone

    n = settings["notifications"]
    local = datetime.fromtimestamp(now, _zone(settings["scout"]))
    today = local.date().isoformat()
    if waiting and local.hour >= n["release_cutoff_hour"] and load_state().get("last_cutoff_release") != today:
        return True, today
    return waiting >= n["release_count"], None


def send_matches(*, now: int | None = None, send: Callable = mailer.send) -> int:
    """Release the good matches waiting in the Scout inbox, all together, once
    ``release_count`` are waiting or at the day's cut-off hour: they show as new
    in Jobs, and (when email is on) go out in one email. Returns how many."""
    from api.job_os.settings import load_settings

    settings = load_settings()
    with _send_lock:
        now = int(time.time()) if now is None else now
        jobs = pending_matches(settings, now=now)
        due, cutoff_day = _release_due(settings, len(jobs), now)
        if not due:
            return 0
        conn = connect_job_os()
        try:
            for job in jobs:
                _event(conn, job["id"], "match_released", {"fit_score": job["fit_score"]})
            conn.commit()
        finally:
            conn.close()
        _save_state(last_release_at=now, **({"last_cutoff_release": cutoff_day} if cutoff_day else {}))
        if _ready(settings, "notify_new_matches"):
            _email_matches(settings, jobs, now, send)
        return len(jobs)


def _email_matches(settings: dict, jobs: list[dict], now: int, send: Callable) -> None:
    shown = jobs[:MAX_PER_ALERT]
    replies = settings["notifications"]["reply_actions"]
    conn = connect_job_os()
    try:
        blocks = [_job_block(j, {a: issue_code(conn, j["id"], a, now) for a in REPLY_ACTIONS} if replies else None) for j in shown]
        conn.commit()
    finally:
        conn.close()
    subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''}" + (f": {jobs[0]['title']}" if len(jobs) == 1 else "")
    intro = f"Luna found {len(jobs)} new good match{'es' if len(jobs) != 1 else ''} for your resume (fit {settings['notifications']['min_fit_score']}+), best first."
    how = ("\n\nTo act on one, reply to this email with its code on its own line, e.g. \"TAILOR 1A2B3C4D\". "
           "You can send several codes in one reply. Codes work once and expire in 7 days.") if replies else ""
    more = f"\n\n{len(jobs) - len(shown)} more in Hermes." if len(jobs) > len(shown) else ""
    body = intro + how + "\n\n" + "\n\n---\n\n".join(blocks) + more + "\n\nOpen Hermes -> Jobs -> Scout to see them all."
    try:
        send(CONTEXT, settings["notifications"]["to_address"], subject, body)
    except Exception as error:
        _log("matches", "failed", subject, str(error))  # the release still stands in Jobs
        return
    conn = connect_job_os()
    try:
        for job in shown:
            _event(conn, job["id"], "match_notified", {"fit_score": job["fit_score"]})
        conn.commit()
    finally:
        conn.close()
    _log("matches", "sent", subject, f"{len(jobs)} job(s)")


def inbox(*, now: int | None = None) -> dict:
    """The Scout inbox: good matches still waiting for a release, and released
    ones not yet marked seen."""
    from api.job_os.settings import load_settings

    settings = load_settings()
    now = int(time.time()) if now is None else now
    seen = int(load_state().get("matches_seen_at") or 0)
    conn = connect_job_os()
    try:
        released = [dict(r) for r in conn.execute(
            "SELECT j.id, j.title, j.company, j.location, j.country, j.source, j.salary_text, j.workplace, j.status,"
            " a.fit_score, MAX(e.created_at) AS released_at FROM job_events e JOIN jobs j ON j.id=e.job_id"
            " JOIN job_analyses a ON a.job_id=j.id WHERE e.event_type='match_released' AND e.created_at>?"
            " GROUP BY j.id ORDER BY a.fit_score DESC", (seen,))]
    finally:
        conn.close()
    n = settings["notifications"]
    return {"waiting": len(pending_matches(settings, now=now)), "released": released,
            "release_count": n["release_count"], "release_cutoff_hour": n["release_cutoff_hour"],
            "min_fit_score": n["min_fit_score"], "last_release_at": load_state().get("last_release_at")}


def mark_matches_seen(*, now: int | None = None) -> dict:
    _save_state(matches_seen_at=int(time.time()) if now is None else now)
    return inbox(now=now)


def build_digest(*, now: int | None = None) -> tuple[str, str] | None:
    """(subject, body) for the last 24 hours, or None when there is nothing to say."""
    from api.job_os.applications import board

    now = int(time.time()) if now is None else now
    since = now - 86400
    conn = connect_job_os()
    try:
        found = conn.execute("SELECT COUNT(*) FROM jobs WHERE created_at>=?", (since,)).fetchone()[0]
        top = conn.execute(
            "SELECT j.id, j.title, j.company, j.canonical_url, a.fit_score FROM jobs j JOIN job_analyses a ON a.job_id=j.id"
            " WHERE a.status='done' AND a.finished_at>=? ORDER BY a.fit_score DESC LIMIT 5", (since,)).fetchall()
        # Every job found today, best score first, then newest: the digest is
        # where you see them even before Luna has scored them.
        new_jobs = conn.execute(
            "SELECT j.id, j.title, j.company, j.location, j.canonical_url, a.fit_score FROM jobs j"
            " LEFT JOIN job_analyses a ON a.job_id=j.id AND a.status='done' WHERE j.created_at>=?"
            " ORDER BY a.fit_score IS NULL, a.fit_score DESC, j.created_at DESC", (since,)).fetchall()
        applied = conn.execute("SELECT COUNT(*) FROM job_events WHERE event_type='application_submitted' AND created_at>=?",
                               (now - 7 * 86400,)).fetchone()[0]
    finally:
        conn.close()
    columns = board()["columns"]
    attention = [(card, reason) for column in columns for card in column["jobs"] for reason in card["attention"]]
    # Applications gone quiet get their own section: they are the ones to act on today.
    follow_ups = [(card, reason) for card, reason in attention if "follow up" in reason]
    closing = [(card, reason) for card, reason in attention if reason.startswith("Closes")]
    attention = [(card, reason) for card, reason in attention if "follow up" not in reason and not reason.startswith("Closes")]
    ready = next((c["jobs"] for c in columns if c["key"] == "ready"), [])
    if not (found or top or attention or ready or follow_ups or closing):
        return None
    parts = [f"Found in the last 24 hours: {found}", f"Applications sent this week: {applied}"]
    if follow_ups:
        parts.append("Follow up:\n" + "\n".join(
            f"  • {c['title']} at {c['company'] or '?'} — {reason.replace(' — follow up?', '')}\n    {c['canonical_url']}"
            for c, reason in follow_ups[:8]))
    if closing:
        parts.append("Closing soon:\n" + "\n".join(
            f"  • {c['title']} at {c['company'] or '?'} — {reason.lower()}\n    {c['canonical_url']}"
            for c, reason in sorted(closing, key=lambda pair: pair[0].get("deadline") or "")[:8]))
    if top:
        parts.append("Best new matches:\n" + "\n".join(f"  • {r['fit_score']} — {r['title']} at {r['company'] or '?'}\n    {r['canonical_url']}" for r in top))
    listed = {r["id"] for r in top}
    rest = [r for r in new_jobs if r["id"] not in listed]
    if rest:
        unscored = sum(1 for r in new_jobs if r["fit_score"] is None)
        def line(r):
            score = f"{r['fit_score']} — " if r["fit_score"] is not None else ""
            where = f" ({r['location']})" if r["location"] else ""
            return f"  • {score}{r['title']} at {r['company'] or '?'}{where}\n    {r['canonical_url']}"
        lines = [line(r) for r in rest[:15]]
        more = f"\n  …and {len(rest) - 15} more in Hermes -> Jobs -> Pipeline" if len(rest) > 15 else ""
        note = (f"\n  {unscored} not scored yet: Pipeline -> Score new, or turn on Settings -> AI -> Analyse new finds automatically."
                if unscored else "")
        parts.append(f"New jobs found ({len(new_jobs)}):\n" + "\n".join(lines) + more + note)
    if ready:
        parts.append("Ready to apply:\n" + "\n".join(f"  • {c['title']} at {c['company'] or '?'}" for c in ready[:8]))
    if attention:
        parts.append("Needs your attention:\n" + "\n".join(f"  • {c['title']}: {reason}" for c, reason in attention[:8]))
    extra = f", {len(follow_ups)} to follow up" if follow_ups else ""
    return (f"Daily digest — {found} found, {len(attention)} need attention{extra}",
            "\n\n".join(parts) + "\n\nOpen Hermes -> Jobs for details.")


def _user_zone(settings: dict):
    try:
        return ZoneInfo((settings.get("scout") or {}).get("timezone") or "Asia/Kuala_Lumpur")
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def maybe_send_digest(*, now: float | None = None, send: Callable = mailer.send, force: bool = False) -> bool:
    """Send today's digest once, at or after ``digest_hour`` local time."""
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not _ready(settings, *(() if force else ("daily_digest",))):
        return False
    now = time.time() if now is None else now
    # The digest hour is on your clock (Settings -> Scout schedule -> Your time
    # zone), not the server's.
    local = datetime.fromtimestamp(now, _user_zone(settings))
    today = local.strftime("%Y-%m-%d")
    if not force and (local.hour < settings["notifications"]["digest_hour"] or load_state().get("last_digest") == today):
        return False
    with _send_lock:
        digest = build_digest(now=int(now))
        _save_state(last_digest=today)
        if digest is None:
            _log("digest", "skipped", "", "Nothing new today")
            return False
        try:
            send(CONTEXT, settings["notifications"]["to_address"], *digest)
        except Exception as error:
            _log("digest", "failed", digest[0], str(error))
            raise
        _log("digest", "sent", digest[0])
        return True


# ---- replies -------------------------------------------------------------

def _reply_text(message) -> str:
    part = message.get_body(preferencelist=("plain",)) if hasattr(message, "get_body") else None
    if part is None:
        return ""
    lines = []
    for line in str(part.get_content() or "").splitlines():
        if line.lstrip().startswith(">"):
            continue
        if re.match(r"^\s*On .+wrote:\s*$", line) or line.strip().startswith("-----Original Message"):
            break
        lines.append(line)
    return "\n".join(lines)


def authenticated_from(message, expected: str) -> bool:
    """From is ``expected`` and Gmail's topmost Authentication-Results says dmarc=pass."""
    sender = parseaddr(str(message.get("From") or ""))[1].lower()
    if not sender or sender != expected.strip().lower():
        return False
    results = message.get_all("Authentication-Results") or []
    if not results:
        return False
    top = re.sub(r"\s+", " ", str(results[0])).strip().lower()
    return top.startswith("mx.google.com;") and "dmarc=pass" in top


def commands_in(message) -> list[tuple[str, str]]:
    seen, out = set(), []
    for action, code in _COMMAND.findall(_reply_text(message)):
        key = (action.lower(), code.upper())
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _act(action: str, job_id: str) -> str:
    from api.job_os import tailor
    from api.job_os.lifecycle import transition_job
    from api.job_os.models import JobStatus
    from api.job_os.repository import get_job

    job = get_job(job_id)
    if job is None:
        return "that job no longer exists"
    name = f"{job.title}" + (f" at {job.company}" if job.company else "")
    try:
        if action == "tailor":
            tailor.request_tailoring(job_id)
            return f"Tailoring started for {name}."
        if action == "skip":
            transition_job(job_id, JobStatus.SKIPPED, expected_revision=job.revision)
            return f"Skipped {name}."
    except Exception as error:
        return f"Couldn't {action} {name}: {error}"
    return f"Unknown action for {name}."


def handle_message(raw: bytes, settings: dict, *, now: int | None = None) -> list[str] | None:
    """Act on one received email. Returns the outcome lines, or None if it was not a valid command reply."""
    message = email.message_from_bytes(raw, policy=email.policy.default)
    commands = commands_in(message)
    if not commands:
        return None
    if not authenticated_from(message, settings["notifications"]["to_address"]):
        _log("reply", "rejected", str(message.get("Subject") or ""), "Not from the Send-to address, or failed Gmail authentication")
        return None
    outcomes = []
    for action, code in commands:
        if action not in ACCEPTED_ACTIONS:
            continue
        job_id = redeem_code(action, code, now=now)
        if job_id is None:
            outcomes.append(f"{action.upper()} {code}: code unknown, already used, or expired.")
            continue
        result = _act(action, job_id)
        conn = connect_job_os()
        try:
            _event(conn, job_id, "reply_action", {"action": action, "result": result[:200]})
            conn.commit()
        finally:
            conn.close()
        outcomes.append(result)
    _log("reply", "handled", str(message.get("Subject") or ""), " | ".join(outcomes))
    return outcomes


def _imap_fetch(address: str, password: str, from_address: str, state: dict) -> tuple[list[tuple[int, bytes]], dict]:
    """New messages from ``from_address`` since the last poll: ([(uid, raw)], new_state)."""
    with imaplib.IMAP4_SSL(mailer.IMAP_HOST, mailer.IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=mailer.TIMEOUT) as imap:
        imap.login(address, password)
        _typ, info = imap.status("INBOX", "(UIDNEXT UIDVALIDITY)")
        numbers = dict(re.findall(r"(UIDNEXT|UIDVALIDITY) (\d+)", (info[0] or b"").decode()))
        validity, uidnext = int(numbers.get("UIDVALIDITY", 0)), int(numbers.get("UIDNEXT", 1))
        if state.get("imap_uidvalidity") != validity or "imap_last_uid" not in state:
            # First poll (or the mailbox was rebuilt): start from now, never act on old mail.
            return [], {"imap_uidvalidity": validity, "imap_last_uid": uidnext - 1}
        last = int(state["imap_last_uid"])
        imap.select("INBOX", readonly=True)
        _typ, data = imap.uid("SEARCH", None, f"UID {last + 1}:*", "FROM", f'"{from_address}"')
        found = []
        for uid in sorted(int(u) for u in (data[0] or b"").split() if int(u) > last)[:20]:
            _typ, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), b"")
            found.append((uid, raw))
        newest = max([last] + [uid for uid, _raw in found])
        return found, {"imap_uidvalidity": validity, "imap_last_uid": newest}


def poll_replies(*, now: int | None = None, fetch: Callable | None = None, send: Callable = mailer.send) -> int:
    """Check the sender inbox for command replies. Returns how many replies were acted on."""
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not _ready(settings, "reply_actions"):
        return 0
    if not _poll_lock.acquire(blocking=False):
        return 0
    try:
        address, password = mailer.credentials()
        try:
            messages, new_state = mailer.with_retry(fetch or _imap_fetch, address, password,
                                                    settings["notifications"]["to_address"], load_state())
        except Exception as error:
            # last_poll stays the last check that worked; a blink is not reported.
            failed = mailer.check_failed(load_state(), "poll", error, int(time.time()))
            _save_state(**failed, last_poll_error=failed["poll_error"])
            return 0
        handled = 0
        for _uid, raw in messages:
            try:
                outcomes = handle_message(raw, settings, now=now)
            except Exception:
                logger.debug("reply handling failed", exc_info=True)
                continue
            if outcomes:
                handled += 1
                try:
                    send(CONTEXT, settings["notifications"]["to_address"], "Done: your reply",
                         "Here is what happened:\n\n" + "\n".join(f"  • {line}" for line in outcomes))
                except Exception:
                    logger.debug("reply confirmation failed", exc_info=True)
        _save_state(**new_state, **mailer.check_ok("poll", int(time.time())), last_poll=int(time.time()), last_poll_error="")
        return handled
    finally:
        _poll_lock.release()


# ---- schedule ------------------------------------------------------------

POLL_EVERY = 120


def tick(*, now: float | None = None) -> None:
    """One scheduler pass: alerts, digest, and (every two minutes) replies."""
    now = time.time() if now is None else now
    for step in (send_matches, maybe_send_digest):
        try:
            step()
        except Exception:
            logger.debug("Job OS notification step failed", exc_info=True)
    state = load_state()
    if now - float(state.get("poll_attempt") or state.get("last_poll") or 0) >= POLL_EVERY:
        try:
            poll_replies()
        except Exception:
            logger.debug("Job OS reply poll failed", exc_info=True)


def status() -> dict:
    from api.job_os import outcomes
    from api.job_os.settings import load_settings

    settings = load_settings()
    state = load_state()
    return {"connected": all(mailer.credentials()), "ready": _ready(settings),
            "last_digest": state.get("last_digest"), "last_poll": state.get("last_poll"),
            "last_poll_error": state.get("last_poll_error") or "", "log": recent_log(), "outcomes": outcomes.status()}
