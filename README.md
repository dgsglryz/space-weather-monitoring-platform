# Space Weather Monitoring Platform

Mission-ready weather intelligence for satellite ground stations. The platform ingests conditions from OpenWeatherMap, evaluates operator-defined thresholds, and surfaces status through a server-rendered dashboard, authenticated REST API, and optional email/WebSocket alerts.

---

## Repository & Contacts

- GitHub (private): https://github.com/dgsglryz/space-weather-monitoring-platform
- Delivery branch: `delivery`
- Reviewer access: add `perceptivespace` as collaborator on request
- Questions / submission email: hiring@perceptivespace.com

---

## Demo Access

- URL: https://space-weather-monitoring-demo.fly.dev
- Credentials: `demo@example.com` / `SolarStorm42!`
- Seeded data: Cape Canaveral, Vandenberg SFB, Baikonur with recent telemetry and alert history
- Admin login (optional): request via email, or create locally with `createsuperuser`

> Submission checklist reminder:
> 1. Share deployed URL and credentials above
> 2. Include private GitHub link
> 3. Document setup notes (env vars, external services)
> 4. State time spent (see **Time & Next Steps**)

---

## Architecture & Key Features

- Django 4.2 + Django REST Framework powering SSR views and JWT-secured API
- PostgreSQL schema covering users, locations, telemetry, alert configs, and alert history (unique `(location, timestamp)` guard)
- Celery beat + worker pair fetching OpenWeatherMap every 30 minutes and evaluating thresholds
- Redis shared for Celery broker/result, caching weather responses, and Channels WebSocket layer
- Plotly-powered dashboard chart visualising the last 24 hours (auto-refresh + WebSocket push)
- OpenAPI documentation available at `/api/docs/`
- Architecture diagram & Mermaid source: `docs/architecture.png` / `docs/architecture.mmd`

---

## Requirement Coverage Snapshot

- ✅ REST endpoints: `/api/locations/`, `/api/weather/<id>/`, `/api/alerts/config/`, `/api/alerts/history/`, JWT auth endpoints (`/api/auth/token/`, `/api/auth/token/refresh/`)
- ✅ Background ingest: Celery beat (`fetch_and_store_weather`) schedules fan-out jobs that persist telemetry and trigger alerts
- ✅ Frontend templates: dashboard, locations CRUD, historical view, alert configuration, alert history
- ✅ Data visualisation: Plotly chart on dashboard and historical pages (24h trend)
- ✅ Deployment: Dockerfile + `docker-compose.yml` (web, worker, beat, PostgreSQL, Redis)
- ✅ Documentation: this README + `.env.example` + architecture assets

---

## Local Development (Python 3.11)

```bash
cp env.example .env                     # populate secrets before running
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser        # optional, for admin login
python manage.py runserver 0.0.0.0:8000 # web server

# in parallel terminals
celery -A core worker -l info
celery -A core beat -l info
```

- Default admin: `/admin/`
- Swagger/OpenAPI: `/api/docs/`
- WebSocket endpoint: `ws://localhost:8000/ws/updates/`

To seed sample telemetry locally run `python manage.py shell` and create locations; Celery beat will backfill on the next cycle.

---

## Docker Compose (local demo)

```bash
cp env.example .env
docker compose up --build
# or `docker compose up --build -d` to detach
```

Services: `web` (Daphne ASGI), `worker`, `beat`, `db` (PostgreSQL 15), `redis`. Static assets collected automatically. Stop with `docker compose down`.

---

## Environment Variables

All variables are documented in `.env.example`; copy to `.env` and adjust for your environment.

| Category | Keys |
| --- | --- |
| Django | `SECRET_KEY`, `DEBUG`, `DJANGO_ENV`, `ALLOWED_HOSTS` |
| Database | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` |
| Celery & Cache | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CACHE_URL`, `REDIS_HOST`, `REDIS_PORT` |
| External APIs | `OWM_API_KEY` |
| Email | `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `ALERT_NOTIFICATION_EMAIL`, `EMAIL_TIMEOUT`, `ALERT_EMAIL_MAX_ATTEMPTS`, `ALERT_EMAIL_RETRY_BACKOFF_SECONDS` |
| UI/Cache tuning | `WEATHER_CACHE_SECONDS`, `DASHBOARD_REFRESH_MAX_AGE_SECONDS`, `DASHBOARD_REFRESH_COOLDOWN_SECONDS` |

---

## API Reference

- `POST /api/auth/token/` → `{"username": "demo@example.com", "password": "SolarStorm42!"}` → returns access/refresh tokens
- `GET /api/locations/` → list locations owned by user
- `POST /api/locations/` → create location by city or coordinates (auto-geocodes when coordinates omitted)
  ```json
  {
    "name": "Toronto",
    "latitude": 43.65,
    "longitude": -79.38
  }
  ```
- `GET /api/weather/<location_id>/?hours=24` → latest measurement + history series
- `POST /api/alerts/config/` →
  ```json
  {
    "location": 1,
    "threshold_type": "wind_gt",
    "threshold_value": 12.5,
    "is_active": true
  }
  ```
- `GET /api/alerts/history/` → recent alert events (user-scoped)

All endpoints require authentication (session or JWT). Full schema published at `/api/schema/` and `/api/docs/`.

---

## Testing

```bash
python manage.py test --settings=core.test_settings
```

Test settings swap PostgreSQL/Redis for in-memory backends and run Celery eagerly.

---

## Design Decisions (≈320 words)

**Database model & scale:** PostgreSQL was chosen for relational integrity, with explicit foreign keys tying telemetry to users and locations. A unique constraint on `(location_id, timestamp)` prevents duplicate ingest, while selective indexes keep dashboard queries (latest measurement per site) efficient. At 1,000+ locations, partitioning by day or location plus read replicas would sustain ingest while keeping alert lookups fast.

**Caching & rate limits:** OpenWeatherMap’s free tier limits calls per minute, so Celery beat schedules a single `fetch_and_store_weather` task every 30 minutes, which then fans out using `apply_async` with a small stagger (`API_RATE_LIMIT_DELAY_SECONDS`). Weather API responses are cached per user/location/hour window via Redis, ensuring dashboard refreshes stay instantaneous without re-hitting the external API.

**Background execution:** Celery was favoured over cron so we could maintain retry logic, structured logging, and share Redis with Channels. Alerts are computed in the worker immediately after writing a telemetry point, guaranteeing consistent state before notifying operators. Email retries honour configurable attempt/backoff settings.

**Realtime UX:** Channels + WebSockets broadcast `weather_update` events to authenticated users, prompting client-side refresh and keeping dashboards in sync. Plotly handles interactive overlays for temperature, wind, and humidity; SSR pages keep the bundle lightweight for constrained network environments while still delivering rich interactions.

---

## Documentation & Assets

- `docs/architecture.mmd` / `docs/architecture.png` — system topology & data flow
- `telemetry/tasks.py` — Celery ingest and alert orchestration
- `telemetry/tests.py` — smoke tests covering API, tasks, and templates
- `env.example` — authoritative list of configuration variables

---

## Time & Next Steps

- Time spent: ~10 hours core build (models, API, Celery, SSR), ~5 hours polish (UI states, docs, deployment)
- If more time: add per-user notification preferences, historical rollups, and automated browser tests

When submitting, email `hiring@perceptivespace.com` with:
1. GitHub repository link (private)
2. Deployed demo URL
3. Credentials and setup caveats (env vars, external services)
4. Actual time spent & known follow-up work

---

## AI Disclosure

I used Cursor for linting hints and GitHub Copilot CLI for shell scaffolding. Algorithm design, data modeling, Celery orchestration, and documentation were written manually, with final review done without AI assistance.
