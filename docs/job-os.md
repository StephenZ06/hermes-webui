# Jobs (Job OS)

The **Jobs** page is a profile-scoped job-search tracker. Its data lives in
`webui_state/job_os/job_os.db` for the active profile.

| Section | What it does |
|---|---|
| **Dashboard** | Counts, automations beside the funnel, recent jobs (ten a page), and **Add job**. |
| **Scout** | Saved Indeed searches; runs find postings and add them to the Pipeline. |
| **Pipeline** | Every job, from new find to offer: a board or a list. |
| **Resume Studio** | The master resume, its match score against a job, and tailored versions. |
| **Logistics** | A 3D view of the same jobs. |
| **Settings** | Connections (Firecrawl, Gmail), AI, your details, Scout schedule, notifications. |

## Two ways in

1. **Scout (automated).** A search names job titles or keywords, the country,
   optional cities, a date-posted window, *remote only*, and its **job sites**:
   Indeed, LinkedIn and Bayt (the last two need Apify; Bayt covers the Gulf
   and a few other markets, and is greyed out elsewhere).
   Job titles are comma-separated and each is searched on its own (up to 5).
   **Title must contain** keeps a posting only if its title has all the words
   of at least one phrase (`analyst`, or `soc, security analyst`): job sites
   match keywords loosely (on 2026-10-07 LinkedIn returned 342 jobs for "IT
   Analyst" in a day, 53 with "analyst" in the title). Scrapers that support it
   (valig's LinkedIn one, `titleInclude`) apply it before returning results,
   so dropped jobs cost nothing; Scout applies it to every site as well. Each run
   reads the country's Indeed results and saves every new posting with its
   description, salary, employment type and country (source `indeed`,
   `linkedin`; one role found on two sites is saved once). See
   `docs/job-os-firecrawl.md` for how Indeed is read.
   With **Apify** on (below), the same search runs on Apify instead.
2. **Add job (manual tracker).** For jobs found anywhere else: title, link,
   company, country, city, salary, employment type, workplace, the job
   description, a note, and whether you already applied (source `manual`).
   Any job's details can be corrected later with **Edit**.

Either way, a job with a description can be scored and tailored.

## Apify (Settings → Apify)

Indeed blocks a reader that asks for many pages from one address. With Apify
connected and **Search Indeed through Apify** on, each city in a Scout search
and site is one run of an Apify actor on Apify's own addresses; it returns finished postings, description included, and Scout
saves them like any other find (same duplicate, blocked-company and remote
checks; same `/viewjob?jk=` identity). Firecrawl is not needed for these runs.

- **Token:** paste it under Settings → Apify. Hermes checks it with Apify
  (`GET /v2/users/me`), then saves it as `APIFY_API_TOKEN` in the env files
  (the shared secrets file when enabled). It is sent to Apify in a header,
  never in a URL, and never returned to the browser (only "connected" and its
  last four characters).
- **Settings:** one actor (`owner/name`) per site and **Results per city**
  (1–1000), which caps the cost.

| Site | Scrapers (first = default) | Cost (free plan) | Notes |
|---|---|---|---|
| Indeed | `valig/indeed-jobs-scraper` | $0.001 a run + $0.10 per 1,000 jobs | country site per search |
| LinkedIn | `curious_coder/linkedin-jobs-scraper` | $0.00005 a run + $2.00 per 1,000 jobs | most used; no title filter or skip list on its side, so every job it returns is charged |
| LinkedIn | `valig/linkedin-jobs-scraper` | $0.001 a run + $0.40 per 1,000 jobs | applies the title filter and skips saved jobs on its side |
| Bayt | `blackfalcondata/bayt-scraper` | $0.0005 a run + $0.99 per 1,000 jobs | the Gulf's main board (Qatar, UAE, Saudi Arabia, Kuwait, Bahrain, Oman, ...); remembers earlier runs and returns only new jobs; Scout applies the title filter |

  The free plan includes $5 a month. Apify counts repeats of jobs you
  already have unless the scraper skips them. Checked on 2026-10-08,
  Malaysia, last 24 hours: curious_coder returned 40 jobs for "SOC Analyst"
  (5 with "analyst" in the title) and 200+ for "IT Analyst" (37 of the first
  200), all with full descriptions; quoting the phrase did not narrow it.
  valig's LinkedIn scraper with the title filter `analyst` returned 53 for
  "IT Analyst", all analyst titles.
- **Failures:** one city failing keeps the others; every city failing fails
  the run with Apify's reason (refused token, out of credit, no answer).
- **More sites or scrapers:** add an `Adapter` (input builder, record mapping,
  and the input fields it has for a title filter or a skip list) to
  `apify.ADAPTERS` and list it under its site in `apify.SITES`. Settings,
  the Scout form and the Pipeline tabs pick it up from there. (JobStreet,
  `blackfalcondata/jobstreet-scraper`, was removed on 2026-10-08; its adapter
  is in git history.)

## Schedule (Settings → Scout schedule)

Job ads go up on weekdays in a morning wave and an afternoon wave, with Monday
to Wednesday the busiest days and weekends the quietest, so by default each
saved search runs at **12:30 and 18:30 in its own country's time**, on that
country's working days, plus **one Saturday run**:

- Malaysia (UTC+8): Monday to Friday; Saturday once; Sunday off.
- Qatar (UTC+3): Sunday to Thursday; Saturday once; Friday off.
- Other countries use their clock and working week from `indeed.CLOCKS`.

After a run that found 0–1 new jobs, the rest of that day is skipped. *Every
few hours* (the old interval) is still available. **Your time zone** sets the
evening update below.

## From find to tailored resume

1. Scout saves each new posting with its description.
2. Luna scores your **master resume** against it right away (Settings → AI →
   *Analyse new finds automatically*; needs a master resume in Resume Studio,
   and a run says so when it is missing).
3. **Good matches** (default 65%+) wait in the Scout inbox. They are
   announced together, once 5 are waiting or at 20:00 your time (once a
   day): the Scout page lists them, the side panel shows a count, and, with
   email on, one email lists them best first.
4. You choose **Tailor resume** on the ones worth it; Luna writes the
   tailored resume and cover letter in Resume Studio.

Pay only for new jobs: scrapers that take a skip list (valig's LinkedIn one)
are given the jobs Scout already has to leave out. The others return them
again and Scout drops the repeats.

## Watching the cost and the result

- **Apify credit (side panel):** this month's credit left against the
  account's monthly limit, in the chat page's usage-meter format
  (`GET /v2/users/me/limits`, checked at most every 10 minutes), with a
  warning from 80%: scheduled runs stop when the credit runs out. The header
  chip shows Apify and its spend while Apify is on.
- **Master vs tailored (Resume Studio):** when Luna tailors a resume, the
  tailored resume is scored against the job with the same prompt as the master
  (`analysis.score_text`), shown as "Master 68 → Tailored 84 (+16)". After
  edits the score is marked as older than the text; **Score again** re-scores
  in the background.
- **Follow-ups (daily digest):** applications with no news for 7 days
  (Applied, Screening, Interviewing) get their own section at the top.
- **Logistics** can be hidden under Settings → Jobs page.

## Pipeline

- **Source tabs:** All · Indeed · Manual, with counts.
- **Board:** one column per stage: New, Shortlisted, Resume, Ready to apply,
  Applied, Interviewing, Offer, Closed. Cards show the company, place,
  salary, workplace and type, the match ring, where the job came from, and
  the next step for the stage (Tailor resume, Review resume, Apply, …).
- **Drag a card** to another column: Shortlisted, Resume (tailors it),
  Ready to apply (from a tailored resume), Applied (asks first), Interviewing,
  Offer, or Closed (pick Rejected, No response, Withdrawn or Skipped). Columns
  a card can't go to fade while it is dragged; the board scrolls at its edges.
- **Move to…** on a card lists only the stages its lifecycle allows
  (`applications.moves_for`). *Applied* records an application from any stage
  before it, with or without a tailored resume.
- **List:** the same jobs sorted by newest or best match; the side-panel stage
  filters open it.
- Clicking a card opens a drawer with the details, the score, the
  description, actions, and **Notes & activity** (notes and stage changes).
- The tab and layout are remembered per browser.

## Match score

Luna (Settings → AI) reads the job description against the master resume and
returns a 0–100 fit score with the matches and gaps. The ring is coloured by
band: **75–100 Good match** (green), **50–74 Needs improvement** (yellow),
**0–49 Terrible match** (red), with the percentage in the centre. Resume
Studio's **Match check** steps through the jobs on the board one at a time,
in board order (New, Shortlisted, Resume, Ready to apply): Previous/Next or
the arrow keys, then **Tailor & next**. **Score my resume** costs one model
call. Scout finds are scored automatically when *Analyse new finds
automatically* is on.

**Automate all** does the same for every job in the match check not yet
tailored: jobs already scored 50% or more are tailored now, unscored ones are
scored first and tailored if they reach 50% (`autopilot.py`, table
`auto_tailor`). Nothing is sent; you review and apply.

## Tailoring in your resume's own design

The master resume's design is read once from the uploaded PDF or DOCX
(`resume_style.py`): page size and margins, font, and the size, colour and
weight of the name, headline, contact line, section headings (and their
rules), entry lines and body, plus the bullet mark. Resume Studio shows a
thumbnail of the uploaded file; click it for a full preview, click again or
press Esc to close.

Luna gets the master as Markdown and keeps its layout: the same header lines,
the same section headings in the same order, the same "Title | Company |
Place | Dates" entry lines and bullets. Only the wording and the selection
change. The PDF and DOCX exports draw that Markdown in the master's design,
and **Preview** shows it. A pasted resume uses a neutral design.

The tailoring prompt follows the resume-tailoring skill
(github.com/amanattar/resume-tailoring-skill, MIT): a success profile of the
role, every bullet matched as direct, transferable or adjacent, truthful
rewording (the posting's terms for the same thing, never a higher title), and
gaps left out and reported. Resume Studio shows that report beside the
tailored resume, with questions that may surface experience you have not
listed yet. The skill itself is also installed for chat use under
`productivity/resume-tailoring` in the Hermes profile.

## Applying: the Apply kit

Hermes does not submit applications. Indeed's and LinkedIn's terms forbid
automated applying, and it would mean handing your session to a third party
(the one Apify actor that tries, for LinkedIn Easy Apply, had 16 users and
no reviews on 2026-10-08). Instead each job not yet applied for has an
**Apply kit** in its side panel:

1. **Documents:** the tailored resume (DOCX/PDF) and cover letter, or a
   prompt to tailor one.
2. **Screening answers:** Luna writes ready-to-paste answers to the usual
   questions (why this role and company, experience, matching skills, notice
   period, salary, work authorisation, relocation, languages) from the job,
   your master resume and **Settings → Application answers**, which it uses
   word for word. A question you left blank comes back as "Not provided —
   fill in before sending", highlighted. Each answer has a Copy button.
3. **Apply on the site:** Open posting, paste, send, then **I've applied**.

Answers are stored per job (`apply_kits`); preparing them is one model call.
