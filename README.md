# Google Maps Scraper

A free-tier ($0/month) Google Maps scraping tool with Playwright-based data
collection, async task processing, and a modern web UI.
**No paid API keys required.**

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Next.js 14    │────▶│   FastAPI 0.111  │────▶│  Celery Worker  │
│   Frontend      │◀────│   Backend        │◀────│  (Redis Queue)  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                               │                          │
                        ┌──────┴──────┐          ┌────────┴────────┐
                        │ PostgreSQL  │          │  Data Sources   │
                        │     16      │          │                 │
                        └─────────────┘          │ 1. Playwright   │
                                                 │ 2. SerpAPI      │
                                                 │ 3. Outscraper   │
                                                 │    (Nominatim)  │
                                                 └─────────────────┘
```

### Cost: $0/month

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| Nominatim (OSM) | Geocoding | Unlimited (1 req/sec) |
| Playwright | Primary scraper | Unlimited (self-hosted) |
| SerpAPI | Supplementary data | 100 searches/month |
| Outscraper | Email/social enrichment | 500 records/month |

### Data Collection Layers

| Layer | Source | Purpose | Limit |
|-------|--------|---------|-------|
| 1 | Playwright + Chromium | Primary — scrapes Google Maps directly | Unlimited |
| 2 | SerpAPI | Supplementary SERP validation | 100/month free |
| 3 | Outscraper (optional) | Email & social media enrichment | 500/month free |

### Scraping Pipeline

1. **Geocode** (Nominatim) — Convert location input to coordinates.
2. **Grid Generation** — Create overlapping search grid within radius.
3. **Playwright Scrape** — Headless Chromium scrapes Google Maps search results.
4. **SerpAPI Supplement** — Supplementary SERP data (if under monthly limit).
5. **Deduplication** — Merge results by `place_id` + fuzzy matching.
6. **Outscraper Enrich** — Add email/social data (optional, if API key set).
7. **Storage** — Persist leads to PostgreSQL.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- That's it. No paid API keys needed.

Optional (for more data):
- SerpAPI key (100 free searches/month) — [serpapi.com](https://serpapi.com)
- Outscraper key (500 free records/month) — [outscraper.com](https://outscraper.com)

### Setup

```bash
# Clone and enter project
git clone <repo-url> && cd GMaps_Scraper

# Copy environment file
cp .env.example .env
# Optionally add SERPAPI_KEY and OUTSCRAPER_API_KEY

# Start everything (builds containers, installs Chromium, runs migrations)
make init
```

The app will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Flower (Celery monitor)**: http://localhost:5555

### Development

```bash
make up          # Start all services
make down        # Stop all services
make build       # Rebuild after dependency changes
make logs        # Tail logs
make test        # Run tests
make lint        # Lint Python code
make format      # Auto-format Python code
make migrate     # Run database migrations
```

## API Reference

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobs` | Create a new scrape job |
| GET | `/api/jobs` | List all jobs (paginated) |
| GET | `/api/jobs/{id}` | Get job details |
| DELETE | `/api/jobs/{id}` | Cancel a running job |

### Results

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/results/{job_id}` | Get leads for a job (paginated, sortable, filterable) |
| GET | `/api/results/{job_id}/export` | Export leads as CSV |
| GET | `/api/results/{job_id}/stats` | Get job statistics |

### Create Job Request

```json
{
  "keyword": "restaurants",
  "location": "Austin, TX",
  "location_type": "address",
  "radius_km": 5.0,
  "latitude": null,
  "longitude": null
}
```

### Job Response

```json
{
  "id": "uuid",
  "status": "playwright",
  "keyword": "restaurants",
  "location": "Austin, TX",
  "progress": 45,
  "total_found": 127,
  "total_unique": 98,
  "estimated_cost_usd": 0.00,
  "created_at": "2025-01-01T00:00:00Z"
}
```

## Roadmap

- [x] Phase 1: Core architecture, database models, grid search
- [x] Phase 2: Playwright primary scraper (replaces Places API)
- [x] Phase 3: SerpAPI supplement + deduplication
- [x] Phase 4: Frontend UI with real-time progress
- [x] Phase 5: Nominatim free geocoding (replaces Google Geocoding)
- [x] Phase 6: Outscraper optional enrichment
- [ ] Phase 7: Advanced filtering + saved searches
- [ ] Phase 8: Webhook notifications + API keys
- [ ] Phase 9: Multi-user support

## License

MIT — see [LICENSE](LICENSE).
