"""The daily digest as a dark HTML email: stat cards, charts and job tables.

``notify.digest_data`` gathers the day; ``notify.build_digest`` writes it as
the plain-text part (the canonical message, and what replies quote). This is
the HTML part beside it. Mail clients drop most of CSS, so everything is
tables, inline styles and ``bgcolor`` attributes: no images, no scripts, no
external fonts, and every value from a job posting is escaped. The page says
it is dark (``color-scheme``) so clients that repaint light emails leave it be.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta

BG = "#0e1116"
CARD = "#161b22"
INSET = "#1c232c"
BORDER = "#2a323d"
TEXT = "#e8edf3"
MUTED = "#98a3b0"
ACCENT = "#5b9bd5"
GOOD = "#4ade80"
WARN = "#f5b84b"
BAD = "#f07878"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"
CHART_DAYS = 14
BAR_MAX_PX = 64


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _link(url: str, text: str) -> str:
    url = str(url or "")
    if not url.lower().startswith(("https://", "http://")):
        return f'<span style="color:{TEXT};">{_e(text)}</span>'
    return f'<a href="{_e(url)}" style="color:{TEXT};text-decoration:none;font-weight:600;">{_e(text)}</a>'


def _score_tone(score) -> str:
    if score is None:
        return MUTED
    return GOOD if score >= 75 else WARN if score >= 50 else BAD


def _chip(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;padding:2px 7px;border-radius:5px;border:1px solid {color};'
            f'color:{color};font-size:11px;font-weight:700;line-height:16px;white-space:nowrap;">{_e(text)}</span>')


def _card(title: str, body: str, *, count: int | None = None) -> str:
    badge = (f'<span style="display:inline-block;margin-left:8px;padding:0 6px;border-radius:5px;background:{INSET};'
             f'color:{MUTED};font-size:11px;font-weight:700;line-height:18px;">{count}</span>') if count is not None else ""
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="{CARD}" '
            f'style="background:{CARD};border:1px solid {BORDER};border-radius:12px;margin:0 0 14px;">'
            f'<tr><td style="padding:16px 18px 6px;color:{TEXT};font-size:12px;font-weight:700;letter-spacing:.08em;'
            f'text-transform:uppercase;">{_e(title)}{badge}</td></tr>'
            f'<tr><td style="padding:4px 18px 14px;">{body}</td></tr></table>')


def _stats(d: dict) -> str:
    items = [("Found today", d["found"], ACCENT), ("Applied this week", d["applied"], GOOD),
             ("To follow up", len(d["follow_ups"]), WARN), ("Need attention", len(d["attention"]), BAD)]
    cells = "".join(
        f'<td width="25%" valign="top" style="padding:0 4px;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="{CARD}" '
        f'style="background:{CARD};border:1px solid {BORDER};border-radius:12px;">'
        f'<tr><td style="padding:14px 14px 0;"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;'
        f'background:{color};"></span></td></tr>'
        f'<tr><td style="padding:6px 14px 0;color:{TEXT};font-size:26px;font-weight:700;line-height:30px;">{_e(value)}</td></tr>'
        f'<tr><td style="padding:2px 14px 14px;color:{MUTED};font-size:12px;line-height:16px;">{_e(label)}</td></tr>'
        f'</table></td>' for label, value, color in items)
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 14px;">'
            f'<tr>{cells}</tr></table>')


def _found_chart(d: dict) -> str:
    activity = d.get("activity") or {}
    try:
        end = date.fromisoformat(activity.get("today") or "")
    except ValueError:
        return ""
    days = activity.get("days") or {}
    series = [(end - timedelta(days=CHART_DAYS - 1 - i)) for i in range(CHART_DAYS)]
    counts = [int((days.get(day.isoformat()) or {}).get("found") or 0) for day in series]
    if not any(counts):
        return ""
    top = max(counts)
    bars = "".join(
        f'<td valign="bottom" align="center" style="padding:0 2px;height:{BAR_MAX_PX + 18}px;">'
        f'<div style="color:{MUTED};font-size:10px;line-height:14px;">{n or ""}</div>'
        f'<div style="height:{max(3, round(BAR_MAX_PX * n / top)) if n else 3}px;line-height:1px;font-size:1px;'
        f'border-radius:3px 3px 0 0;background:{ACCENT if day == end else (ACCENT + "99" if n else BORDER)};">&nbsp;</div></td>'
        for day, n in zip(series, counts))
    labels = "".join(f'<td align="center" style="padding:6px 2px 0;color:{MUTED};font-size:10px;line-height:12px;">'
                     f'{_e(day.strftime("%a")[0])}<br>{day.day}</td>' for day in series)
    total = sum(counts)
    body = (f'<p style="margin:0 0 10px;color:{MUTED};font-size:13px;line-height:18px;">{total} found in the last {CHART_DAYS} days</p>'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="table-layout:fixed;">'
            f'<tr>{bars}</tr><tr>{labels}</tr></table>')
    return _card("Jobs found", body)


def _funnel(d: dict) -> str:
    rows = [r for r in d.get("funnel") or [] if isinstance(r, dict)]
    if not rows or not rows[0].get("count"):
        return ""
    top = max(int(r.get("count") or 0) for r in rows) or 1
    lines = "".join(
        f'<tr><td width="96" style="padding:5px 12px 5px 0;color:{MUTED};font-size:13px;white-space:nowrap;">{_e(r.get("label"))}</td>'
        f'<td style="padding:5px 0;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'bgcolor="{INSET}" style="background:{INSET};border-radius:5px;"><tr>'
        f'<td width="{max(2, round(100 * int(r.get("count") or 0) / top))}%" bgcolor="{ACCENT}" '
        f'style="background:{ACCENT};height:10px;line-height:10px;font-size:1px;border-radius:5px;">&nbsp;</td>'
        f'<td style="font-size:1px;line-height:10px;">&nbsp;</td></tr></table></td>'
        f'<td width="44" align="right" style="padding:5px 0 5px 12px;color:{TEXT};font-size:13px;font-weight:700;">{_e(r.get("count"))}</td></tr>'
        for r in rows)
    return _card("Application funnel", f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{lines}</table>')


def _job_rows(rows: list[tuple[str, str, str, str]]) -> str:
    """``(score_chip_html, title_link_html, detail, note)`` rows as one table."""
    def line(text: str, color: str) -> str:
        return f'<br><span style="color:{color};font-size:12px;line-height:17px;">{_e(text)}</span>' if text else ""

    cells = "".join(
        f'<tr><td width="46" valign="top" style="padding:10px 10px 10px 0;border-top:1px solid {BORDER};">{chip}</td>'
        f'<td valign="top" style="padding:10px 0;border-top:1px solid {BORDER};font-size:14px;line-height:19px;">{title}'
        f'{line(detail, MUTED)}{line(note, WARN)}</td></tr>'
        for chip, title, detail, note in rows)
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">{cells}</table>'


def _where(job: dict) -> str:
    return " · ".join(str(x) for x in (job.get("company"), job.get("location")) if x)


def _scored(job: dict) -> str:
    score = job.get("fit_score")
    return _chip(str(score) if score is not None else "—", _score_tone(score))


def digest_html(d: dict, *, sender: str = "Hermes Jobs", zone=None) -> str:
    when = datetime.fromtimestamp(d["now"], zone) if zone is not None else datetime.fromtimestamp(d["now"])
    sections = [_stats(d), _found_chart(d)]
    if d["follow_ups"]:
        sections.append(_card("Follow up", _job_rows([
            (_chip("Quiet", WARN), _link(c.get("canonical_url"), c.get("title") or "Untitled job"), _where(c),
             reason.replace(" — follow up?", "")) for c, reason in d["follow_ups"][:8]]), count=len(d["follow_ups"])))
    if d["closing"]:
        sections.append(_card("Closing soon", _job_rows([
            (_chip("Soon", BAD), _link(c.get("canonical_url"), c.get("title") or "Untitled job"), _where(c), reason)
            for c, reason in d["closing"][:8]]), count=len(d["closing"])))
    if d["top"]:
        sections.append(_card("Best new matches", _job_rows([
            (_scored(r), _link(r.get("canonical_url"), r.get("title") or "Untitled job"), _where(r), "") for r in d["top"]]),
            count=len(d["top"])))
    rest = d["rest"]
    if rest:
        unscored = sum(1 for r in d["new_jobs"] if r.get("fit_score") is None)
        more = (f'<p style="margin:10px 0 0;color:{MUTED};font-size:12px;line-height:17px;">…and {len(rest) - 15} more in '
                f'Hermes → Jobs → Pipeline.</p>') if len(rest) > 15 else ""
        note = (f'<p style="margin:10px 0 0;color:{MUTED};font-size:12px;line-height:17px;">{unscored} not scored yet: '
                f'Pipeline → Score new.</p>') if unscored else ""
        sections.append(_card("New jobs found", _job_rows([
            (_scored(r), _link(r.get("canonical_url"), r.get("title") or "Untitled job"), _where(r), "") for r in rest[:15]]) + more + note,
            count=len(d["new_jobs"])))
    if d["ready"]:
        sections.append(_card("Ready to apply", _job_rows([
            (_chip("Ready", GOOD), _link(c.get("canonical_url"), c.get("title") or "Untitled job"), _where(c), "") for c in d["ready"][:8]]),
            count=len(d["ready"])))
    if d["attention"]:
        sections.append(_card("Needs your attention", _job_rows([
            (_chip("Check", BAD), _link(c.get("canonical_url"), c.get("title") or "Untitled job"), _where(c), reason)
            for c, reason in d["attention"][:8]]), count=len(d["attention"])))
    sections.append(_funnel(d))
    body = "".join(s for s in sections if s)
    title = "Daily digest"
    return f"""<!doctype html>
<html lang="en" style="color-scheme:dark;">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
  <title>{_e(title)}</title>
  <style>:root{{color-scheme:dark;supported-color-schemes:dark;}}</style></head>
  <body bgcolor="{BG}" style="margin:0;padding:0;background:{BG};color:{TEXT};font-family:{FONT};">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="{BG}" style="background:{BG};padding:24px 10px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;">
          <tr><td style="padding:4px 4px 18px;">
            <p style="margin:0 0 6px;color:{ACCENT};font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">{_e(sender)}</p>
            <h1 style="margin:0;color:{TEXT};font-size:24px;line-height:30px;font-weight:700;">{_e(title)}</h1>
            <p style="margin:6px 0 0;color:{MUTED};font-size:13px;line-height:18px;">{_e(when.strftime("%A, %d %B %Y"))} · the last 24 hours</p>
          </td></tr>
          <tr><td>{body}</td></tr>
          <tr><td style="padding:8px 4px 0;color:{MUTED};font-size:12px;line-height:17px;">Open Hermes → Jobs for details. Sent by Hermes.</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
