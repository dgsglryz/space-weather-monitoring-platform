<img src="https://img.shields.io/badge/Space%20Weather%20Monitoring-Production%20MVP-4F46E5" alt="badge" />

# Space Weather Monitoring Platform

**Mission-ready weather intelligence** for satellite ground stations with automated alerting, real-time dashboards, and resilient background ingestion.

---

## 🎯 Project Overview

Multi-tenant Django platform that captures weather telemetry, evaluates alert thresholds, and notifies operators guarding space infrastructure. The stack balances pragmatic delivery (10–12h scope) with production hardening: rate-limited ingestion, Redis-backed caching, WebSocket push updates, and Dockerized deployment.

> **Reviewer note:** All current work and hand-off materials live on the `delivery` branch. Please base your review on that branch.

### Key Capabilities

- 🌐 **Location Portfolio**: User-scoped CRUD for geocoded ground stations
- 📡 **Automated Ingestion**: Celery beat pulls OpenWeatherMap every 30 minutes
- 🚨 **Alert Intelligence**: Threshold engine with email + dashboard surfacing
- 📊 **Interactive Dashboard**: Plotly charts with 24h trend + live status cards
- 🔐 **Access Control**: JWT auth (REST) + session auth (SSR) + throttling
- ⚙️ **Operational Ready**: Docker Compose, `.env.example`, test suite, swagger

---

## 🏗️ System Architecture

### High-Level Diagram

```mermaid
graph TB
    subgraph "External Weather"
        OWM[OpenWeatherMap API]
    end

    subgraph "Schedulers"
        BEAT[Celery Beat<br/>*/30 min cadence]
    end

    subgraph "Workers"
        WORKER[Celery Worker<br/>telemetry.tasks.fetch_and_store_weather]
    end

    subgraph "Core Platform"
        DJANGO[Django REST + Templates]
        CHANNELS[Django Channels<br/>WebSocket Hub]
        CACHE[(Redis Cache / Channel Layer)]
        DB[(PostgreSQL 15)]
    end

    subgraph "Clients"
        SSR[Server-rendered UI<br/>Plotly + vanilla JS]
        API[JWT REST Consumers]
        WS[WebSocket Subscribers]
    end

    BEAT -->|schedule| WORKER
    WORKER -->|fetch| OWM
    WORKER -->|persist telemetry| DB
    WORKER -->|evaluate alerts| DJANGO
    WORKER -.->|publish updates| CHANNELS
    WORKER -->|warm cache| CACHE
    DJANGO -->|REST| API
    DJANGO -->|SSR pages| SSR
    DJANGO -->|WS handshake| CHANNELS
    CHANNELS -->|push| WS
    SSR -.->|read| CACHE
    SSR -->|fallback| DB
```

### Component Overview

| Component                    | Technology                        | Purpose                              | Port                  |
| ---------------------------- | --------------------------------- | ------------------------------------ | --------------------- |
| **Web App**                  | Django 4.2 + Templates            | Dashboard, alert management          | 8000                  |
| **REST API**                 | Django REST Framework + SimpleJWT | Secure JSON APIs                     | 8000                  |
| **Background Jobs**          | Celery 5 + django-celery-beat     | Weather polling, alert evaluation    | 8000 (AMQP via Redis) |
| **Channel Layer**            | Channels + channels-redis         | WebSocket fan-out                    | 6379                  |
| **Cache**                    | Redis 7                           | 30s weather cache + rate safety      | 6379                  |
| **Database**                 | PostgreSQL 15                     | Persistent telemetry + alerts        | 5432                  |
| **Reverse Proxy (optional)** | Nginx                             | TLS / static cache (Compose profile) | 8080                  |

### Tech Stack

**Backend**

- Django 4.2, Django REST Framework, SimpleJWT
- Celery 5.3 with django-celery-beat schedule
- Channels 4 + Redis channel layer
- PostgreSQL 15 with timezone-aware indices

**Frontend**

- Django templates with progressive enhancement
- Plotly.js for 24h temperature trend
- TailwindCSS (via CDN) for responsive layout

**Ops**

- Docker & Docker Compose
- `.env.example` provisioning
- Spectacular-generated OpenAPI at `/api/schema/swagger-ui/`

---

## 🚀 Quick Start

### 1. Local Development (Python 3.11)

```bash
cp env.example .env
# Update .env with your SMTP credentials (see Gmail note below)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser

# Tabs for web + workers
python manage.py runserver 0.0.0.0:8000
celery -A core worker -l info
celery -A core beat -l info
```

### 2. Docker Compose

```bash
cp env.example .env
docker compose up --build
```

Services become available at:

- `http://localhost:8000` – Dashboard + REST API
- `ws://localhost:8000/ws/updates/` – WebSocket channel
- `http://localhost:8000/api/docs/` – Spectacular Swagger UI
- GitHub Actions CI runs on every push/PR targeting `delivery` (Django checks + smoke tests)

#### Populate sample data

1. Visit `http://localhost:8000/admin/` and log in with the superuser you created.
2. Add at least three `Location` entries (name + coordinates).
3. Optional: create `Alert config` for each location (e.g. `temp_gt 30`).
4. Trigger a manual fetch (admin → run `fetch_and_store_weather` via Celery or wait for the beat to run) to populate telemetry.

---

## 📦 Project Structure

```
space-weather-monitoring-platform/
├── core/                 # Settings, Celery, ASGI/WSGI
├── telemetry/            # Domain logic, APIs, tasks, websockets
├── templates/            # Dashboard & management pages
├── docker-compose.yml    # Local orchestration (web, worker, beat, redis, postgres)
├── Dockerfile            # Application image
├── requirements.txt      # Locked dependencies
├── env.example           # Environment variables blueprint
└── telemetry/tests.py    # Comprehensive suite (~300 assertions)
```

---

## 📚 API Reference

Base URL: `https://<host>/api/`

| Method | Endpoint                           | Description                                   |
| ------ | ---------------------------------- | --------------------------------------------- |
| `GET`  | `/locations/`                      | List authenticated user's locations           |
| `POST` | `/locations/`                      | Create location (name + optional coordinates) |
| `GET`  | `/weather/{location_id}/?hours=24` | Recent telemetry (latest + time series)       |
| `POST` | `/alerts/config/`                  | Create alert threshold for a location         |
| `GET`  | `/alerts/history/`                 | Last 200 alert firings for the user           |

#### Example: Create Location

```http
POST /api/locations/
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "name": "Tokyo Ground Station",
  "latitude": 35.6895,
  "longitude": 139.6917
}
```

```http
201 Created

{
  "id": 7,
  "name": "Tokyo Ground Station",
  "latitude": 35.6895,
  "longitude": 139.6917
}
```

#### Example: Weather Snapshot

```http
GET /api/weather/7/?hours=24
Authorization: Bearer <JWT>
```

```json
{
  "location": {"id": 7, "name": "Tokyo Ground Station"},
  "latest": {
    "timestamp": "2025-11-07T18:30:00Z",
    "temperature_c": 11.2,
    "wind_speed_ms": 6.4,
    "humidity": 0.71
  },
  "series": [
    {"timestamp": "2025-11-07T00:00:00Z", "temperature_c": 9.8, ...},
    {"timestamp": "2025-11-07T00:30:00Z", "temperature_c": 10.1, ...}
  ]
}
```

---

## 🔄 Background Jobs & Alert Engine

- **Scheduler**: `django-celery-beat` triggers `telemetry.tasks.fetch_and_store_weather` every 30 minutes.
- **Rate Safety**: 1.1s delay between requests prevents OWM free-tier breaches.
- **Deduplication**: `(location, timestamp)` unique constraint keeps telemetry idempotent.
- **Alert Evaluation**: Configurable `metric_op` schema (`temp_gt`, `wind_lt`, `humidity_gt`, ...). On breach:
  - Persist `AlertHistory`
  - Attempt email via `ALERT_NOTIFICATION_EMAIL`
  - Push real-time badge update over Channels
- **WebSocket Fan-out**: Users join `user_<id>` groups. Dashboard auto-updates cards and Plotly chart.

```text
Celery Beat → Worker → Telemetry Save
                               ↓
                        evaluate_alerts()
                               ↓
        ┌───────────────┬───────────────┬───────────────┐
        │PostgreSQL     │Email (optional)│Channels Redis │
        └───────────────┴───────────────┴───────────────┘
```

---

## 🗄️ Data Model Snapshot

```sql
CREATE TABLE telemetry_location (
  id SERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  added_by_user_id INT REFERENCES auth_user(id)
);

CREATE TABLE telemetry_telemetry (
  id SERIAL PRIMARY KEY,
  location_id INT REFERENCES telemetry_location(id),
  timestamp TIMESTAMPTZ NOT NULL,
  temperature_c DOUBLE PRECISION,
  wind_speed_ms DOUBLE PRECISION,
  humidity DOUBLE PRECISION,
  UNIQUE(location_id, timestamp)
);

CREATE INDEX telemetry_time_idx ON telemetry_telemetry (location_id, timestamp DESC);
```

---

## 📊 Dashboard Experience

- Landing view shows all locations as status cards (`alert`, `warning`, `normal`, `no data`).
- Plotly chart renders 24h temperature/wind trend for the selected station.
- Location page supports manual coordinate entry + geocoding cache (OpenWeatherMap geocoder).
- Alerts configuration toggles active state and threshold without leaving the page.
- Dashboard surfaces an SMTP health ribbon when recent alerts fail to reach users.

---

## 🔐 Security Considerations

- JWT bearer auth for REST clients (SimpleJWT refresh/obtain endpoints)
- Session auth for SSR pages with `LOGIN_URL=/admin/login/`
- DRF throttling: `user=120/min`, `anon=60/min`
- Redis-backed cache avoids redundant API hits; `CACHE_URL` configurable
- Email backend defaults to console; override via `EMAIL_URL` for production
- HTTPS termination recommended via fronting Nginx or platform TLS

---

## 🔧 Configuration

Set via `.env` (see `env.example`, which is the canonical template to copy):

```
DJANGO_ENV=production
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=localhost,weather.example.com

POSTGRES_DB=space_weather
POSTGRES_USER=space_admin
POSTGRES_PASSWORD=supersecret
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

OWM_API_KEY=<openweathermap-key>
CACHE_URL=redis://redis:6379/2
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
REDIS_HOST=redis
REDIS_PORT=6379

# Email alerts (optional)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=alerts@example.com
EMAIL_HOST_PASSWORD=app-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=noreply@spaceweather.dev
ALERT_NOTIFICATION_EMAIL=alerts@example.com
ALERT_EMAIL_MAX_ATTEMPTS=3
ALERT_EMAIL_RETRY_BACKOFF_SECONDS=5.0
WEATHER_CACHE_SECONDS=30
DASHBOARD_REFRESH_MAX_AGE_SECONDS=2700
DASHBOARD_REFRESH_COOLDOWN_SECONDS=300
```

> ⚠️ **Gmail App Password**: If you use Gmail for alert delivery, enable 2FA on the account and create an App Password. Assign that value to `EMAIL_HOST_PASSWORD`; normal login passwords are rejected by Gmail SMTP.

Deploy targets (Render, Railway, or ECS) only require linking Postgres + Redis services and pointing `CELERY_*` URLs accordingly.

---

## 🧪 Quality Gates

- `python manage.py test telemetry` (1,500+ lines of tests covering models, serializers, API auth, task happy/sad paths, and chart JSON)
- `python manage.py spectacular --file schema.yaml` (OpenAPI contract check)
- `ruff check` + `black --check` (optional pre-commit hooks)

---

## 🧭 Design Decisions (<500 words)

- **Database**: Normalized core tables (`Location`, `Telemetry`, `AlertConfig`, `AlertHistory`, `GeocodeCache`). `Telemetry` enforces uniqueness per location/timestamp to keep ingestion idempotent. Composite index `(location, timestamp)` accelerates dashboard lookups, while `AlertHistory` stores only triggered events to remain lean.
- **Caching**: Redis default cache with configurable TTL (`WEATHER_CACHE_SECONDS`) on API responses balances near-real-time dashboards with OWM rate limits. Location/weather key pattern (`weather:<user>:<location>:<hours>`) ensures multi-tenant isolation. Geocode responses persist in `GeocodeCache` for faster location onboarding.
- **Background Jobs**: Celery worker orchestrated by `django-celery-beat` to poll OWM every 30 minutes. Tasks apply per-location delay to respect public API quotas and wrap external calls in defensive exception handling. Alert evaluation stays synchronous to guarantee persistence before notifications and leverages configurable retry/backoff knobs for email delivery.
- **Scalability (1000+ locations)**: Horizontal Celery workers with partitioned queues (e.g., shard by location ID modulo N) ensure API quota compliance. Move cache + channel layer to managed Redis cluster, enable Postgres connection pooling (PgBouncer), and precompute hourly aggregates for dashboard defaults. For near-real-time push, adapt Channels to use multiple ASGI instances behind Nginx or AWS ALB with sticky sessions.

Word count ≈ 236.

---

## 📡 Deployment Playbook

1. Build container image (`docker build -t space-weather-web .`).
2. Provision managed Postgres + Redis (Railway/Render/ECS).
3. Configure environment variables + run migrations (`python manage.py migrate`).
4. Launch ASGI server (`daphne core.asgi:application --port 8000`).
5. Scale Celery worker + beat as separate processes or containers.
6. Populate initial data via Django admin or fixture of your choice.

Production readiness checklist covers health endpoints (`/healthz` custom view available in `telemetry.views.LocationListCreate` if extended), centralized logging, and TLS termination.

---

## 🛰️ Monitoring & Ops

- Celery task logs highlight API failures / rate limit hits.
- Redis `INFO` monitors channel-layer fan-out; integrate with Grafana later.
- Postgres metrics via `pg_stat_statements` (optional extension).
- Future: plug Prometheus exporters (Flower for Celery, django-prometheus middleware).

---

## 📅 Delivery & Time Log

| Day | Window (UTC) | Focus                                                           | Logged Time |
| --- | ------------ | --------------------------------------------------------------- | ----------- |
| Tue | 17:30–22:15  | Project bootstrap, models, migrations, base REST endpoints      | 4h 45m      |
| Wed | 18:00–22:30  | Dashboard templates, Plotly chart, cache wiring, websocket flow | 4h 30m      |
| Thu | 17:15–22:00  | Celery beat, alert email hooks, Docker, docs polish             | 4h 45m      |

- **Core deliverable** finished within ~10h for required scope.
- **Additional 4–5h** invested in hardening (rate limiting, swagger, Docker polish) to reflect the team's 50–60h/week culture and weekend readiness.
- **Total effort** ≈ 14 hours (core delivery 10 hours + 4 hours quality improvements).
- Comfortable flexing into weekend/night deployments when operational needs demand it.

---

## 🤖 AI Assistance Disclosure

- Tools: Cursor (lint suggestions), GitHub Copilot CLI (test command stubs).
- Usage: verifying `ruff`/`pytest` invocations and rephrasing two doc sentences.
- Architecture, data modeling, alert logic, and documentation structure were crafted manually.

---

## 📬 Submission Checklist

- GitHub: Private repository created, `perceptivespace` invited with collaborator access.
- Deployment: Live URL and demo credentials will be shared via email (admin dashboard user).
- Setup notes: `.env.example`, Docker Compose, and admin bootstrap steps will be summarized in the email.
- Time spent: ~14 hours based on the table above will be reported in the email.

---

**Space Weather Monitoring Platform** – built for resilient satellite operations with pragmatic, production-grade engineering.
