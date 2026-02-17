# CLAUDE.md — Google Maps Scraper

## Project Overview

A free-tier ($0/month) Google Maps scraping tool that combines multiple data
sources for comprehensive business lead extraction. No paid API keys required.

### Data Source Layers

1. **Playwright** (Primary) — Headless Chromium scrapes Google Maps directly.
   Free, self-hosted, no API key needed. Extracts listings from search results
   and optionally scrapes detail pages for phone/website/hours.
2. **SerpAPI** (Supplement) — Validates and supplements Playwright results.
   100 free searches/month. Cached queries are free.
3. **Outscraper** (Enrichment, optional) — Adds email and social media links.
   500 free records/month. Only runs if API key is configured.

### Architecture

```
[Next.js Frontend] → [FastAPI Backend] → [Celery + Redis Queue]
                                              ↓
                         [PostgreSQL] ← [Worker Tasks]
                                              ↓
                    [Nominatim] → [Playwright] → [SerpAPI] → [Outscraper]
```

### Data Flow

1. User submits a scrape job (location + keyword + radius).
2. Backend geocodes via Nominatim (free), generates a search grid.
3. Celery task runs: Playwright → SerpAPI → Dedup → Outscraper → Store.
4. Frontend polls job status, displays results when done.
5. User can export results as CSV (default or Clay-compatible template).

## Cost

**$0/month** — All services run on free tiers:
- Geocoding: Nominatim (OpenStreetMap) — unlimited, 1 req/sec
- Scraping: Playwright (self-hosted Chromium) — unlimited
- Supplement: SerpAPI — 100 free searches/month
- Enrichment: Outscraper — 500 free records/month (optional)

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Celery + Redis
- **Scraping**: Playwright (async) + Chromium
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS
- **Database**: PostgreSQL 16
- **Queue**: Celery + Redis
- **Containerization**: Docker Compose

## Directory Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── db/           # Database session, migrations
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── services/     # geocoder, grid, playwright_scraper, serp_api, outscraper_api, dedup
│   │   ├── tasks/        # Celery task definitions
│   │   ├── config.py     # Pydantic Settings
│   │   ├── main.py       # FastAPI app entrypoint
│   │   └── schemas.py    # Pydantic request/response schemas
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/          # Next.js App Router pages
│       ├── components/   # React components
│       └── lib/          # API client, types, utilities
└── docs/
```

## Conventions

- **Python**: async/await everywhere, type hints required, snake_case.
- **Playwright**: always use `async with async_playwright() as p:` pattern.
- **Nominatim**: 1-second delay between requests (`asyncio.sleep(1.0)`).
- **Free tier limits**: Track monthly usage in each service module. Use env
  vars for limits so they can be adjusted without code changes.
- **TypeScript**: strict mode, camelCase, no `any`.
- **Models**: UUID primary keys, created_at/updated_at timestamps.
- **API**: JSON responses, pagination via `skip`/`limit`, proper HTTP status codes.
- **Commits**: conventional commits (`feat:`, `fix:`, `docs:`, `chore:`).

## Common Commands

```bash
make up          # Start all services
make down        # Stop all services
make build       # Rebuild containers
make logs        # Tail all logs
make migrate     # Run Alembic migrations
make test        # Run backend tests
make lint        # Run ruff linter
make format      # Run ruff formatter
make clean       # Remove containers and volumes
make init        # First-time setup
```

## Environment Variables

Copy `.env.example` to `.env`. No paid API keys required. Optional:
- `SERPAPI_KEY` — SerpAPI key (100 free searches/month)
- `OUTSCRAPER_API_KEY` — Outscraper key (500 free records/month)
- Database and Redis URLs are pre-configured for Docker Compose.
