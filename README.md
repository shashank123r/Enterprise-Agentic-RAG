# 🧠 Enterprise Agentic RAG Platform

A **production-grade** Retrieval-Augmented Generation platform engineered for enterprise AI workloads. Built on a **Clean Architecture** foundation with async-first Python, multi-agent orchestration, and a modular retrieval pipeline — designed to scale from proof-of-concept to billion-document deployments.

---

## 📋 Table of Contents

- [Architecture Overview](#-architecture-overview)
- [Technology Stack](#-technology-stack)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [API Documentation](#-api-documentation)
- [Development](#-development)
- [Testing](#-testing)
- [Docker Deployment](#-docker-deployment)
- [Design Decisions](#-design-decisions)
- [License](#-license)

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend (UI)                      │
├─────────────────────────────────────────────────────────────┤
│                    FastAPI Gateway (API)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │ Auth     │ │ Router   │ │ Services │ │  Middleware     │ │
│  │ (JWT)    │ │ (v1)     │ │ (Logic)  │ │  CORS/Log/Rate │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Service Layer                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │ Auth     │ │ RAG      │ │ Agent    │ │  Evaluation    │ │
│  │ Service  │ │ Pipeline │ │ Orchestr.│ │  Service       │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │PostgreSQL│ │ Milvus   │ │ Redis    │ │  Object Store  │ │
│  │+pgvector │ │(VectorDB)│ │(Cache/Q) │ │  (MinIO/S3)    │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Inference Layer (NVIDIA NIM)               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Embedding NIM│ │ Re-ranking   │ │ Chat/LLM NIM         │ │
│  │ (nv-embed-qa)│ │ NIM          │ │ (Nemotron/Llama)     │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Principles

| Principle | Implementation |
|---|---|
| **Clean Architecture** | Domain-driven structure with strict separation of concerns: API → Service → Repository → Model |
| **Dependency Injection** | FastAPI `Depends` for auth, DB sessions, and services — maximally testable |
| **Async-Native** | Full `asyncio` throughout — asyncpg, redis-py, httpx for all I/O |
| **RBAC** | Role-based access control with granular permissions, enforced at the dependency level |
| **Observability** | Structured JSON logging (structlog), request tracing, health probes |
| **Security First** | JWT with refresh tokens, bcrypt password hashing, rate limiting, CORS |

---

## 💻 Technology Stack

| Category | Technology | Version | Purpose |
|---|---|---|---|
| **Language** | Python | 3.13+ | Runtime |
| **Framework** | FastAPI | 0.115+ | Async HTTP API |
| **ORM** | SQLAlchemy | 2.0+ | Async database ORM |
| **Migrations** | Alembic | 1.14+ | Schema migrations |
| **Database** | PostgreSQL 17 + pgvector | 17 | Primary + vector storage |
| **Vector DB** | Milvus | 2.5+ | Billion-scale vector search |
| **Cache** | Redis | 7.4+ | Caching, sessions, rate limiting |
| **Serialization** | Pydantic V2 | 2.10+ | Validation + settings |
| **Auth** | python-jose + passlib | latest | JWT + bcrypt |
| **Logging** | structlog | 24.4+ | Structured JSON logging |
| **Inference** | NVIDIA NIM | latest | GPU-optimized LLM serving |
| **Frontend** | React + TypeScript | latest | Admin UI |
| **Containers** | Docker + Compose | latest | Local dev & prod |
| **CI/CD** | GitHub Actions | — | Automated quality gates |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- Docker & Docker Compose
- PostgreSQL 17 (or Docker)
- Redis 7.4+ (or Docker)
- NVIDIA GPU + NVIDIA Container Toolkit (for NIM inference — optional for dev)

### 1. Clone & Setup

```bash
git clone <repo-url>
cd enterprise-rag

# Create environment
cp .env.example .env
# Edit .env with your settings

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
```

### 2. Install Dependencies

```bash
# Development install (includes test/lint tools)
pip install -e ".[dev]"

# Production install only
pip install -e .
```

### 3. Start Dependencies

```bash
docker compose up -d postgres redis
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Application

```bash
# Development (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using Make
make run
```

### 6. Verify

```bash
# Health check
curl http://localhost:8000/api/v1/health/live

# API documentation
open http://localhost:8000/api/v1/docs
```

---

## 📁 Project Structure

```
enterprise-rag/
├── app/                         # Application package
│   ├── main.py                 # FastAPI application factory
│   ├── api/                    # API layer
│   │   └── v1/
│   │       ├── router.py       # Route aggregation
│   │       └── endpoints/      # Endpoint handlers
│   │           ├── health.py   # Liveness/readiness probes
│   │           ├── auth.py     # Login, register, refresh
│   │           └── users.py    # User CRUD with RBAC
│   ├── core/                   # Configuration & utilities
│   │   ├── config.py           # Pydantic Settings (.env)
│   │   ├── security.py         # JWT, password hashing
│   │   ├── exceptions.py       # Exception hierarchy + handlers
│   │   ├── logging.py          # structlog configuration
│   │   ├── dependencies.py     # FastAPI DI providers
│   │   └── constants.py        # Enums, roles, permissions
│   ├── models/                 # SQLAlchemy ORM models
│   │   └── user.py            # User model with RBAC
│   ├── schemas/                # Pydantic V2 schemas
│   │   ├── auth.py            # Auth request/response schemas
│   │   ├── user.py            # User CRUD schemas
│   │   └── common.py          # Pagination, health, errors
│   ├── services/               # Business logic layer
│   │   ├── auth_service.py    # Authentication logic
│   │   └── user_service.py    # User management logic
│   ├── repositories/           # Data access layer
│   │   ├── base.py            # Generic CRUD repository
│   │   └── user_repository.py # User-specific queries
│   ├── db/                     # Database configuration
│   │   ├── session.py         # Async engine + session factory
│   │   └── base.py            # Declarative base + mixins
│   ├── cache/                  # Redis caching layer
│   │   └── redis.py           # Connection pool + manager
│   └── middleware/             # FastAPI middleware
│       ├── cors.py            # CORS configuration
│       ├── logging.py         # Request/response logging
│       └── rate_limit.py      # Sliding window rate limiter
├── alembic/                    # Database migrations
│   ├── env.py                 # Async Alembic environment
│   ├── script.py.mako         # Migration template
│   └── versions/              # Migration versions
├── tests/                      # Test suite
│   ├── conftest.py            # Fixtures (DB, client, auth)
│   ├── test_api/              # API endpoint tests
│   │   ├── test_health.py     # Health endpoint tests
│   │   └── test_auth.py       # Auth endpoint tests
│   └── test_services/         # Service layer tests
│       └── test_auth_service.py
├── scripts/                    # Utility scripts
│   └── init-db.sql            # DB initialization
├── .github/workflows/         # CI/CD pipelines
│   └── ci.yml                 # Lint, test, build, security
├── Dockerfile                  # Production container
├── Dockerfile.dev              # Development container
├── docker-compose.yml          # Service orchestration
├── docker-compose.dev.yml      # Development overrides
├── pyproject.toml              # Project metadata + tooling
├── .env.example                # Environment template
├── Makefile                    # Common commands
└── README.md                   # This file
```

---

## ⚙️ Configuration

All configuration is managed via **environment variables** loaded from `.env`. The settings are validated at startup by Pydantic V2 `BaseSettings`.

### Key Configuration Groups

| Group | Variables | Description |
|---|---|---|
| **General** | `PROJECT_NAME`, `ENVIRONMENT`, `DEBUG`, `SECRET_KEY` | Application metadata |
| **Authentication** | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | JWT configuration |
| **PostgreSQL** | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Database connection |
| **Redis** | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | Cache configuration |
| **Milvus** | `MILVUS_HOST`, `MILVUS_PORT`, `MILVUS_COLLECTION_PREFIX` | Vector database |
| **NVIDIA NIM** | `NIM_EMBEDDING_URL`, `NIM_CHAT_URL`, `NIM_API_KEY`, `NIM_MODEL_*` | Inference microservices |
| **Rate Limiting** | `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS_PER_MINUTE` | API protection |
| **CORS** | `CORS_ORIGINS`, `CORS_ALLOW_CREDENTIALS` | Cross-origin settings |
| **Logging** | `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE` | Observability |

> **Security Note:** In production, all secrets (`SECRET_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, `NIM_API_KEY`) **must** be rotated to strong, unique values. The application will refuse to start with default secrets in production mode.

---

## 📖 API Documentation

### Base URL
```
http://localhost:8000/api/v1
```

### Interactive Docs
```
http://localhost:8000/api/v1/docs   # Swagger UI
http://localhost:8000/api/v1/redoc  # ReDoc
```

### Endpoint Overview

#### Health

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health/live` | No | Liveness probe |
| GET | `/health/ready` | No | Readiness probe with dependency checks |
| GET | `/health` | No | Full health status |

#### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | No | Login with email + password |
| POST | `/auth/register` | No | Create a new account |
| POST | `/auth/refresh` | No | Refresh expired access token |
| POST | `/auth/logout` | Yes | Invalidate refresh token |
| GET | `/auth/me` | Yes | Get current user profile |

#### Users

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/users/` | Admin | List all users (paginated) |
| GET | `/users/{id}` | Yes | Get user by ID |
| PATCH | `/users/me` | Yes | Update own profile |
| PATCH | `/users/{id}` | Admin | Admin update user |
| DELETE | `/users/{id}` | Admin | Delete user |

### Response Format

**Success:**
```json
{
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe",
    "role": "user",
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z"
}
```

**Error:**
```json
{
    "error": {
        "code": "invalid_credentials",
        "message": "Invalid email or password",
        "details": {}
    }
}
```

---

## 🛠 Development

### Setup Development Environment

```bash
# Install with dev dependencies
make dev

# Install pre-commit hooks
make precommit-install

# Start dependencies
docker compose up -d postgres redis

# Run migrations
make migrate

# Start the server with hot reload
make run
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type check
make typecheck

# Run all quality checks
make precommit-run
```

### Makefile Commands

| Command | Description |
|---|---|
| `make install` | Install production dependencies |
| `make dev` | Install development dependencies |
| `make format` | Format with Black + Ruff |
| `make lint` | Lint with Ruff |
| `make typecheck` | Type check with MyPy |
| `make test` | Run tests with coverage |
| `make run` | Start dev server with reload |
| `make migrate` | Run database migrations |
| `make revision` | Create new migration |
| `make docker-up` | Start all Docker services |

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_api/test_auth.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run with verbose output
pytest tests/ -v --tb=long
```

### Test Structure

- **`tests/conftest.py`** — Shared fixtures (DB session, test client, auth tokens)
- **`tests/test_api/`** — End-to-end API tests using `httpx.AsyncClient`
- **`tests/test_services/`** — Unit tests for service layer

### Test Fixtures

| Fixture | Description |
|---|---|
| `db_session` | Clean PostgreSQL session per test |
| `client` | FastAPI test client (httpx AsyncClient) |
| `test_user` | Pre-created regular user |
| `admin_user` | Pre-created admin user |
| `user_token` | JWT access token for test user |
| `admin_token` | JWT access token for admin user |

---

## 🐳 Docker Deployment

### Development

```bash
# Start all services
docker compose up -d

# Start with hot reload
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# View logs
docker compose logs -f api

# Rebuild
docker compose up -d --build
```

### Production

```bash
# Build and start
docker compose up -d

# Scale API workers
docker compose up -d --scale api=3

# Run migrations
docker compose run --rm migration

# Full stack (including Milvus)
docker compose --profile full up -d

# With NVIDIA NIM
docker compose --profile full --profile nim up -d
```

### Health Checks

All services include Docker health checks. Verify deployment:

```bash
curl http://localhost:8000/api/v1/health
```

---

## 🎯 Design Decisions

### Why FastAPI over Django/Flask?
- Async-native, critical for I/O-bound RAG workloads
- Automatic OpenAPI docs with Pydantic V2 validation
- First-class dependency injection for Clean Architecture
- ORJSON for high-performance serialization

### Why SQLAlchemy 2.0 over raw SQL?
- Async support via asyncpg
- Type-safe queries with Mapped[] annotations
- Alembic for version-controlled migrations
- pgvector extension for hybrid search fallback

### Why Repository Pattern?
- Clean separation of data access from business logic
- Makes unit testing trivial (mock repositories)
- Consistent interface for all data operations
- Easy to add caching layer later

### Why structlog over standard logging?
- Native JSON output for log aggregation (ELK, Datadog)
- Context variables for request tracing
- Better performance than stdlib logging
- Structured format enables automated analysis

### Why Custom Auth over Auth0/Okta?
- Zero external dependencies for core auth
- JWT-based, stateless, horizontally scalable
- RBAC built into the dependency injection system
- Easy to plug in OIDC/SSO later

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <strong>Built with ❤️ for Enterprise AI</strong>
</div>
