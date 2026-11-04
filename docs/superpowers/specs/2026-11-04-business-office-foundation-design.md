# Business Office foundation design

Implements steps 1 to 5 of `office/Business Office Multi-Agent Implementation
Plan.md`: businesses, provider registry, tasks, approvals, audit, scoped
Obsidian access, Google and Meta sign-in, and the task runtime. Later phases
(Calendar, CRM, publishing, newsletters, analytics, ERPNext) are not built.

## Services and boundaries

Everything runs inside the WebUI process. No new service or dependency:
`cryptography` was already required and HTTP uses `urllib`. Hermes Agent is
not changed. The Projects Office has no path into `api/business_office/`.

| Module | Owns |
| --- | --- |
| `store.py` | All rows in `STATE_DIR/business_office.db` (0600) |
| `crypto.py` | AES-256-GCM for tokens and app secrets |
| `registry.py` | Providers, capabilities, risk, default modes, input checks |
| `oauth.py` | Sign-in, token exchange, refresh, disconnect |
| `service.py` | The only route to an adapter: every rule, rechecked per call |
| `runtime.py` | Durable queue, limits, retries, recovery, schedules |
| `http.py` | `/api/office/business/*`, public fields only |
| `adapters/` | Gmail, Threads and Instagram identity, Obsidian |

## Contracts

- Business and agent come from the task row, never from provider input.
  `registry.validate_input` refuses unknown keys, so a payload cannot name one.
- External writes can never be `automatic`: `allowed_modes` omits it, and a
  forced database row resolves to `disabled`.
- An approval binds to its task, capability and a hash of the exact content.
  For a Gmail send the content is the draft as fetched, so editing a draft after
  approval makes the approval `stale`. Approvals are single use and expire.
- A provider error during an approved write is `uncertain` unless the provider
  clearly refused. Uncertain actions are never retried and are flagged for review.
- A vault grant stores the vault path and folder. Each operation also needs that
  agent's own flag. A different vault matches no grant.
- The OAuth `state` is random, single use, expires in ten minutes, and is bound to
  the WebUI session. The business comes from that stored row.
- Provider HTTP goes only to an allow-list of https hosts.

## Data and migrations

New database only; created with `CREATE TABLE IF NOT EXISTS`. Three businesses
are seeded once. Vault files are never moved. The key is
`HERMES_BUSINESS_OFFICE_KEY` when set, otherwise `STATE_DIR/business_office.key`.

## Failure modes

| Failure | Result |
| --- | --- |
| Sign-in expired or revoked | Connection shows Sign in again; tasks fail visibly |
| Rate limit, timeout, outage on a read | Retried with backoff and jitter |
| Same on a write | Task fails, no retry |
| Restart mid-read | Requeued |
| Restart mid-write | Failed and flagged for review |
| Concurrent note edit | `conflict`, nothing written |
| Note differs after writing | `uncertain`, surfaced for review |
| Key lost or changed | Secrets fail to decrypt; connection needs signing in again |

Note edits compare a hash of the file's bytes, then replace atomically. A writer
landing between the final check and the replace is not prevented; the re-read
after writing reports that case as uncertain.

## Observability

The `audit` table records actor, agent, task, provider, capability, target,
decision and outcome, with `detail` passed through redaction. Payloads are not
copied into it. It is independent of chat sessions, unlike `api/audit_trail.py`.

## Authorization and known limits

`/api/office/business/*` uses the WebUI's normal auth and CSRF checks.

- The approval gate binds code paths, not everything on the machine. A process
  that can read the WebUI state and key can use the tokens directly. The
  `hermes-migrated` agent container mounts the Docker socket, so it can reach the
  WebUI container that way.
- Language-model agents do not call these tools yet. With the gateway chat
  backend, agents run in another container and WebUI-registered tools do not reach
  them. Today tasks start from the Integrations page and schedules. A bridge needs
  a per-task credential so that the server, not the model, names the business.
- `api/mailer.py` remains a separate app-password sender for other features.
- Threads and Instagram are sign-in and profile read only.
- Gmail labelling is not included; it would need the `gmail.modify` scope.

## Rollout and rollback

Ship with the normal redeploy. Rollback is reverting the commit. The database and
key file can stay; removing them forgets all connections, grants and history.

## Testing

`tests/test_business_office.py` covers isolation, approvals, OAuth, vault scope
and runtime with the network replaced at `http_client.request_json`.
`tests/test_business_office_browser.py` drives the page. Real Google and Meta
behaviour is unverified until the owner signs in.
