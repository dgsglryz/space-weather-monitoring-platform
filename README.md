# Weather Alert Dashboard

Django web application for monitoring weather at multiple locations with configurable alert thresholds.

## Features

- Monitor weather for multiple locations
- Set custom alert thresholds per location
- View historical data with charts
- Automatic weather data fetching every 30 minutes
- REST API for programmatic access

## Tech Stack

- Django 4.2, Django REST Framework
- PostgreSQL
- Celery with Redis
- Django Templates, Plotly.js
- OpenWeatherMap API

## Setup Instructions

### Prerequisites

- Python 3.9+
- PostgreSQL
- Redis
- Docker & Docker Compose (optional)

### Local Development

1. Clone the repository and navigate to the project directory

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file from `.env.example`:
```bash
cp .env.example .env
```

5. Update `.env` with your configuration:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
POSTGRES_DB=weather_db
POSTGRES_USER=weather_user
POSTGRES_PASSWORD=weather_pass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
OWM_API_KEY=your-openweathermap-api-key
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

6. Create PostgreSQL database:
```bash
createdb weather_db
```

7. Run migrations:
```bash
python manage.py migrate
```

8. Create a superuser:
```bash
python manage.py createsuperuser
```

9. Start Redis (if not running):
```bash
redis-server
```

10. Start Celery worker (in a separate terminal):
```bash
celery -A core worker -l info
```

11. Start Celery beat (in another terminal):
```bash
celery -A core beat -l info
```

12. Run the development server:
```bash
python manage.py runserver
```

The application will be available at `http://localhost:8000`

### Docker Deployment

1. Copy `.env.example` to `.env` and update with your values

2. Build and start containers:
```bash
docker-compose up --build
```

This will start:
- PostgreSQL database
- Redis
- Django web server
- Celery worker
- Celery beat scheduler

## API Documentation

All API endpoints require authentication. Use JWT tokens or session authentication.

### Authentication

**Get JWT Token:**
```bash
POST /api/auth/token/
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password"
}
```

**Refresh Token:**
```bash
POST /api/auth/token/refresh/
Content-Type: application/json

{
  "refresh": "your_refresh_token"
}
```

### Endpoints

**List Locations:**
```bash
GET /api/locations/
Authorization: Bearer <token>
```

**Add Location:**
```bash
POST /api/locations/
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Toronto",
  "latitude": 43.6532,
  "longitude": -79.3832
}
```

**Get Weather Data:**
```bash
GET /api/weather/{location_id}/?hours=24
Authorization: Bearer <token>
```

Response:
```json
{
  "location": {
    "id": 1,
    "name": "Toronto",
    "latitude": 43.6532,
    "longitude": -79.3832
  },
  "latest": {
    "timestamp": "2025-11-06T10:30:00Z",
    "temperature_c": 15.5,
    "wind_speed_ms": 8.2,
    "humidity": 65
  },
  "series": [...]
}
```

**Configure Alert:**
```bash
POST /api/alerts/config/
Authorization: Bearer <token>
Content-Type: application/json

{
  "location": 1,
  "threshold_type": "temp_gt",
  "threshold_value": 30.0,
  "is_active": true
}
```

Threshold types: `temp_gt`, `temp_lt`, `wind_gt`, `wind_lt`, `humidity_gt`, `humidity_lt`

**Get Alert History:**
```bash
GET /api/alerts/history/
Authorization: Bearer <token>
```

## Environment Variables

See `.env.example` for all required environment variables.

## Design Decisions

**Database:**
PostgreSQL chosen for reliability with time-series data. Separate tables for locations, telemetry, alerts, and history. Timestamp fields indexed for faster queries.

**Background Jobs:**
Celery with Redis runs every 30 minutes to balance API limits and freshness. Each location processed separately with error handling so one failure doesn't block others.

**Caching:**
Geocoding results cached in database to reduce external API calls. No additional caching - PostgreSQL handles current scale well.

**Scaling:**
Current setup handles ~1000 locations with single worker. For larger scale: multiple Celery workers, Redis caching, connection pooling, consider TimescaleDB for telemetry, horizontal scaling with load balancer.

## License

This project is proprietary and confidential.

