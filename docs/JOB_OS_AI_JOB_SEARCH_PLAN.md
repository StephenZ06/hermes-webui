# Job OS × ai-job-search: improvement plan

Status: **proposed, not started** (written 2026-10-27).
Source reviewed: [ai-job-search-dev/ai-job-search](https://github.com/ai-job-search-dev/ai-job-search)
at commit `4b109c2` (2026-10-26), MIT licence, © 2026 Mads Lorentzen.

## Why

ai-job-search is a Claude Code command set (`/scrape`, `/rank`, `/apply`,
`/outcome`, `/interview`, `/upskill`) driven from a terminal, with Danish job
boards. Job OS already automates more of the pipeline: Scout, scoring,
tailoring, the Apply kit and Gmail replies. The value is in its **rules**,
not its code: what to check before scoring, how to retire dead postings, how
to chase quiet applications, how to treat postings as hostile input. This plan
ports nine of those rules into Job OS as server features with UI.

## Ground rules for every phase

- **Credit.** Rules adapted from ai-job-search get a module docstring line,
  `Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT)`,
  like `tailor.py`'s credit to the resume-tailoring skill. Code is written
  fresh for Job OS. Their files are not vendored.
- **Never invent, never send.** The existing Job OS rules stand. Luna cites
  only the resume and your answers, unsupported claims are flagged, and
  Hermes never submits applications or sends mail on its own.
- **Fail closed.** A check that cannot decide flags the job for you. It never
  passes it silently, and it never drops it silently either.
- **Profile-scoped state** stays in `webui_state/job_os/job_os.db`. New
  columns go through `api/job_os/schema.py` migrations (`ALTER TABLE … ADD
  COLUMN`, defaults that keep old rows valid).
- **Model calls are counted.** Each phase states its extra Luna calls per job.
  Anything that doubles cost is a setting, off by default.
- **Each phase is one commit or PR** with tests that fail before it and pass
  after, `docs/job-os.md` updated, the service restarted, and `graphify update .`.
- UI work follows `docs/UIUX-GUIDE.md` and `DESIGN.md` and uses the impeccable
  skill, with desktop and phone checked.

## Phases at a glance

| # | Phase | Value | Effort | Extra Luna calls |
|---|---|---|---|---|
| 1 | Posting guard (clean hidden text, flag injection) | Security | S | 0 |
| 2 | Eligibility and language gates | Stops wasted tailoring | S | 0 (same scoring call) |
| 3 | Deadlines, expiry and stale postings | Stops dead-job spend | M | 0 (same scoring call) |
| 4 | Dimension scores and location veto | Better ranking | S–M | 0 (same scoring call) |
| 5 | Follow-up drafts and the stale sweep | Applications get chased | M | 1 per draft, on request |
| 6 | Resume parse check (ATS) on export | Fewer silent rejections | S–M | 0 |
| 7 | Second-pass review of tailored documents | Better documents | M | +1–2 per tailoring (setting) |
| 8 | Calibration from outcomes | Scoring learns | M | 1 per calibration, on request |
| 9 | Skill-gap report | Career planning | M | 1 per report, on request |

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. Phases 2–4 change the
same scoring prompt, so they ship one after another and share one prompt
version bump.

---

## Phase 1: Posting guard

**Problem.** Postings are text from strangers, read by Luna next to your
resume and application answers. Today the only defence is the `llm.UNTRUSTED`
instruction. The page readers (`firecrawl.py`, `extract.py`, `remoteid.py`,
Apify mapping in `apify.py`) do not strip hidden text, invisible characters
or tag characters.

**Change.**
- New `api/job_os/posting_guard.py`, adapted from `tools/posting_guard.py`
  (about 480 lines, standard library only). It removes hidden HTML (inline
  hidden styles, the `hidden` attribute, `aria-hidden`), comments,
  script/style/template blocks, zero-width and bidi characters, and Unicode
  tag characters. It flags instruction-shaped lines aimed at an agent,
  words mixing Latin with Cyrillic or Greek letters, and links that only
  exist in hidden text. It returns `(clean_text, findings)`.
- Call it at the one place every posting enters: where Scout and Add job save
  `description` (`scout.py` save path, `extract.py`, and the
  `repository.py` insert). Store the cleaned text. Store the findings as
  counts and a verdict in a new `jobs.guard_json` column, with excerpts
  capped at 3 × 160 characters.
- It **advises and never blocks.** A flagged job is still saved and scored.

**UI.** A small shield chip on the card and in the job drawer when the
verdict is flagged ("Hidden instructions found"). The drawer lists the
excerpts.

**Tests.**
- Unit cases for each payload class: hidden span, zero-width character
  inside a word, a tag-character sentence, an "ignore previous instructions"
  line, a Cyrillic look-alike.
- A clean real posting stays byte-identical except for whitespace.
- An API test: a job saved with a hidden payload never has it in
  `description`.

**Risk.** False positives on legitimate text (an SSH admin job). Mitigation:
flag only, quote the line, never remove visible text.

## Phase 2: Eligibility and language gates

**Problem.** Scoring ignores Settings → Application answers
(`work_authorization`, `relocation`, `languages`), so a "citizens only" or
"fluent Arabic required" job still scores 80 and gets tailored.

**Change.**
- Extend the scoring prompt in `analysis.py` (`SYSTEM`) to receive a compact
  profile block built from `settings["apply"]` and to return:
  ```json
  "gates": {
    "eligibility": "pass|fail|unverified",
    "eligibility_quote": "<posting wording>",
    "language": "pass|fail|flag",
    "language_quote": "<posting wording>"
  }
  ```
  The verdict rules are adapted from `04-job-evaluation.md`:
  - **Eligibility.** A citizenship, permanent-residency or security-clearance
    requirement is a fail. Explicit visa or sponsorship acceptance is a pass.
    A posting that says nothing is `unverified`, never a pass.
  - **Language.** A required language you don't list is a fail. A bar that
    reads above your stated level is a flag. Otherwise it's a pass.
- `_clean` validates the gate values. Missing or invalid values become
  `unverified` or `flag` (fail closed).
- A **fail** caps the job's verdict at "poor" and keeps it out of the Scout
  inbox, good-match email and Automate all (`autopilot.py`). The job stays on
  the board, with the quote, so you can override it ("Ignore this gate" in
  the drawer, stored per job).
- If Application answers are empty, the gates return `unverified` and the
  drawer says "Add your work authorisation and languages in Settings".

**UI.** A red chip on a fail ("Citizens only", "Needs Arabic"), amber on a
flag or unverified. The drawer shows the quoted wording. The Match check
shows the chip.

**Tests.**
- Prompt-contract tests on `_clean` (invalid values become fail closed).
- Autopilot skips gate-failed jobs; an overridden job is not skipped.
- An inbox-release test.
- A browser test for the chip and the override.

**Cost.** None extra (same call). The prompt version is bumped, and existing
analyses are kept until re-scored.

## Phase 3: Deadlines, expiry and stale postings

**Problem.** Job OS has an `expired` status but nothing sets it. Closing
dates aren't captured, so dead postings keep their place and get tailored.

**Change.**
- **Capture.** The scoring call also returns `deadline` (`YYYY-MM-DD` or
  null). Apify adapters map any closing-date field they have. Store it in a
  new `jobs.deadline` column, validated, with unparseable values dropped and
  counted.
- **Daily sweep** (new `api/job_os/expiry.py`, run from `scheduler.py` once
  a day in the Scout time zone):
  - A `deadline` in the past moves a pre-application job to `expired`
    (allowed by `lifecycle._ALLOWED_TRANSITIONS`).
  - A deadline within 7 days marks the job "Closing soon".
  - A job with no deadline is **never** expired by date.
- **Evidence-based expiry check** (optional, Firecrawl or Apify on). It
  re-reads the posting of shortlisted and favourite jobs once a week. A
  "no longer available" page, a 410, or a redirect to a listing page means
  expired. A 404, 403 or timeout means "couldn't check", which changes
  nothing. This follows the `expired` versus `unreachable` rule from
  `/rank`.
- **Staleness.** A posting more than 30 days old (its `posted_at`) gets a
  ⚠ age label. It is a signal, not a veto.
- Every automatic expiry is reversible: drag the card back, and the activity
  log records why it moved.

**UI.**
- A "Closing in 3 days" chip.
- An Expired column, or the Closed column with an "expired" reason. Decide
  at implementation; the board columns are in `applications.py`.
- A Dashboard attention item, and a "Closing soon" section in the daily
  email.

**Tests.**
- Sweep unit tests: past, near and none, and a malformed date that is never
  compared.
- Expiry check: 410 means expired, 404 means unchanged.
- A board test for the chip.

## Phase 4: Dimension scores and location veto

**Problem.** One 0–100 number hides why a job fits.

**Change.**
- The scoring call returns `dimensions`:
  - `skills`, `experience`, `career` (each 0–100);
  - `culture` (0–100, or null when the posting gives nothing to judge);
  - `location` (`pass`, `fail` or `flag`) against Settings `relocation` and
    the search's workplace.
- `fit_score` becomes the weighted average: skills 30, experience 25,
  culture 15, career 30, with culture's weight shared out when it's null.
  Weights live in `settings` so Phase 8 can tune them.
- A location **fail** acts like a gate fail (Phase 2), and a flag gets an
  amber chip.
- Old analyses without dimensions render as today.

**UI.** The drawer and Match check show four small bars under the ring. The
List view can sort by any dimension.

**Tests.**
- The weighted-score maths, including the null-culture case.
- Back-compatibility rendering of an old analysis.
- The location veto feeding autopilot and the inbox.

## Phase 5: Follow-up drafts and the stale sweep

**Problem.** After 7 days of silence the board says "follow up?"
(`applications.FOLLOW_UP_DAYS`), and you write the message yourself.

**Change.**
- New `api/job_os/followup.py`. **Draft follow-up** in the job drawer (shown
  once an application is quiet for 7+ days). It makes one Luna call with
  the posting, the tailored resume and cover letter you sent, and the
  contact if known. The rules are adapted from `/outcome followup`:
  - 60–120 words, using only claims from what you sent;
  - one value reminder and one question about timing;
  - your cover letter's tone and language;
  - an email (subject line), LinkedIn or portal shape.
- **Never sent.** The draft can be copied, or opened in your mail app with
  `mailto:`. **I sent it** logs it on the job's activity and resets the
  quiet clock.
- **Two follow-ups at most.** After the second, the drawer offers "Mark no
  response".
- **Stale sweep.** A Pipeline toolbar action lists applications quiet for
  60+ days (adjustable) with checkboxes, then moves them to No response in
  one batch. Each move is logged and can be dragged back.
- Gmail replies (`outcomes.py`) already move jobs on replies. A reply
  arriving cancels a pending follow-up suggestion.

**UI.** The drawer section "Follow up" with draft, copy, open in mail and
"I sent it". A count on the Dashboard's attention list. The sweep is a sheet
on the Pipeline.

**Tests.**
- The draft prompt contract (no new claims: unknown skills in the output are
  flagged by the same unsupported-claim check tailoring uses).
- The two-follow-up cap.
- Sweep selection maths.
- A browser test of the drawer flow.

## Phase 6: Resume parse check (ATS) on export

**Problem.** Exports are never checked the way hiring software reads them.

**Change.**
- New `api/job_os/ats_check.py`. After a PDF or DOCX export, extract its text
  layer: DOCX through `zipfile` and XML (standard library), PDF through
  `pypdf` if installed, otherwise skipped with a note. Then check:
  1. **Contact details** (name, email, phone) appear as literal text.
  2. **No garbled glyphs** (replacement characters, private-use characters).
  3. **Reading order:** section headings appear in the master's order.
  4. **Keyword coverage:** the posting's must-haves (already in the analysis
     as `must_haves`) found in the text. Missing ones the resume genuinely
     lacks are listed as gaps, never inserted.
- The result is stored on the tailored document and shown in Resume Studio
  as a checklist, for example "Parse check: 4/4 · 7 of 9 key terms".
- `pypdf` becomes an optional dependency (BSD licence). Add it to the extras
  only if the PDF branch is wanted, with a rollback by removing the extra.

**Tests.** Extraction from a generated DOCX and PDF fixture, a missing-email
failure, keyword coverage maths, and graceful skip without `pypdf`.

## Phase 7: Second-pass review of tailored documents

**Problem.** Tailoring is a single pass. The `needs_review` status catches
unsupported claims but not weak framing or missed requirements.

**Change.**
- Setting: Settings → AI → **Review tailored documents** (off by default; it
  shows the cost "+1 call per tailoring").
- When it's on, `tailor.py` sends the draft resume and letter and the posting
  to a reviewer prompt with a fresh context. The reviewer returns:
  - missed requirements;
  - generic phrases;
  - claims not in the master;
  - two or three concrete edits.

  Luna then revises once, adapted from `/apply`'s drafter-reviewer split.
- The review notes are shown beside the tailored resume, where the gap
  report already is. The master → tailored score comparison still runs on
  the final text.
- Automate all respects the setting and queues the extra call.

**Tests.**
- With the setting off, the call count is unchanged.
- With it on, the reviewer's claims flag reaches `needs_review`.
- If the review call fails, the first draft is kept with a note (not lost).

## Phase 8: Calibration from outcomes

**Problem.** Rejections and interviews are recorded (Gmail replies, drags),
but scoring never learns which fits actually got interviews.

**Change.**
- Once **3 or more** applications have a final outcome (rejected,
  interviewing, offer, no response), the Dashboard offers **Calibrate
  scoring**.
- One Luna call reads, per resolved application, the analysis dimensions,
  gates and outcome. It proposes:
  - weight changes (bounded ±10 per dimension);
  - a short "what worked" note added to the scoring prompt as guidance;
  - patterns ("analyst roles at banks went silent twice").
- **You approve before anything changes.** The proposal is shown as a diff of
  weights and guidance. Accepting stores it in `settings["calibration"]`
  with a version and date. **Undo** restores the previous version.
- It never edits past scores, which stay comparable.

**Tests.**
- Below 3 outcomes there is no offer.
- Bounded weight changes.
- The approve and undo round trip.
- New analyses use the calibrated weights.

## Phase 9: Skill-gap report

**Problem.** Gaps are listed per job, never added up.

**Change.**
- Resume Studio → **Skill gaps**. It adds up the `gaps` and `must_haves` of
  analysed jobs (optionally only good matches, or a time window) into a
  ranked list with counts, then makes one Luna call to group them by theme
  and suggest a short learning plan. Study links are left out unless web
  search is available.
- Reports are saved, keeping the last 5. The next report shows "since last
  time": new gaps and closed gaps.
- Adapted from `/upskill`, aggregate mode.

**Tests.** The aggregation maths (deduplication of near-identical gap
strings), the saved-report diff, and the empty state with no analyses.

---

## Not adopted, and why

| ai-job-search piece | Reason |
|---|---|
| Danish job-board CLIs, `/add-portal` | Scout's Apify and remote.id sources already fit the markets used. New sites go in as `apify.ADAPTERS`. |
| LaTeX templates and page-layout verification | Job OS exports in the master resume's own design (`resume_style.py`). |
| `/notion-sync`, `/html-report` | The Jobs Dashboard covers this. |
| Upstream-update tooling, `/reset`, `/setup` document import | Specific to a forked terminal workflow. Resume Studio owns the master resume. |
| Salary lookup with your own data | Possible later. It needs a salary data source the user doesn't have yet. |
| Company research cache | Possible later, with Phase 7, if the reviewer gains web search. |

## Cross-cutting work

- **Docs:** each phase updates `docs/job-os.md`. Phase 1 adds a
  "Postings are untrusted" section, and Phase 3 documents the expiry rules.
- **Daily email** (`notify.py`) gains "Closing soon" (Phase 3) and "Ready to
  follow up" (Phase 5) sections, sharing the existing digest.
- **Prompt versioning:** Phases 2–4 bump one `ANALYSIS_PROMPT_VERSION` stored
  with each analysis, so **Score again** can target old analyses in bulk.
- **Performance:** the expiry sweep, the stale sweep and gap aggregation are
  SQL over the local database. Only the optional expiry re-check
  (Phase 3) reaches the network, at most once a week per job, through the
  existing Firecrawl or Apify paths and their cost caps.

## Definition of done (per phase)

1. Tests that fail before the change and pass after; the neighbouring Job OS
   suites pass (`./scripts/test.sh tests/test_job_os*`).
2. `docs/job-os.md` updated. The credit line is present where rules were
   adapted.
3. The UI is checked at desktop and phone widths with before and after
   screenshots.
4. `systemctl --user restart hermes-webui-native`, a commit, and
   `graphify update .`.

## Open questions for the owner

1. Phase 3: should an expired job go to **Closed** with a reason, or have
   its own **Expired** column?
2. Phase 6: is adding `pypdf` acceptable, or DOCX-only checks to start?
3. Phase 7: keep the review off by default (cost), or on for good matches
   only?
