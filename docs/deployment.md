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
| GOOGLE_MAPS_API_KEY | Yes | Google Cloud Console |
| SERPAPI_KEY | Recommended | serpapi.com |
| DATABASE_URL | Yes | PostgreSQL async URL |
| DATABASE_URL_SYNC | Yes | PostgreSQL sync URL |
| REDIS_URL | Yes | Redis connection URL |
| SECRET_KEY | Yes | Random string for production |
| BACKEND_CORS_ORIGINS | Yes | JSON array of allowed origins |
| NEXT_PUBLIC_API_URL | Yes | Public URL of the backend API |
| PLACES_API_RPS | No | Default: 10 |
| SERP_API_RPS | No | Default: 5 |
