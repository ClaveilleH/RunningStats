.PHONY: help install db db-stop api worker web dev migrate admin test lint format

help: ## Liste les commandes
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

install: ## Installe les dépendances back et front (+ .env si absent)
	@test -f .env || cp .env.example .env
	cd backend && uv sync
	cd frontend && pnpm install

db: ## Démarre PostgreSQL (port 5433)
	docker compose up -d --wait db

db-stop: ## Arrête PostgreSQL (les données restent dans le volume)
	docker compose stop db

api: ## Lance l'API en dev sur :8000
	cd backend && uv run fastapi dev app/main.py --port 8000

worker: ## Lance le worker des tâches de fond
	cd backend && uv run python -m app.worker

web: ## Lance le front en dev sur :5173
	cd frontend && pnpm dev --port 5173

dev: db ## Base + API + worker + front en parallèle (Ctrl+C arrête tout)
	$(MAKE) -j3 api worker web

migrate: ## Applique les migrations Alembic
	cd backend && uv run alembic upgrade head

admin: ## Crée le compte admin (demande email, nom, mot de passe)
	cd backend && uv run python -m app.cli create-admin

test: ## Tests du back (base runningstats_test créée au besoin)
	cd backend && uv run pytest

lint: ## Lint et vérif de types, back et front
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm check && pnpm lint

format: ## Formate le code, back et front
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && pnpm format
