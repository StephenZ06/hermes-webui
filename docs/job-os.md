# Jobs (Job OS)

The **Jobs** page is a profile-scoped job-search tracker. Its data lives in
`webui_state/job_os/job_os.db` for the active profile.

| Section | What it does |
|---|---|
| **Dashboard** | Counts, the funnel, automations, recent jobs, and **Add job**. |
| **Scout** | Saved Indeed searches; runs find postings and add them to the Pipeline. |
| **Pipeline** | Every job, from new find to offer: a board or a list. |
| **Resume Studio** | The master resume, its match score against a job, and tailored versions. |
| **Logistics** | A 3D view of the same jobs. |
| **Settings** | Connections (Firecrawl, Gmail), AI, your details, Scout schedule, notifications. |

## Two ways in

1. **Scout (automated).** A search names job titles or keywords, the country,
   optional cities, a date-posted window, *remote only*, and its **job sites**:
   Indeed, LinkedIn and JobStreet (JobStreet covers Malaysia, Singapore,
   Indonesia and the Philippines). LinkedIn and JobStreet need Apify. Each run
   reads the country's Indeed results and saves every new posting with its
   description, salary, employment type and country (source `indeed`,
   `linkedin` or `jobstreet`; one role found on two sites is saved once). See
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

| Site | Default actor | Cost (free plan) | Notes |
|---|---|---|---|
| Indeed | `valig/indeed-jobs-scraper` | $0.001 a run + $0.10 per 1,000 jobs | country site per search |
| LinkedIn | `valig/linkedin-jobs-scraper` | $0.001 a run + $0.40 per 1,000 jobs | country goes into the location; date filter 1/7/30 days, Scout drops older posts |
| JobStreet | `blackfalcondata/jobstreet-scraper` | $0.01 a run + $2.00 per 1,000 jobs | MY, SG, ID, PH; sorted by date |

  The free plan includes $5 a month. Apify counts repeats of jobs you
  already have. Checked on 2026-10-07 for "data analyst", Kuala Lumpur, 7
  days: LinkedIn 10/10 records with full descriptions (no salary or work
  arrangement given); JobStreet 10/10 with descriptions, 6 with salary.
- **Failures:** one city failing keeps the others; every city failing fails
  the run with Apify's reason (refused token, out of credit, no answer).
- **More sites:** `apify.SITES` maps a site to its default actor, with an
  input builder and a record mapping per site.

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

Pay only for new jobs: JobStreet runs in the actor's incremental mode (one
memory per search and city), and LinkedIn is given the jobs Scout already has
to leave out. Indeed has no such option but costs $0.10 per 1,000 jobs.

## Pipeline

- **Source tabs:** All · Indeed · Manual, with counts.
- **Board:** one column per stage: New, Shortlisted, Resume, Ready to apply,
  Applied, Interviewing, Offer, Closed. Cards show the company, place,
  salary, workplace and type, the match ring, where the job came from, and
  the next step for the stage (Tailor resume, Review resume, Apply, …).
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
Studio's **Match check** shows it for any job with a description; **Score my
resume** costs one model call. Scout finds are scored automatically when
*Analyse new finds automatically* is on.

## Applying

You apply on the job's own site (**Apply** opens the posting) and record it
here. Automated applying was removed: Indeed's own application flow needs a
signed-in account and its terms forbid automation.
