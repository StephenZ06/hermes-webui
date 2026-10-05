"""Browser half of gated auto-apply. Runs in its own process (see autoapply.py).

Reads one JSON job from stdin, drives headless Chromium with Playwright, and
prints one JSON result line. Standard library + Playwright only, so it can run
under whichever interpreter has Playwright installed.

Modes:
  ``preview`` -- open the form, fill what it recognises, screenshot, never submit.
  ``submit``  -- the same, then press submit and wait for a confirmation.

Every field on the form is classified from its label/name. Known applicant
fields are filled; anything else that is required, any salary/legal/consent
question (required or not), and any visible captcha stops the run instead.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

SALARY_LEGAL = re.compile(
    r"salary|compensation|pay expectation|expected pay|desired pay|sponsor|visa|authori[sz]|right to work|"
    r"eligible to work|legally|criminal|convict|felony|background check|security clearance|non-?compete|"
    r"consent|privacy|\bterms\b|\bi agree\b|acknowledge|gdpr", re.I)
NOT_APPLICANT = re.compile(r"company|employer|school|universit|referr|reference|manager|recruiter|prefer", re.I)
RULES = (  # (field, pattern on "label name type")
    ("resume", re.compile(r"\b(resume|cv|curriculum)\b", re.I)),
    ("cover_letter", re.compile(r"cover[\s_-]*letter", re.I)),
    ("first_name", re.compile(r"first[\s_-]*name|given[\s_-]*name|forename", re.I)),
    ("last_name", re.compile(r"last[\s_-]*name|surname|family[\s_-]*name", re.I)),
    ("email", re.compile(r"e-?mail|\btype:email\b", re.I)),
    ("phone", re.compile(r"phone|mobile|\btype:tel\b", re.I)),
    ("linkedin_url", re.compile(r"linked\s*in", re.I)),
    ("portfolio_url", re.compile(r"website|portfolio|personal (site|url)|github", re.I)),
    ("location", re.compile(r"\blocation\b|\bcity\b|where are you (based|located)|current address", re.I)),
    ("full_name", re.compile(r"(^|\b)(full[\s_-]*name|your name|legal name|_systemfield_name|name)\b", re.I)),
)
EEO = re.compile(r"gender|race|ethnic|veteran|disabilit|hispanic|latino|pronoun|sexual orientation|transgender", re.I)
CONFIRM = re.compile(r"thank you for (applying|your application)|application (has been |was )?(submitted|received)|"
                     r"we('ve| have) received your application|successfully submitted", re.I)

# Collect every visible form control with its label text and required flag.
_COLLECT_JS = r"""
() => {
  const seen = new Set(); const out = [];
  const textOf = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const visible = (el) => { if (el.type === 'file') return true; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const controls = [...document.querySelectorAll('input, select, textarea')]
    .filter((el) => !['hidden', 'submit', 'button', 'reset', 'image', 'search'].includes((el.type || '').toLowerCase()));
  controls.forEach((el, index) => {
    if (!visible(el) || el.disabled) return;
    if (el.type === 'radio' || el.type === 'checkbox') { if (el.name && seen.has(el.name)) return; if (el.name) seen.add(el.name); }
    let label = el.getAttribute('aria-label') || '';
    if (!label && el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); label = textOf(l); }
    if (!label && el.getAttribute('aria-labelledby')) label = el.getAttribute('aria-labelledby').split(/\s+/).map((id) => textOf(document.getElementById(id))).join(' ');
    if (!label) label = textOf(el.closest('label'));
    if (!label) { const f = el.closest('fieldset'); if (f) label = textOf(f.querySelector('legend')); }
    if (!label) { const box = el.closest('div, li, section'); if (box) { const l = box.querySelector('label, legend, [class*="label"]'); label = textOf(l); } }
    if (!label) label = el.getAttribute('placeholder') || '';
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label) || /\(required\)/i.test(label);
    el.setAttribute('data-hermes-field', String(index));
    out.push({index, tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(), name: el.name || el.id || '',
              label: label.slice(0, 200), required, accept: el.getAttribute('accept') || ''});
  });
  return out;
}
"""

_CAPTCHA_JS = r"""
() => [...document.querySelectorAll('iframe')].some((f) => {
  const src = f.src || ''; const r = f.getBoundingClientRect();
  if (!/recaptcha|hcaptcha|challenges\.cloudflare|turnstile|arkoselabs|funcaptcha/i.test(src)) return false;
  if (/size=invisible/i.test(src)) return false;
  return r.width > 30 && r.height > 30 && getComputedStyle(f).visibility !== 'hidden';
})
"""


def classify(control: dict) -> str:
    """The applicant field a control asks for, or 'eeo' / 'sensitive' / 'unknown'."""
    text = f"{control.get('label', '')} {control.get('name', '')} type:{control.get('type', '')}"
    if SALARY_LEGAL.search(text):
        return "sensitive"
    if control.get("type") == "file":
        if RULES[1][1].search(text):
            return "cover_letter"
        if RULES[0][1].search(text):
            return "resume"
        # An unlabeled upload (e.g. Ashby's "autofill from resume" drop zone) is never guessed at.
        labelled = (control.get("label") or control.get("name") or "").strip()
        return "resume" if labelled and "pdf" in control.get("accept", "") else "unknown"
    if EEO.search(text):
        return "eeo"
    for field, pattern in RULES[2:]:
        if field in ("full_name", "first_name", "last_name") and NOT_APPLICANT.search(text):
            continue
        if pattern.search(text):
            return field
    if control.get("tag") == "textarea" and RULES[1][1].search(text):
        return "cover_letter"
    return "unknown"


def plan(controls: list[dict], applicant: dict, files: dict, cover_text: str) -> tuple[list[dict], list[str]]:
    """(fills, stop_reasons). Pure: decides everything before the page is touched."""
    fills, stops = [], []
    full = str(applicant.get("full_name") or "").strip()
    first, _, last = full.partition(" ")
    values = {**applicant, "first_name": first, "last_name": last.strip() or first}
    for c in controls:
        field = classify(c)
        label = re.sub(r"[\s*✱]+$", "", c.get("label") or c.get("name") or "") or "a field"
        if field == "sensitive":
            stops.append(f"Salary, legal or consent question: “{label[:80]}”")
            continue
        if field == "eeo":
            if c["required"]:
                stops.append(f"Required personal (EEO) question: “{label[:80]}”")
            continue
        if field in ("resume", "cover_letter") and c["type"] == "file":
            path = files.get(field)
            if path:
                fills.append({"index": c["index"], "field": field, "file": path, "label": label})
            elif c["required"]:
                stops.append(f"Required upload: “{label[:80]}”")
            continue
        if field == "cover_letter":
            if cover_text:
                fills.append({"index": c["index"], "field": field, "value": cover_text, "label": label})
            elif c["required"]:
                stops.append(f"Required question: “{label[:80]}”")
            continue
        value = str(values.get(field) or "").strip() if field != "unknown" else ""
        if value and c["type"] not in ("checkbox", "radio", "select-one", "select-multiple") and c["tag"] != "select":
            fills.append({"index": c["index"], "field": field, "value": value, "label": label})
        elif c["required"]:
            stops.append(f"Required question Hermes can't answer: “{label[:80]}”")
    return fills, stops


def _fill(page, fills: list[dict]) -> None:
    for item in fills:
        locator = page.locator(f'[data-hermes-field="{item["index"]}"]')
        if "file" in item:
            locator.set_input_files(item["file"])
        else:
            locator.fill(item["value"])
        page.wait_for_timeout(120)


def _submit_button(page):
    for selector in ('button[type="submit"]', 'input[type="submit"]', 'button:has-text("Submit application")',
                     'button:has-text("Submit Application")', 'button:has-text("Submit")'):
        button = page.locator(selector)
        if button.count():
            return button.last
    return None


def run(job: dict) -> dict:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    result = {"status": "error", "reason": "", "filled": [], "stops": [], "screenshots": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"])
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 1600}, locale="en-US")
            page = context.new_page()
            for kind, html in (job.get("pdf_html") or {}).items():  # render tailored documents to PDF first
                page.set_content(html, wait_until="load")
                target = out_dir / f"{kind}.pdf"
                page.pdf(path=str(target), format="A4", print_background=False)
                job.setdefault("files", {})[kind] = str(target)
            page.goto(job["url"], wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeout:
                pass
            try:  # single-page apps (Ashby) render the form after load
                page.wait_for_selector('input[type="email"], input[name*="email" i], input[id*="email" i]', timeout=20000)
            except PlaywrightTimeout:
                pass
            controls = page.evaluate(_COLLECT_JS)
            if not any(classify(c) == "email" for c in controls):
                result.update(status="stopped", reason="No application form found on the page.")
                return result
            fills, stops = plan(controls, job.get("applicant") or {}, job.get("files") or {}, job.get("cover_text") or "")
            if page.evaluate(_CAPTCHA_JS):
                stops.append("A captcha must be solved by a person.")
            result["stops"] = stops
            if not stops:
                _fill(page, fills)
                result["filled"] = [{"field": f["field"], "label": f["label"][:80]} for f in fills]
            shot = f"{stamp}-{job['mode']}-filled.png"
            page.screenshot(path=str(out_dir / shot), full_page=True)
            result["screenshots"].append(shot)
            if stops:
                result.update(status="stopped", reason=stops[0])
                return result
            if job["mode"] != "submit":
                result.update(status="filled")
                return result
            button = _submit_button(page)
            if button is None:
                result.update(status="stopped", reason="Couldn't find the submit button.")
                return result
            button.click()
            deadline = time.time() + 25
            confirmed = False
            while time.time() < deadline:
                page.wait_for_timeout(1000)
                text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 20000) : ''")
                if CONFIRM.search(text) or re.search(r"/(confirmation|thank|success)", page.url, re.I):
                    confirmed = True
                    break
                if page.evaluate(_CAPTCHA_JS):
                    break
            shot = f"{stamp}-submit-result.png"
            page.screenshot(path=str(out_dir / shot), full_page=True)
            result["screenshots"].append(shot)
            if confirmed:
                result.update(status="submitted")
            elif page.evaluate(_CAPTCHA_JS):
                result.update(status="stopped", reason="A captcha appeared after pressing submit.")
            else:
                result.update(status="stopped", reason="No confirmation after submitting; check the screenshot and the site.")
            return result
        finally:
            browser.close()


def main() -> int:
    job = json.loads(sys.stdin.read())
    try:
        result = run(job)
    except Exception as error:  # report, never hang
        result = {"status": "error", "reason": f"Browser run failed ({type(error).__name__}: {str(error)[:200]})",
                  "filled": [], "stops": [], "screenshots": []}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
