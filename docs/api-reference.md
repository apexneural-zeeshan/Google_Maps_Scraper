# API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

## Health

### GET /health

Check API health status.

**Response:** `200 OK`

```json
{ "status": "ok" }
```

---

## Jobs

### POST /api/jobs/

Create a new scrape job.

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| keyword | string | Yes | — | Business type or search term |
| location | string | Yes | — | Address or city name |
| location_type | string | No | "address" | "address" or "coordinates" |
| radius_km | float | No | 5.0 | Search radius in km (0–50) |
| latitude | float | No | null | Required if location_type="coordinates" |
| longitude | float | No | null | Required if location_type="coordinates" |

**Example:**

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "restaurants",
    "location": "Austin, TX",
    "radius_km": 5.0
  }'
```

**Response:** `201 Created`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "keyword": "restaurants",
  "location": "Austin, TX",
  "location_type": "address",
  "radius_km": 5.0,
  "latitude": null,
  "longitude": null,
  "progress": 0,
  "current_step": null,
  "total_found": 0,
  "total_unique": 0,
  "places_api_calls": 0,
  "serp_api_calls": 0,
  "estimated_cost_usd": 0.0,
  "celery_task_id": "abc123",
  "error_message": null,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

---

### GET /api/jobs/

List all jobs (paginated, ordered by creation date descending).

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| skip | int | 0 | Offset for pagination |
| limit | int | 50 | Number of results (max 200) |

**Response:** `200 OK`

```json
{
  "items": [ /* JobResponse[] */ ],
  "total": 42,
  "skip": 0,
  "limit": 50
}
```

---

### GET /api/jobs/{job_id}

Get details of a specific job.

**Response:** `200 OK` — JobResponse

**Errors:** `404` if job not found.

---

### DELETE /api/jobs/{job_id}

Cancel a running job and revoke its Celery task.

**Response:** `200 OK` — JobResponse with status="cancelled"

**Errors:**
- `404` if job not found.
- `409` if job is already in a terminal state (completed/failed/cancelled).

---

## Results

### GET /api/results/{job_id}

Get leads for a job (paginated, sortable, filterable).

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| skip | int | 0 | Offset for pagination |
| limit | int | 50 | Number of results (max 200) |
| sort_by | string | "name" | Sort field: name, rating, review_count, created_at |
| sort_order | string | "asc" | "asc" or "desc" |
| search | string | null | Filter by name (case-insensitive) |
| has_phone | bool | null | Filter: true=has phone, false=no phone |
| has_website | bool | null | Filter: true=has website, false=no website |
| min_rating | float | null | Minimum rating filter (0–5) |

**Response:** `200 OK`

```json
{
  "items": [ /* LeadResponse[] */ ],
  "total": 98,
  "skip": 0,
  "limit": 50
}
```

---

### GET /api/results/{job_id}/export

Export leads as a CSV file.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| template | string | "default" | "default" (all fields) or "clay" (Clay-compatible) |

**Response:** `200 OK` — CSV file download

**Default template columns:** place_id, name, address, phone, website, rating, review_count, business_type, types, latitude, longitude, price_level, business_status, maps_url, source

**Clay template columns:** Company Name, Website, Phone Number, Address, Rating, Reviews

---

### GET /api/results/{job_id}/stats

Get aggregate statistics for a job's results.

**Response:** `200 OK`

```json
{
  "job_id": "550e8400-...",
  "total_leads": 98,
  "unique_place_ids": 98,
  "sources": { "places_api": 75, "serp_api": 23 },
  "avg_rating": 4.2,
  "with_phone": 82,
  "with_website": 65,
  "with_email": 0,
  "business_types": { "restaurant": 45, "cafe": 12 }
}
```
