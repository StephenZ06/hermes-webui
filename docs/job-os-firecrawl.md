# Job OS: self-hosted Firecrawl

The Jobs page (Job OS) discovers and reads Indeed postings through a
self-hosted [Firecrawl](https://github.com/firecrawl/firecrawl). This page is
how it is set up next to a native Hermes WebUI on WSL2.

## Where it runs

On the **WSL Docker engine** (the same engine as other Hermes containers).
Docker Desktop's engine runs inside the same WSL2 VM and shares the same
`.wslconfig` CPU/RAM limits, so moving Firecrawl there saves nothing.

The API listens on **`127.0.0.1:3002` only**. WSL mirrored networking would
otherwise expose a `0.0.0.0` port on the LAN and Tailscale, and the
self-hosted API has no authentication by default.

## Setup

```bash
git clone --depth 1 https://github.com/firecrawl/firecrawl.git ~/firecrawl
```

The WSL engine may lack the Compose plugin; install it per user (no sudo)
from Docker's releases and verify the published SHA-256 before use:

```bash
mkdir -p ~/.docker/cli-plugins
# download docker-compose-linux-x86_64 and its .sha256 from
# https://github.com/docker/compose/releases into ~/.docker/cli-plugins/,
# check it with `sha256sum -c`, rename it to docker-compose, chmod +x
```

Create `~/firecrawl/hermes-searxng/settings.yml` (chmod 600) with a random
`secret_key` (`python3 -c "import secrets;print(secrets.token_hex(32))"`):

```yaml
use_default_settings: true
server:
  secret_key: "<random hex>"
  limiter: false
  image_proxy: false
search:
  formats: [html, json]
```

Then add `~/firecrawl/docker-compose.override.yaml`; Compose merges it with
the upstream file automatically:

```yaml
# Hermes local overrides (not part of upstream Firecrawl).
# - prebuilt images instead of building from source
# - whole stack capped at ~3.8 GB RAM / ~2.6 CPUs (limits; real use is lower)
# - API on 127.0.0.1 only (WSL mirrored networking would otherwise expose it
#   on the LAN / Tailscale)
# - fewer workers; FoundationDB (experimental) disabled; SearXNG for /search
x-hermes-env: &hermes-env
  NUQ_WORKER_COUNT: "1"
  NUM_WORKERS_PER_QUEUE: "2"
  MAX_CONCURRENT_JOBS: "2"
  BROWSER_POOL_SIZE: "2"
  CRAWL_CONCURRENT_REQUESTS: "3"
  SEARXNG_ENDPOINT: http://searxng:8080
  LOGGING_LEVEL: warn
  # Six Node processes boot inside the CPU-capped api container; give the
  # harness longer than its 60s default before it declares the API dead.
  HARNESS_STARTUP_TIMEOUT_MS: "240000"

services:
  api:
    image: ghcr.io/firecrawl/firecrawl:latest
    build: !reset null
    pull_policy: missing
    environment: *hermes-env
    ports: !override
      - "127.0.0.1:3002:3002"
    # The harness runs the API plus ~5 worker processes in this container.
    cpus: 1.5
    mem_limit: 2048M
    memswap_limit: 2048M
    restart: unless-stopped

  playwright-service:
    image: ghcr.io/firecrawl/playwright-service:latest
    build: !reset null
    pull_policy: missing
    environment:
      MAX_CONCURRENT_PAGES: "3"
      BLOCK_MEDIA: "true"
    cpus: 0.6
    mem_limit: 768M
    memswap_limit: 768M
    restart: unless-stopped

  nuq-postgres:
    image: ghcr.io/firecrawl/nuq-postgres:latest
    build: !reset null
    pull_policy: missing
    cpus: 0.2
    mem_limit: 256M
    restart: unless-stopped

  redis:
    cpus: 0.1
    mem_limit: 128M
    restart: unless-stopped

  rabbitmq:
    # Plain image (no management UI) and a longer start window: under the CPU
    # cap the broker needs more than upstream's 5s start_period to boot.
    image: rabbitmq:3
    cpus: 0.5
    mem_limit: 400M
    healthcheck:
      # Each check boots an Erlang VM (~0.5 CPU for a few seconds); check
      # every 5s while starting, then every 60s.
      start_period: 60s
      start_interval: 5s
      interval: 60s
      timeout: 5s
      retries: 12
    restart: unless-stopped

  searxng:
    image: searxng/searxng:latest
    networks:
      - backend
    volumes:
      - ./hermes-searxng/settings.yml:/etc/searxng/settings.yml:ro
    cpus: 0.2
    mem_limit: 256M
    restart: unless-stopped

  foundationdb:
    profiles: ["fdb"]
  foundationdb-init:
    profiles: ["fdb"]
```

Start it:

```bash
cd ~/firecrawl && docker compose pull && docker compose up -d
```

## What the override changes, and why

| Change | Reason |
| --- | --- |
| Prebuilt `ghcr.io/firecrawl/*` images (`build: !reset null`) | No local source build |
| API bound to `127.0.0.1:3002` | Not reachable from the LAN or Tailscale |
| `NUQ_WORKER_COUNT=1`, `NUM_WORKERS_PER_QUEUE=2`, fewer browser pages | The API container runs the API plus ~5 worker processes; upstream defaults need several GB |
| API capped at 2 GB / 1.5 CPU, other services smaller | Whole stack limited to about 3.8 GB / 2.6 CPU (typical use ~2.3 GB, a few % CPU idle) |
| `HARNESS_STARTUP_TIMEOUT_MS=240000` | Six Node processes boot slowly under the CPU cap; the 60 s default restarts the API in a loop |
| RabbitMQ: plain image, 60 s start window, health check every 60 s once up | Each check boots an Erlang VM (~0.5 CPU for a few seconds); the upstream 5 s check kept it busy |
| FoundationDB services moved to an `fdb` profile | Experimental; not started by default |
| SearXNG container, `SEARXNG_ENDPOINT` | Reliable keyword search for Scout |

## Pointing Hermes at it

Set `FIRECRAWL_API_URL=http://localhost:3002` in the profile `.env` files.
(`host.docker.internal` only resolves inside Docker containers; the native
WebUI and agent cannot reach it.) **Jobs → Settings → Connections** shows
the live state (*Firecrawl ready / offline / incompatible / not set up*) and
accepts a per-profile URL override; the header chip on every Jobs page shows
the same state.

Health is read from `GET /` (`{"message": "Firecrawl API"}`) and
`GET /v0/health/readiness`.

## How Scout finds and reads postings

Scout searches **Indeed only** (`indeed.py`, `scout.py`):

- **Country and cities.** Indeed runs a separate site per country
  (`malaysia.indeed.com`, `sg.indeed.com`, `www.indeed.com`, …). A saved
  search names its country and, optionally, cities; each city is searched on
  that country's site: `https://<host>/jobs?q=<keywords>&l=<city>`, with
  `fromage=<days>` when the search limits the date posted. The quota is
  shared across cities.
- **Results pages.** Scout reads up to 3 results pages per city (Indeed shows
  about 10 postings a page) and stops at a short or repeated page.
- **Postings.** Indeed serves a posting to an automated reader only through
  its click link (`/rc/clk?jk=…`), not `/viewjob?jk=…`, and refuses
  back-to-back requests, so Indeed pages are read 5 seconds apart. A posting
  is parsed from its schema.org `JobPosting` JSON-LD (`extract.py`) and saved
  as `https://<host>/viewjob?jk=<key>`; the key is what makes two Indeed
  postings different jobs. Postings Indeed no longer lists count as *closed*.
- **Blocks.** After a burst, Indeed refuses every request for several
  minutes. Four refused postings in a row end the run early ("Indeed is
  refusing requests right now"); the search's last-run time is still set, so
  the schedule waits its interval before trying again.
- **Fallback search.** If Indeed refuses a results page, Scout asks a web
  search for that Indeed site instead: the **Brave Search API** when
  `BRAVE_SEARCH_API_KEY` is set (paced to 1 request/second), otherwise
  Firecrawl's `/search` (SearXNG, which its upstream engines rate-limit after
  a burst). Links to any other site, or another country's Indeed, are
  skipped.
- **Other job sites.** LinkedIn and JobStreet refuse the self-hosted Firecrawl
  outright, so they are not searched. Track jobs from them with **Add job**.
- **Runs** are saved after every page (`scout.py`), can be cancelled between
  pages, and a WebUI restart mid-run leaves them *interrupted*.
- **Schedule:** Jobs → Settings → Scout schedule runs enabled searches every
  N hours from inside the WebUI (`scheduler.py`); no AI tokens are used.

## Gmail (notifications)

Connect it in **Jobs → Settings → Connections**: Hermes checks the address
and app password with a real Gmail login, then saves them as
`HERMES_GMAIL_ADDRESS` / `HERMES_GMAIL_APP_PASSWORD` (in the shared secrets
file when enabled, see `docs/shared-secrets.md`). One Gmail sends for every
Hermes feature, each under its own name (`api/mailer.py`): *Hermes Jobs*,
*Hermes Business*. A dedicated Gmail for Hermes works best; put your main
address in Jobs → Settings → Notifications → *Send to*. The older
`JOB_OS_GMAIL_*` names are still read.

## Operating it

```bash
cd ~/firecrawl
docker compose ps                     # status
docker compose stop                   # free the RAM when not job hunting
docker compose up -d                  # start again
docker stats --no-stream | grep firecrawl
```
