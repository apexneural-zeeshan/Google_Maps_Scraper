# Getting Started

Complete step-by-step setup guide for the Google Maps Scraper.

## Prerequisites

- **Docker** & **Docker Compose** (v2.0+)
- A **Google Cloud** API key with the following APIs enabled:
  - Places API (New)
  - Geocoding API
- A **SerpAPI** API key (optional but recommended)

## Step 1: Clone the Repository

```bash
git clone <repo-url>
cd GMaps_Scraper
```

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Open `.env` and fill in your API keys:

```env
GOOGLE_MAPS_API_KEY=AIza...your-key-here
SERPAPI_KEY=your-serpapi-key-here
```

All other values have sensible defaults for local development.

## Step 3: Start the Application

```bash
make init
```

This will:
1. Build all Docker containers.
2. Start PostgreSQL, Redis, Backend, Celery Worker, Flower, and Frontend.
3. Run database migrations.

## Step 4: Verify Everything is Running

Visit these URLs:

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:3000 | Web UI |
| Backend API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Flower | http://localhost:5555 | Celery task monitor |

Check the health endpoint:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Step 5: Run Your First Scrape

1. Open http://localhost:3000
2. Enter a location (e.g., "Austin, TX")
3. Enter a keyword (e.g., "restaurants")
4. Set the search radius (e.g., 5 km)
5. Click **Start Scraping**
6. Watch the progress in real-time
7. Export results as CSV when complete

## Step 6: View Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f backend
docker compose logs -f celery_worker
```

## Stopping the Application

```bash
make down          # Stop containers (data preserved)
make clean         # Stop containers AND delete volumes (data lost)
```

## Troubleshooting

### "Connection refused" on backend

The backend may still be starting. Wait a few seconds and try again.
Check logs with `docker compose logs backend`.

### Database migration errors

```bash
make migrate
```

### Celery tasks stuck in "pending"

Check that the Celery worker is running:

```bash
docker compose logs celery_worker
```

### API key errors

Verify your keys are set in `.env` and that the required Google APIs
are enabled in the Google Cloud Console.
