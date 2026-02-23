# Deployment Guide

## Docker Compose (Self-Hosted / VPS)

The simplest deployment option. Works on any Linux VPS with Docker installed.

### Requirements

- Linux VPS (Ubuntu 22.04+ recommended)
- 2+ GB RAM, 2+ vCPU
- Docker & Docker Compose installed
- Domain name (optional, for HTTPS)

### Steps

```bash
# 1. Clone to your server
git clone <repo-url> /opt/gmaps-scraper
cd /opt/gmaps-scraper

# 2. Configure environment
cp .env.example .env
nano .env
# Set production values:
#   SECRET_KEY=<random-64-char-string>
#   BACKEND_CORS_ORIGINS=["https://your-domain.com"]
#   NEXT_PUBLIC_API_URL=https://your-domain.com

# 3. Build and start
docker compose up -d --build

# 4. Verify
curl http://localhost:8000/health
```

### Reverse Proxy (Nginx)

For HTTPS, place Nginx in front:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

---

## Dokploy (Production)

Deployment with custom domains:

- **Frontend:** `https://gmapscraper.apexneural.cloud` (port **3334**)
- **Backend API:** `https://gmapscraperapi.apexneural.cloud` (port **8554**)

CORS is configured to allow the frontend origin by default. Override via `BACKEND_CORS_ORIGINS` if needed.

Ports are controlled by `FRONTEND_PORT` and `BACKEND_PORT` in the root `.env` used by Docker Compose. Set them for production so the reverse proxy (e.g. Dokploy) can map the domains to the correct container ports.

### Root `.env` (Docker Compose – production)

Set the host ports used when running `docker compose`:

```env
# Production ports (host mapping)
FRONTEND_PORT=3334
BACKEND_PORT=8554
```

- **`FRONTEND_PORT`** – Host port for the frontend container (default dev: 3000). Production: **3334**.
- **`BACKEND_PORT`** – Host port for the backend container (default dev: 8000). Production: **8554**.

### Redis and database on Dokploy

The default `redis_url` is `redis://redis:6379/0`. The hostname **`redis`** only resolves inside Docker Compose. On Dokploy you must:

1. **Deploy a Redis service** (e.g. Dokploy’s Redis template, or use an external Redis like Upstash / Redis Cloud).
2. **Set `REDIS_URL`** in the backend and Celery worker env to a URL the backend/worker can reach, for example:
   - Internal Redis: `redis://<redis-service-host>:6379/0` (use the host Dokploy gives for the Redis service).
   - External Redis: `redis://default:YOUR_PASSWORD@your-redis-host:6379/0` or the URL your provider gives you.

If `REDIS_URL` is wrong or Redis is not deployed, you will see:  
`Error -2 connecting to redis:6379. Name or service not known` and job creation will fail (Celery needs Redis as broker).

Same idea for **Postgres**: set `DATABASE_URL` and `DATABASE_URL_SYNC` to your real DB URLs (not `db:5432` unless that hostname exists in your Dokploy network).

### Backend `.env` (on production server)

Set these (and other vars from `.env.example`):

```env
# Required for Dokploy domains
BACKEND_CORS_ORIGINS=["https://gmapscraper.apexneural.cloud"]
APP_BASE_URL=https://gmapscraper.apexneural.cloud
API_BASE_URL=https://gmapscraperapi.apexneural.cloud

# Required: use URLs reachable from your backend/worker (not docker hostnames unless in same network)
SECRET_KEY=<your-secure-random-key>
DATABASE_URL=postgresql+asyncpg://USER:PASS@YOUR_DB_HOST:5432/DATABASE
DATABASE_URL_SYNC=postgresql+psycopg2://USER:PASS@YOUR_DB_HOST:5432/DATABASE
REDIS_URL=redis://YOUR_REDIS_HOST:6379/0
```

- **`REDIS_URL`** – **Must** point to a Redis instance the backend and Celery worker can connect to (see “Redis and database on Dokploy” above).
- **`BACKEND_CORS_ORIGINS`** – Must include the frontend origin. Use a JSON array, e.g. `["https://gmapscraper.apexneural.cloud"]`.
- **`APP_BASE_URL`** – Base URL of the frontend (used for email links, etc.).
- **`API_BASE_URL`** – Base URL of the backend API (used for links in emails/notifications).

### Frontend `.env` (on production server)

Set the public API URL so the app talks to your backend:

```env
NEXT_PUBLIC_API_URL=https://gmapscraperapi.apexneural.cloud
```

- **`NEXT_PUBLIC_API_URL`** – Must be the public URL of the backend (e.g. `https://gmapscraperapi.apexneural.cloud`). No trailing slash. This is baked in at build time, so rebuild the frontend after changing it.

---

## Railway

Railway supports Docker-based deployments with managed PostgreSQL and Redis.

### Steps

1. Create a new Railway project.
2. Add a **PostgreSQL** service — copy the `DATABASE_URL`.
3. Add a **Redis** service — copy the `REDIS_URL`.
4. Add a service from your GitHub repo for the **backend**:
   - Set root directory to `backend/`.
   - Set start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add environment variables from `.env.example`.
5. Add another service for the **Celery worker**:
   - Same repo, root directory `backend/`.
   - Start command: `celery -A app.tasks worker --loglevel=info`
   - Same environment variables.
6. Add a service for the **frontend**:
   - Root directory: `frontend/`.
   - Set `NEXT_PUBLIC_API_URL` to the backend's Railway URL.
7. Deploy.

---

## Render

### Backend (Web Service)

1. Create a new **Web Service** from your repo.
2. Root directory: `backend`
3. Runtime: Docker
4. Add environment variables from `.env.example`.
5. Add a **PostgreSQL** database — use its internal URL for `DATABASE_URL`.
6. Add a **Redis** instance — use its internal URL for `REDIS_URL`.

### Celery Worker (Background Worker)

1. Create a new **Background Worker** from the same repo.
2. Root directory: `backend`
3. Start command: `celery -A app.tasks worker --loglevel=info`
4. Same environment variables as the backend.

### Frontend (Static Site or Web Service)

1. Create a new **Web Service**.
2. Root directory: `frontend`
3. Build command: `npm run build`
4. Start command: `npm start`
5. Set `NEXT_PUBLIC_API_URL` to the backend service URL.

---

## Environment Variables Checklist

| Variable | Required | Notes |
|----------|----------|-------|
| FRONTEND_PORT | No | Host port for frontend (default: 3000). Production: 3334 |
| BACKEND_PORT | No | Host port for backend (default: 8000). Production: 8554 |
| GOOGLE_MAPS_API_KEY | Yes | Google Cloud Console |
| SERPAPI_KEY | Recommended | serpapi.com |
| DATABASE_URL | Yes | PostgreSQL async URL |
| DATABASE_URL_SYNC | Yes | PostgreSQL sync URL |
| REDIS_URL | Yes | Redis connection URL |
| SECRET_KEY | Yes | Random string for production |
| BACKEND_CORS_ORIGINS | Yes | JSON array of allowed origins |
| NEXT_PUBLIC_API_URL | Yes | Public URL of the backend API |
| APP_BASE_URL | No | Frontend base URL (emails, etc.) |
| API_BASE_URL | No | Backend base URL (emails, etc.) |
| PLACES_API_RPS | No | Default: 10 |
| SERP_API_RPS | No | Default: 5 |
