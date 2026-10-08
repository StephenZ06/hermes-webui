# Jobs (Job OS)

The **Jobs** page is a profile-scoped job-search tracker. Its data lives in
`webui_state/job_os/job_os.db` for the active profile.

| Section | What it does |
|---|---|
| **Dashboard** | Counts, automations beside the funnel and its activity calendars, recent jobs (ten a page), and **Add job**. |
| **Scout** | Saved Indeed searches; runs find postings and add them to the Pipeline. |
| **Pipeline** | Every job, from new find to offer: a board or a list. |
| **Resume Studio** | The master resume, its match score against a job, and tailored versions. |
| **Logistics** | A 3D view of the same jobs. |
| **Settings** | A side menu of sections, one shown at a time: Connections (Firecrawl, Gmail), Apify, Scout schedule, Luna (AI), Notifications, your details, application answers, the Jobs page. |

## Two ways in

1. **Scout (automated).** A search names job titles or keywords, the country,
   optional cities, a date-posted window, *remote only*, and its **job sites**:
   Indeed, LinkedIn and Bayt (the last two need Apify; Bayt covers the Gulf
   and a few other markets, and is greyed out elsewhere).
   Job titles are comma-separated and each is searched on its own (up to 5).
   **Only keep matching titles** (on by default) keeps a posting only when its
   title carries every distinctive word of one of the search's job titles, or
   of a **related title** (`api/job_os/relevance.py`): for "IT Analyst" a
   "Sales Executive" or a "Business Analyst" is dropped, "Lead IT Business
   Analyst" and "ICT Analyst" are kept. Seniority words (senior, lead, L2,
   intern) don't count, and a word matches its usual equivalents ("security"
   in "cybersecurity", "SOC" as "security operations"). Luna suggests the
   related titles once, on the search's first run or when the Scout page
   loads (**Suggest** in the form asks again); you can edit them. Finds saved
   before a search turned strict show on its card as off-target, with
   **Move to Closed** (they can be dragged back).
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

### remote.id (remotefreelance.id)

An Indonesian board of remote jobs gathered from JobStreet, LinkedIn, SEEK and
Upwork. It has no Apify scraper, so Scout reads it directly (`remoteid.py`),
with or without Apify and without Firecrawl:

- `https://remotefreelance.id/jobs?q=<title>&page=<n>` per job title (up to 3
  pages), then each job page, one a second. robots.txt allows `/jobs`; nothing
  else is read (the reader refuses other hosts and paths).
- Each find is labelled **remote.id** and saved under its source site's own
  link (`id.jobstreet.com/job/<id>`, `linkedin.com/jobs/view/<id>`,
  `upwork.com/jobs/~<id>`, SEEK's job link), so a LinkedIn job a LinkedIn
  search already found is skipped as known (and the other way round).
  Upwork gigs are kept (company "Upwork client" when the page names none).
- The search's country is not applied (every job is remote); its titles,
  title filter, related titles and date window are. Pay, type, place and the
  posted date (Indonesian month names) come from the job page.
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

- **Source tabs:** All, each job site, Manual, with counts. The board is
  loaded once and the tabs filter it in the page, so switching is instant.
- **Search** (beside the layout switch, or press `/`): narrows the board or
  the list to jobs whose title, company or place contain every word typed;
  Esc clears it.
- **Board:** one column per stage: New (grey), Favorite (purple), Ready to
  apply, Applied, Rejected (red), Interview (green), Offer, Closed. Cards
  show the company, place, salary, workplace and type, the match ring, where
  the job came from, and the next step for the stage (Tailor resume, Review
  resume, Apply, …). A job moves to Ready to apply as soon as Luna starts
  tailoring for it (Tailor resume on a card or Tailor & next in Resume
  Studio), showing *Tailoring* until the resume is ready; a failed tailoring
  puts it back in Favorite.
- **Drag a card** to any other column, back as well as forward
  (`applications.move_to_column`, `POST /api/job-os/jobs/{id}/move`): the job
  gets the status the column means for it (back to New is *analysed* or
  *scraped*; Ready to apply is *resume ready* when a tailored resume exists;
  Closed is *skipped* before applying and asks *no response* or *withdrawn*
  after). Applied asks first and records the application once. Only a job
  Luna is tailoring can't be moved. While a card is held, refreshes leave the
  board alone; the board scrolls at its edges.
- **Fold a column** (the arrow in its header, on hover) to a slim strip with
  its name and count, as in most Kanban boards; it still takes drops, and
  folded columns are remembered per browser. While a card is held over a
  column, a card-sized slot shows at the top where it will land.
- **Scrolling sideways:** a scrollbar pinned to the bottom of the view, or
  press on empty board space and drag left or right.
- **Cards** are compact and all one height: the title (two lines kept),
  company and site, place and when, pay and job type side by side (*N/A*
  when the posting doesn't say; pay shortened, e.g. "/mo"), and one
  full-width capitalised button in its column's colour (*Open job* where
  there is no next step). A follow-up note is a warning icon by the time
  (hover for the text). Columns have a 2px outline in their colour. A
  column shows ten cards, then scrolls; its thin scrollbar shows only while
  scrolling.
- **List:** the same jobs sorted by newest or best match; the dashboard's
  *Active work* and *Applied* tiles open it.
- **Side panel stages:** every board column with its colour and count; a stage
  opens the board scrolled to that column (unfolded), which flashes once.
- The board sits on the page background and never selects card text while
  panning or dragging. **Add job** on the toolbar is an icon button.
- Clicking a card opens a drawer with the details, the score, the
  description, actions, and **Notes & activity** (notes and stage changes).
- The tab and layout are remembered per browser.

## Employer replies (Settings → Notifications)

With Gmail connected and **Read employer replies** on, Luna reads new mail in
the connected inbox every 10 minutes (`api/job_os/outcomes.py`; read-only,
nothing is marked or changed; the first check only notes where the inbox is,
so older mail is never acted on). Mail that talks about an application goes
to Luna with the list of jobs you applied for; when it is clearly about one of
them (company and role) and says **no**, the job moves to **Rejected**; when
it asks you to go further (an interview, an assessment, details to proceed),
it moves to **Interview**. Acknowledgements, alerts and unsure answers move
nothing. The job's activity shows the move with the email's subject, and a
wrong move can be dragged back. **Check now** reads the inbox at once.

Employers write to the address you applied with. When that is not the
connected Gmail, forward job replies to it with a Gmail filter (Settings →
Forwarding, then a filter such as `subject:(application OR interview OR
candidate)` → Forward to).

## Feedback and small interactions

Shared helpers in `static/micro.js` (ideas from transitions.dev,
designspells.com, ObsidianUI and Rare UI, rebuilt in plain CSS/JS):
- Tabs and side menus slide a pill to the active item.
- Save, connect, test, send and run buttons show a spinner, then a drawn
  tick; a failure restores the button and shakes it, and invalid fields are
  outlined until edited.
- Luna and Scout's busy states share one shimmering "working" line that
  steps through what is happening.
- The Automations card is two columns of tiles; each tile's last 14 days run
  its full width as ticks (green ran, red failed, amber both, grey nothing).
- Deleting a saved search asks in place: the bin becomes *Delete search?* and a
  second click deletes; it settles back after 3 seconds or a click elsewhere.
  The card fades out and the cards after it slide into its place. On a search
  card, **Run now** fills the row and Edit and Delete are icons on the right.
- A view still loading shows the app's loading bar, not text.
- Cards on every Jobs page are 16px apart (12px on a phone).

## On a phone

Below 768px wide the Jobs page is laid out like a native app: the sections
sit in a tab bar along the bottom of the screen (safe-area aware); the page
title is large with its description and status under it; the Pipeline board
shows one column a screen and swipes sideways, snapping into place, with the
source tabs scrolling in their own row and layout, search and Add job sharing
the next; the dashboard's activity calendars swipe sideways; job rows read like
list cells (status top-right, chips wrapping across); the Settings menu sticks
to the top; Match check's actions sit two to a row. Nothing scrolls the page
sideways. A job's details and the Add job form open as full-screen sheets.
- `?` opens the keyboard shortcuts, now with a Jobs group.

## Dashboard activity

Under **Your funnel**, three month calendars on your clock (Scout schedule
time zone): **Jobs found** (shade by how many), **Applications** (with your
current streak of days in a row) and **Replies** (green interview, red
rejection). The arrows step back up to five months.

## Match score

Luna (Settings → AI) reads the job description against the master resume and
returns a 0–100 fit score with the matches and gaps. The ring is coloured by
band: **75–100 Good match** (green), **50–74 Needs improvement** (yellow),
**0–49 Terrible match** (red), with the percentage in the centre. Resume
Studio's **Match check** steps through the jobs on the board one at a time,
in board order (New, Favorite, Ready to apply): Previous/Next or
the arrow keys, then **Tailor & next**; the actions sit centred along the
bottom of the card. **Score my resume** costs one model call. Scout finds are scored automatically when *Analyse new finds
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
