# Contributing

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- Git

### First-Time Setup

```bash
# Clone the repo
git clone <repo-url> && cd GMaps_Scraper

# Copy env file
cp .env.example .env

# Start infrastructure (DB + Redis)
docker compose up -d db redis

# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head

# Frontend setup
cd ../frontend
npm install
```

### Running Locally

```bash
# Terminal 1: Backend
cd backend && uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery worker
cd backend && celery -A app.tasks worker --loglevel=info

# Terminal 3: Frontend
cd frontend && npm run dev
```

Or use Docker Compose for everything:

```bash
make up
```

## Code Standards

### Python

- Use `async`/`await` for all I/O operations.
- Type hints on all function signatures.
- Use `dataclasses` or Pydantic models for data structures.
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes.
- Use `ruff` for linting and formatting.
- Docstrings on public functions (Google style).

### TypeScript

- Strict mode enabled (`strict: true` in tsconfig).
- No `any` types — use proper interfaces.
- Use `camelCase` for variables/functions, `PascalCase` for components/types.
- Tailwind CSS only — no CSS modules or styled-components.

### SQL / Models

- UUID primary keys on all tables.
- `created_at` and `updated_at` timestamps on all models.
- Use Alembic for all schema changes — never modify the DB directly.
- Add indexes for columns used in filters/sorts.

## Git Workflow

### Branching

- `main` — production-ready code
- `feat/<name>` — new features
- `fix/<name>` — bug fixes
- `chore/<name>` — maintenance, deps, config

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add SerpAPI integration for supplementary scraping
fix: handle empty grid when radius is too small
docs: update API reference with export endpoints
chore: bump fastapi to 0.111.0
```

### Pull Request Process

1. Create a feature branch from `main`.
2. Make changes, write tests.
3. Run `make lint` and `make test` locally.
4. Push branch and open a PR.
5. PR description should include: what changed, why, how to test.
6. Squash-merge to `main`.

## Adding Features

### New API Endpoint

See `.claude/skills/add-api-endpoint.md` for the step-by-step guide.

### New Service

See `.claude/skills/add-service.md` for the step-by-step guide.

### New Model

1. Create model in `backend/app/models/`.
2. Import in `backend/app/models/__init__.py`.
3. Create Alembic migration: `make migrate-create msg="add_new_table"`.
4. Run migration: `make migrate`.
5. Add Pydantic schemas in `backend/app/schemas.py`.

## Testing

```bash
# Run all tests
make test

# Run specific test file
docker compose exec backend pytest tests/test_grid.py -v

# Run with coverage
docker compose exec backend pytest --cov=app tests/
```
