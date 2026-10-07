# Job OS email: alerts, digest, reply-to-proceed

Jobs sends email from the connected Gmail (Jobs → Settings → Connections) as
**Hermes Jobs**, to **Send to** under Settings → Notifications. Nothing is sent
unless **Email me** is on and a Send-to address is set.

| What | When |
|---|---|
| New-match alert | After Luna finishes analysing, for jobs at or above *Minimum fit score* (analysed in the last 3 days, still in *Analyzed*). Each job is alerted once; at most 10 per email. |
| Daily digest | Once a day at or after *Digest hour* (server local time): jobs found in the last 24 hours, best new matches, ready-to-apply jobs, and everything needing attention. Skipped when there is nothing to report. |
| Reply confirmation | After Hermes acts on your reply. |

## Replying to proceed

Each job in an alert lists codes such as `TAILOR 1A2B3C4D` and `SKIP 9F8E7D6C`.
Reply to the alert with one or more codes, each on its own line. Hermes checks
the sending account's inbox every two minutes (or on **Check replies now**).

A reply is acted on only if:

- it is newer than the first check (old mail is never read as commands),
- it comes from the Send-to address and Gmail's own `Authentication-Results`
  header reports `dmarc=pass`,
- the code is in your own text, not in quoted lines,
- the code is unused, unexpired (7 days), and matches the action.

Anything else is ignored and shown as *rejected* in the Notifications log.
Codes are stored only as SHA-256 hashes.

State: `webui_state/job_os/notify.json` (last digest date, inbox position) and
the `reply_codes` / `email_log` tables in `job_os.db`.
