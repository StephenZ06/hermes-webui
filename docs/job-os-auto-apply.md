# Job OS gated auto-apply

Off by default: Jobs → Settings → Auto-apply. When on, Hermes can fill and
submit **Greenhouse, Lever and Ashby** application forms for you, under these
gates (all must pass, every run):

- the ATS is in *Allowed application systems*;
- the job is **Application ready** — you approved its tailored resume;
- its fit score is at or above the auto-apply minimum;
- your name and email are filled in under *Your details*;
- for a real submission, today's count is under *Daily limit*.

## Flow

1. **Preview (dry run).** Hermes opens the form in a headless browser, fills
   what it recognises (name, email, phone, location, LinkedIn, website, the
   tailored resume and cover letter as PDFs), takes a full-page screenshot,
   and does **not** submit. The job moves to *Awaiting approval* and shows the
   screenshot on the Applications board. With email on, you also get a
   *Ready to send* email with an `APPLY` code.
2. **Approve.** *Send application* on the board (or replying `APPLY <code>`)
   fills the form again and presses submit. A confirmation page moves the
   job to *Submitted* (recorded as an automatic application). Anything else
   returns it to *Application ready* with the reason under *Needs attention*.
3. **Dry run first.** While this is on, each ATS gets previews until you have
   approved one confirmed submission there. After that, scheduled runs on that
   ATS submit directly (still under every gate above).

The scheduler starts at most one run at a time, only for jobs that have never
had a run; a job that stopped is never retried automatically — use *Auto-fill*
on its card after fixing the cause.

## What stops a run

- a visible captcha (before or after submit);
- any salary, sponsorship/visa/work-authorisation, legal, background-check or
  consent/privacy question — required or not;
- a required question Hermes can't answer, or a required personal (EEO)
  question;
- no confirmation within 25 seconds of pressing submit.

Optional unknown questions and optional EEO questions are left blank.
Screenshots are kept in `webui_state/job_os/applications/<job id>/`.

## Browser

Runs happen in a separate process with a 4-minute limit. The interpreter is
`HERMES_JOB_OS_BROWSER_PYTHON` if set, else the server's own Python when it has
Playwright, else the repository `.venv` (which `scripts/test.sh` creates with
Playwright and Chromium). Without any, runs stop with "Browser automation isn't
installed".
