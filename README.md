Space Weather Monitoring Platform
=================================

Overview
--------

This project delivers a weather monitoring dashboard focused on sudden
environment changes. Authenticated users can register the locations they care
about, ingest near-real-time telemetry, and configure threshold-based alerts.

Key Modules
-----------

* `telemetry` – data models, REST endpoints, Celery tasks, websocket updates
* `templates` – server-rendered dashboard, alerts, and location management UIs
* `core` – project settings, URL router, Celery bootstrap

Stack
-----

* Django 4.x + Django REST Framework
* Celery + Redis for ingestion/alerts (see `docker-compose.yml`)
* Channels for websocket updates to the dashboard
* PostgreSQL (via Docker) as the main datastore
* Plotly for client-side visualisations

Local Setup
-----------

1. Copy `.env.example` to `.env` and adjust the required secrets (OWM key, DB credentials).
2. Create a virtualenv, install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Apply migrations and create a superuser:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. Run the development stack:

   ```bash
   python manage.py runserver
   celery -A core worker -l info
   celery -A core beat -l info
   ```

   Or launch the Docker Compose stack:

   ```bash
   docker compose up --build
   ```

Testing
-------

The `telemetry/tests.py` module covers model constraints, serializer validation,
API authentication, alert flow, and dashboard rendering. Run the suite with:

```bash
python manage.py test telemetry
```

Alert Pipeline
--------------

1. `celery beat` schedules `fetch_and_store_weather()` every 30 minutes.
2. The task fetches from OpenWeatherMap, stores telemetry, and calls
   `evaluate_alerts()`.
3. Alerts trigger an email, persist to `AlertHistory`, and broadcast over a
   Channels group via `_publish_update()`.
4. The dashboard websocket consumer refreshes the active chart when a new
   payload lands.

Delivery Notes
--------------

This branch (`delivery`) curates the project history for submission. Commits are
grouped by major concerns:

1. Core Django scaffold & dependencies
2. Telemetry models & migrations
3. API serializers, permissions, URL wiring
4. REST & dashboard views with caching
5. Celery ingest + alert evaluation pipeline
6. Server-rendered UI + websocket consumer
7. Docker/Compose setup & env templates
8. CI/test scaffolding & documentation

AI Assistance Disclosure
------------------------

Coding decisions, schema design, and data flow were authored manually. An AI
assistant was used for light editing (comment wording, commit planning) but not
for architectural choices or algorithm design.

