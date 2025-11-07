# Space Weather Monitoring Platform

Django-powered monitoring for satellite ground stations: ingest weather, flag risky conditions, and notify operators through a server-rendered dashboard and authenticated API.

## Demo

- URL: https://space-weather-monitoring-demo.fly.dev
- Credentials: `demo@example.com` / `1234`
- Seeded data: Cape Canaveral, Vandenberg, Baikonur with 24-hour telemetry and alert history.

## Quickstart (Local, Python 3.11)

1. `cp env.example .env`
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `python manage.py migrate && python manage.py loaddata telemetry/fixtures/seed.json`
5. Run `celery -A core worker -l info`, `celery -A core beat -l info`, and `python manage.py runserver` in separate terminals.

## Docker Compose

1. `cp env.example .env`
2. `docker compose --profile prod up --build`
3. Visit `http://localhost:8000` for the dashboard, `/admin/` for management, `/api/schema/` for the OpenAPI spec.

## Environment Variables

- `SECRET_KEY`, `DEBUG`, `DJANGO_ENV`, `ALLOWED_HOSTS`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CACHE_URL`, `REDIS_HOST`, `REDIS_PORT`
- `OWM_API_KEY`
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `ALERT_NOTIFICATION_EMAIL`
- `WEATHER_CACHE_SECONDS`, `DASHBOARD_REFRESH_MAX_AGE_SECONDS`, `DASHBOARD_REFRESH_COOLDOWN_SECONDS`

Copy `.env.example` to `.env` and replace placeholder values before deploying.

## API Endpoints

- `GET /api/locations/` — list the authenticated user's monitored locations.
- `POST /api/locations/` — create a location `{ "name": "Toronto", "latitude": 43.65, "longitude": -79.38 }`.
- `GET /api/weather/{location_id}/` — retrieve the most recent telemetry for a location.
- `POST /api/alerts/config/` — upsert thresholds `{ "location": 1, "threshold_type": "temp_gt", "threshold_value": 30 }`.
- `GET /api/alerts/history/` — show alert history ordered by `triggered_at`.

Authenticate via session cookies (admin login) or JWT (`/api/token/`, `/api/token/refresh/`).

## Design Decisions

PostgreSQL persists locations, telemetry, alert configs, and histories with indexes on `(location_id, timestamp)` to keep reads predictable. Celery beat schedules ingestion every 30 minutes, and worker fan-out throttles OpenWeatherMap calls while triggering alert evaluation and optional email delivery. Redis serves as broker, cache, and WebSocket channel layer so dashboards hit cached metrics while receiving push updates. Scaling to 1,000+ locations relies on horizontal Celery workers, API pagination, and time-series partitioning (via database indexes) without changing the deployment story defined in Docker Compose.

## AI Disclosure

I used Cursor for lint suggestions, leaned on AI assistance while writing tests, and sought targeted mentorship on alert escalation trade-offs; implementation choices and final documentation are my own.
