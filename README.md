# Dopamine Detox API

Backend API for the Dopamine Detox and Mindfulness Application.

## Tech Stack

| Component          | Technology                | Version |
|--------------------|---------------------------|---------|
| Web Framework      | FastAPI                   | 0.115.0 |
| Database           | PostgreSQL (Supabase)     | 14+     |
| Cache              | Redis                     | 5.0.7   |
| ORM                | SQLAlchemy                | 2.0.30  |
| Voice Storage      | Azure Blob Storage        | 12.19.0 |
| Speech-to-Text     | Google Cloud Speech       | 2.26.0  |
| LLM                | Google Gemini (LangChain) | 0.2.0   |
| Subscriptions      | RevenueCat                | -       |

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Docker (optional)

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
alembic upgrade head

# Start development server
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program uvicorn app.main:app --reload --port 8000
```

### Docker Development

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

nohup bash scripts/keep_alive.sh > keep_alive.log 2>&1 &

## API Documentation

When running in development mode, documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── api/v1/           # API endpoints
│   │   ├── auth.py       # Authentication
│   │   ├── profile.py    # User profile
│   │   ├── tasks.py      # Task management
│   │   ├── journal.py    # Journal entries
│   │   ├── subscription.py # Subscriptions
│   │   ├── onboarding.py # Onboarding flow
│   │   └── home.py       # Home/Stories
│   ├── core/             # Core functionality
│   │   ├── security.py   # JWT/password
│   │   ├── errors.py     # Error handling
│   │   ├── feature_limits.py
│   │   └── rate_limit.py
│   ├── db/               # Database
│   │   ├── base.py       # Base models
│   │   └── session.py    # Connection pool
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── auth_service.py
│   │   ├── task_service.py
│   │   ├── journal_service.py
│   │   ├── progress_service.py
│   │   ├── cache.py
│   │   ├── azure_storage.py
│   │   ├── speech_to_text.py
│   │   ├── gemini_llm.py
│   │   └── revenuecat.py
│   ├── middleware/
│   ├── utils/
│   ├── config.py         # Settings
│   ├── dependencies.py   # DI
│   └── main.py           # FastAPI app
├── alembic/              # Migrations
├── tests/                # Test suite
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Create account
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/logout` - Logout
- `POST /api/v1/auth/refresh-token` - Refresh JWT

### Profile
- `GET /api/v1/profile` - Get profile
- `PUT /api/v1/profile` - Update profile
- `GET /api/v1/profile/progress` - Progress stats

### Tasks
- `GET /api/v1/tasks/today` - Today's tasks
- `POST /api/v1/tasks` - Create task
- `POST /api/v1/tasks/{id}/complete` - Complete task
- `POST /api/v1/tasks/plan-day` - Voice planning (Premium)

### Journal
- `POST /api/v1/journal/entry` - Create entry
- `GET /api/v1/journal/entries` - List entries
- `GET /api/v1/journal/entries/{id}` - Get entry details

### Subscription
- `GET /api/v1/subscription/packages` - List packages
- `POST /api/v1/subscription/purchase` - Verify purchase
- `GET /api/v1/subscription/status` - Current status

### Home
- `GET /api/v1/home/stories` - Daily stories
- `GET /api/v1/home/dashboard` - Dashboard data

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run marked tests
pytest -m unit
```

## Environment Variables

See `.env.example` for all required environment variables.

Key configurations:
- `SUPABASE_DATABASE_URL` - PostgreSQL connection
- `REDIS_URL` - Redis connection
- `JWT_SECRET` - JWT signing key (min 32 chars)
- `GOOGLE_GEMINI_API_KEY` - Gemini API key
- `AZURE_STORAGE_CONNECTION_STRING` - Azure Blob Storage
- `REVENUECAT_API_KEY` - RevenueCat API key

## Deployment

### Production Checklist

1. Set `ENVIRONMENT=production`
2. Configure strong `JWT_SECRET`
3. Enable SSL/TLS
4. Set up database backups
5. Set up log aggregation
7. Configure rate limiting

### Docker Production

```bash
# Build image
docker build -t dopamine-detox-api .

# Run with environment file
docker run -p 8000:8000 --env-file .env dopamine-detox-api
```

## License

Proprietary - All rights reserved
