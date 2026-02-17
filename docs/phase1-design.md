# Phase 1 Design Document

## Tech Stack Decisions

### Backend: FastAPI + SQLAlchemy 2.0 (async)

**Why FastAPI:**
- Native async support — critical for I/O-heavy scraping workloads.
- Automatic OpenAPI docs for frontend integration.
- Pydantic validation built-in.
- High performance with uvicorn.

**Why SQLAlchemy 2.0 async:**
- First-class async engine with asyncpg driver.
- Mature ORM with excellent migration support (Alembic).
- JSONB column support for flexible data (hours, photos, raw API responses).

### Task Queue: Celery + Redis

**Why Celery:**
- Battle-tested distributed task queue.
- Built-in task revocation (for job cancellation).
- Flower monitoring UI.
- Supports rate limiting and retry logic.

**Why Redis (not RabbitMQ):**
- Simpler deployment — single service for broker + result backend.
- Lower memory footprint for our workload.
- Also usable for caching in later phases.

### Frontend: Next.js 14 (App Router)

**Why Next.js:**
- App Router for modern React patterns.
- Server Components for initial page loads.
- Built-in routing and code splitting.
- Strong TypeScript support.

**Why Tailwind CSS:**
- Utility-first — faster to build custom UI without fighting a component library.
- Small bundle size with purging.
- Dark mode support via CSS variables.

### Database: PostgreSQL 16

**Why PostgreSQL:**
- JSONB columns for flexible semi-structured data.
- Full-text search for future lead searching.
- UUID primary key support.
- Robust indexing for filtered queries.

---

## Data Schema

### Job Table

Represents a single scrape request. Tracks status through the pipeline.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| status | Enum | Pipeline step: pending → geocoding → grid_search → places_api → serp_api → dedup → completed/failed/cancelled |
| keyword | String | What to search for |
| location | String | Where to search |
| location_type | String | "address" or "coordinates" |
| radius_km | Float | Search area radius |
| latitude/longitude | Float | Geocoded center point |
| progress | Integer | 0–100 percentage |
| current_step | String | Human-readable step description |
| total_found/total_unique | Integer | Result counts |
| places_api_calls/serp_api_calls | Integer | API call counters |
| estimated_cost_usd | Float | Running cost estimate |
| celery_task_id | String | For task revocation |
| error_message | Text | Error details if failed |

### Lead Table

Represents a single business found during scraping.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID | Primary key |
| job_id | UUID (FK) | Parent job |
| place_id | String | Google Place ID (dedup key) |
| name, address, phone, website | String/Text | Core business info |
| rating, review_count | Float/Integer | Reputation data |
| types | JSONB | Google place type array |
| business_type | String | Primary type for filtering |
| latitude/longitude | Float | Coordinates |
| opening_hours | JSONB | Structured hours data |
| photos | JSONB | Photo references |
| source | String | "places_api", "serp_api", or "places_api+serp_api" |
| raw_data | JSONB | Full API response for debugging |

**Indexes:**
- `ix_leads_job_id_place_id` (unique) — prevents duplicates per job.
- `ix_leads_name` — for search filtering.
- `ix_leads_rating` — for sort/filter queries.

---

## Location Strategy

### Grid-Based Search

The Google Places API limits Nearby Search to a circular area. To cover
a larger area (e.g., 20km radius), we generate a grid of overlapping
search circles.

```
     ○ ○ ○
    ○ ○ ○ ○
   ○ ○ ○ ○ ○
    ○ ○ ○ ○
     ○ ○ ○
```

**Parameters:**
- **Max cell radius:** 5km (Places API practical limit for nearby search).
- **Overlap factor:** 20% (configurable). Ensures no gaps between cells.
- **Step distance:** `cell_diameter * (1 - overlap_factor)`.

**Single-cell optimization:** If `radius_km <= 5`, skip grid generation
and search with a single cell at the center point.

### Dual Search Strategy

For each grid point, we run two API calls:
1. **Nearby Search** — Finds places within the radius, biased by proximity.
2. **Text Search** — Finds places matching the keyword, biased by location.

This captures both proximity-ranked and relevance-ranked results.

### Cost Model

| API | Cost per Request | Typical Calls per Grid Point |
|-----|------------------|------------------------------|
| Places API (Nearby Search - Basic) | $0.032 | 1 |
| Places API (Text Search - Basic) | $0.032 | 1 |
| SerpAPI | $0.01 | 1 |
| Google Geocoding | $0.005 | 1 (total) |

**Example:** 10km radius ≈ 13 grid points ≈ 26 Places + 13 SerpAPI = ~$0.96

---

## Deduplication Strategy

### Two-Phase Dedup

1. **Phase 1: place_id match** (exact)
   - Group all leads by Google Place ID.
   - Merge fields: keep non-null values, prefer Places API data.

2. **Phase 2: Fuzzy match** (for leads without place_id)
   - Compare name similarity (threshold: 85% via fuzz.ratio).
   - Verify geographic proximity (< 100m apart).
   - Merge if both conditions pass.

### Field Merging

When merging two records for the same business:
- Keep non-null values from either source.
- For list fields (types, photos), merge unique items.
- Track combined source (e.g., "places_api+serp_api").
