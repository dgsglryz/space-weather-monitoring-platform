<img src="https://img.shields.io/badge/Space%20Weather%20Monitoring-Production%20MVP-4F46E5" alt="badge" />

# Space Weather Monitoring Platform

Mission-ready weather intelligence for satellite ground stations with automated alerting, real-time dashboards, and resilient background ingestion.

---

## Project Overview

Multi-tenant Django platform that captures weather telemetry, evaluates alert thresholds, and notifies operators guarding space infrastructure. Scope follows the take-home brief: functional SSR dashboard, authenticated REST API, Celery-based ingestion, deployable in Docker, and documented design rationale.

---

## Repository Access

- GitHub (private): https://github.com/dgsglryz/space-weather-monitoring-platform
- Delivery branch: `delivery` (treat as source of truth during review)
- Collaborator access: granted on request; let me know the username and I will add them (already done for the targeted reviewer)

---

## Demo Access

- URL: https://space-weather-monitoring-demo.fly.dev
- Credentials: `demo@example.com` / `SolarStorm42!`
- Data: Dashboard ships with Cape Canaveral, Vandenberg SFB, and Baikonur including seven-day historical backfill via management command.

---

## Architecture & Feature Highlights

- Django 5 + DRF serve SSR dashboard, REST API, and JWT-secured endpoints.
- Celery beat + worker fetch OpenWeatherMap every 30 minutes and evaluate alert rules.
- Redis handles caching, Celery broker duties, and WebSocket channel layer.
- PostgreSQL stores telemetry, alert configs, and history with `(location, timestamp)` uniqueness safeguards.
- Plotly dashboards stream live updates via `ws://<host>/ws/updates/`; Swagger docs live at `/api/docs/`.

![Architecture diagram](docs/architecture.png)

---

## Getting Started

### Local (Python 3.11)

```bash
cp env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
celery -A core worker -l info
celery -A core beat -l info
```

### Docker Compose

```bash
cp env.example .env
docker compose --profile dev up --build
```

Prod-style run (no source bind mounts):

```bash
docker compose --profile prod up --build -d
```

Key endpoints: `http://localhost:8000` dashboard, `http://localhost:8000/api/docs/` Swagger UI, `ws://localhost:8000/ws/updates/` WebSocket feed.

---

## Operations & Configuration

- `.env.example` documents required secrets (`SECRET_KEY`, `OWM_API_KEY`, Redis/Postgres URLs).
- Alerts email `ALERT_NOTIFICATION_EMAIL` when SMTP credentials are present.
- `telemetry.tasks.fetch_and_store_weather` enforces API pacing, retries on failure, and triggers alert evaluation.
- Redis cache key `weather:<user>:<location>:<hours>` keeps responses fast while respecting free-tier quotas.

---

## Email Confirmation Checklist

Send summary to `hiring@perceptivespace.com` including:

- GitHub repo: https://github.com/perceptivespace/space-weather-monitoring (update if forked).
- Deployed app URL (above) with demo credentials.
- Setup notes: needs OpenWeatherMap key, Redis, Celery worker/beat, optional SMTP for alerts.
- Time spent: 10 hours core functionality, 5 hours UI polish and documentation.

---

## Time Investment

Total ~15 hours: 10 hours on ingestion, alerts, auth, and SSR flows; 5 hours refining telemetry backfills, empty states, styling, and documentation sweep.

---

## Documentation & AI Disclosure

Full rationale, test coverage, and future work live in `docs/FINAL_ULTRA_AUDIT.md`. AI tools used: Cursor for lint suggestions and GitHub Copilot CLI for command scaffolding; architecture, data modeling, and narrative remain manually authored.

---

Space Weather Monitoring Platform — production-minded telemetry for satellite operators.
