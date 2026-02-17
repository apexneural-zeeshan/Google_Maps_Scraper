.PHONY: up down build logs migrate migrate-create test lint format clean init

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	@read -p "Migration message: " msg; \
	docker compose exec backend alembic revision --autogenerate -m "$$msg"

test:
	docker compose exec backend pytest tests/ -v

lint:
	docker compose exec backend ruff check app/ tests/

format:
	docker compose exec backend ruff format app/ tests/

clean:
	docker compose down -v --remove-orphans

init:
	@echo "==> Copying .env.example to .env (if not exists)..."
	@cp -n .env.example .env 2>/dev/null || true
	@echo "==> Building containers..."
	docker compose build
	@echo "==> Starting services..."
	docker compose up -d
	@echo "==> Waiting for database..."
	@sleep 5
	@echo "==> Running migrations..."
	docker compose exec backend alembic upgrade head
	@echo "==> Done! Visit http://localhost:3000"
