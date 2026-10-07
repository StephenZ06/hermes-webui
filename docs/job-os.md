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

1. **Scout (automated).** A search names job titles or keywords, the Indeed
   country, optional cities, a date-posted window and *remote only*. Each run
   reads the country's Indeed results and saves every new posting with its
   description, salary, employment type and country (source `indeed`). See
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
is one run of an Apify actor (default `valig/indeed-jobs-scraper`) on Apify's
own addresses; it returns finished postings, description included, and Scout
saves them like any other find (same duplicate, blocked-company and remote
checks; same `/viewjob?jk=` identity). Firecrawl is not needed for these runs.

- **Token:** paste it under Settings → Apify. Hermes checks it with Apify
  (`GET /v2/users/me`), then saves it as `APIFY_API_TOKEN` in the env files
  (the shared secrets file when enabled). It is sent to Apify in a header,
  never in a URL, and never returned to the browser (only "connected" and its
  last four characters).
- **Settings:** the actor (`owner/name`) and **Results per city** (1–1000),
  which caps the cost.
- **Cost (valig, free plan):** $0.001 per run + $0.10 per 1,000 jobs; the free
  plan includes $5 a month. Apify counts repeats of jobs you already have.
- **Failures:** one city failing keeps the others; every city failing fails
  the run with Apify's reason (refused token, out of credit, no answer).
- **More sites:** `apify.SITES` maps a site to its default actor; LinkedIn
  and JobStreet actors can be added with their own record mapping.

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
