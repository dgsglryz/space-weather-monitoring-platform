# Space Weather Monitoring Platform

Production-ready weather monitoring and alerting for satellite ground stations. It fetches OpenWeatherMap data, stores telemetry, evaluates thresholds, and surfaces status through a server-rendered dashboard, JWT-secured REST API, live WebSockets, and email alerts.

- Repo: https://github.com/dgsglryz/space-weather-monitoring-platform
- Diagram: `docs/architecture.png` (Mermaid source: `docs/architecture.mmd`)
- Local demo: username `demo`, password `1234`

![System architecture](docs/architecture.png)

## Features

- Django 4.2 + DRF backend (SSR, JWT auth, OpenAPI at `/api/docs/`)
- PostgreSQL tables for locations, telemetry, alert configs, alert history
- Celery beat + worker run 30-minute ingests with retry/backoff email alerts
- Channels WebSocket pushes live readings to dashboards
- Plotly SSR dashboard with 24-hour charts and history metrics
- Docker Compose stack: Daphne web, worker, beat, PostgreSQL, Redis

## Setup

### Local Development

```bash
cp env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# in parallel terminals
celery -A core worker -l info
celery -A core beat -l info
```

- Admin UI: `/admin/`
- WebSocket feed: `ws://localhost:8000/ws/updates/`

### Docker

```bash
cp env.example .env
docker compose up --build
```

## API Reference

- `POST /api/auth/token/` → obtain JWT tokens
- `GET /api/locations/`
- `POST /api/locations/`
- `GET /api/weather/<id>/?hours=24`
- `POST /api/alerts/config/`
- `GET /api/alerts/history/`

Complete schema available at `/api/docs/`.

## Environment Variables

All variables live in `.env.example`: Django runtime, PostgreSQL, Redis/Celery URLs, `OWM_API_KEY`, SMTP credentials, and cache tuning knobs.

## Testing

```bash
python manage.py test --settings=core.test_settings
```

Uses in-memory database/cache and Celery eager mode.

## Design Decisions

- **Database.** PostgreSQL keeps telemetry, locations, alerts, and histories consistent, with `(location, timestamp)` uniqueness and targeted indexes. Scaling to 1,000+ locations would lean on partitioning plus read replicas.
- **Caching & rate limits.** Fetch cadence matches OpenWeatherMap’s free tier. Redis caches per-user/location windows and also backs Celery broker/result plus the WebSocket layer, so dashboards refresh without extra API calls.
- **Background jobs.** Celery supplies scheduling and retries. Each ingest writes telemetry, evaluates thresholds, stores alert history, and sends email with configurable retry/backoff.
- **SSR & UX.** Django templates keep pages lightweight. Plotly renders interactive 24-hour charts, while WebSockets stream live deltas. The history page adds min/max/avg summaries and last-updated timestamps.
- **Scalability.** Additional Celery workers, Redis queues, and indexed tables handle growth; Docker Compose mirrors production deployment, easing moves to managed infrastructure.

## Time Spent

Approximately 14 hours end-to-end (core build, ingestion, alerting, deployment polish, docs).

## AI Disclosure

Received light support from Cursor (ChatGPT-based) for polishing documentation phrasing, brainstorming test scenarios, and tightening inline comments. Architecture, application code, Celery/Redis integration, and final verification were handled directly by me.
