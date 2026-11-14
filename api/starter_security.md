# Security checklist

<!-- hermes:security:begin -->
Run this before calling any task in this project finished. It is the security
side of the SaaS web app checklist; `docs/PERFORMANCE.md` covers speed. It
applies whenever a change touches something on the list (a new page, form,
endpoint, table, upload, login or session, dependency, environment variable
or deploy setting).

## How to use it

- **Applicable items are required.** If an item fits the project and the
  change, do it.
- **Skip items that don't fit.** For example, there is no database, no login,
  no file upload or no public URL yet. Give a short reason for each skip.
- **Check what already exists first.** Many items may already be in place
  (the framework often provides them). Verify them instead of re-adding them.
- **Prove it.** Where you can, show it working: a request without a session
  is refused, another user's record returns 403 or 404, a script tag in user
  text shows as text, the headers appear in the response.
- **Dependencies:**
  - Install a library only when an item really needs one and the project
    allows it.
  - This project's own rules win (AGENTS.md, CONTRIBUTING.md, "no new
    dependencies" policies). If they forbid it, use a built-in or hand-rolled
    approach, or skip the item and say why.
  - Ask before adding paid or externally visible services, such as a bot
    protection provider, a secrets manager or a scanning service.
- **Never print a secret.** Don't write keys, tokens, cookies or password
  hashes into chat, logs, commits or docs.
- **Report at the end.** In the final summary, add a short "Security
  checklist" note covering:
  - what was applied
  - what was already in place
  - what was skipped, and why

## Checklist

### Secrets and keys

- [ ] Hide API keys: keep them in server-side environment variables, never in client code, the repository or a public bundle.
- [ ] Purge Git secrets: scan the history for committed keys and `.env` files, remove them, and rotate anything that was ever exposed.
- [ ] Use the public DB key in the browser: ship only the public (anon or publishable) key to the client, and keep the service-role or admin key on the server.

### Data and access

- [ ] Enable row-level security on every table that holds user data, with a policy for each action.
- [ ] Encrypt sensitive data at rest (and in backups), and keep the keys out of the database.
- [ ] Enforce server-side auth: check the session or token on the server for every protected route and action, never only in the UI.
- [ ] Lock record access: a user can read and change only their own records (or their team's); check ownership on every read, update and delete by id.
- [ ] Block field tampering: accept only the fields each endpoint expects, and set roles, prices, owners and status on the server, never from the request body.

### Accounts and sessions

- [ ] Secure session cookies: `HttpOnly`, `Secure` and `SameSite`, with a sensible expiry and rotation on login.
- [ ] Hash passwords with a slow, salted algorithm (argon2, bcrypt or scrypt), never plain text or a fast hash.
- [ ] Rate limit login, password reset and other sign-up and token endpoints, per account and per address.
- [ ] Add bot protection to sign-up, login and public forms (a CAPTCHA or challenge).

### Input and output

- [ ] Parameterize queries: never build SQL or other query strings by joining user text.
- [ ] Validate all inputs on the server: type, length, format and range, with an allow-list where possible.
- [ ] Escape user content when it is shown (prevent XSS), and avoid raw HTML injection.
- [ ] Restrict file uploads: allowed types and size, content checks, random names, stored outside the web root or in private storage, served with the right content type.
- [ ] Trim API responses to the fields the client needs (no password hashes, tokens, internal ids or other users' data).

### Transport and supply chain

- [ ] Add security headers: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy` and frame protection (`frame-ancestors`).
- [ ] Force HTTPS: redirect all HTTP traffic and set HSTS.
- [ ] Scan dependencies for known vulnerabilities (`npm audit`, `pip-audit` or the project's equivalent) and update what is flagged.
<!-- hermes:security:end -->
