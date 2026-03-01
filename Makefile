.PHONY: dev build up down logs migrate migrate-create test lint format clean shell-backend shell-frontend

# Development
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Production
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# Database
migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

# Testing
test:
	docker compose exec backend pytest -v

# Code quality
lint:
	docker compose exec backend ruff check .
	cd frontend && npm run lint

format:
	docker compose exec backend ruff format .

# Shell access
shell-backend:
	docker compose exec backend bash

shell-frontend:
	docker compose exec frontend sh

# Cleanup
clean:
	docker compose down -v --remove-orphans
	docker system prune -f
