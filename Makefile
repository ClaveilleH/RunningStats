.PHONY: help doctor install db db-stop api worker web dev migrate admin test lint format

help: ## Liste les commandes
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

doctor: ## Vérifie les outils nécessaires au démarrage
	@missing=0; for tool in uv node pnpm docker; do \
		command -v $$tool >/dev/null 2>&1 || { echo "Outil absent : $$tool (voir README.md, Prérequis)"; missing=1; }; \
	done; test $$missing -eq 0
	@node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (!(major === 22 && minor >= 17 || major >= 24)) { console.error("Node.js 22.17+ (22.x) ou 24+ requis par le front."); process.exit(1); }'
	@docker compose version >/dev/null

install: doctor ## Installe les dépendances back et front (+ .env si absent)
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

dev: doctor ## Migre la base puis lance API + worker + front (Ctrl+C arrête tout)
	$(MAKE) migrate
	$(MAKE) -j3 api worker web

migrate: db ## Démarre la base et applique les migrations Alembic
	cd backend && uv run alembic upgrade head

admin: migrate ## Prépare la base puis crée l'admin (email, nom, mot de passe)
	cd backend && uv run python -m app.cli create-admin

test: ## Tests du back (base runningstats_test créée au besoin)
	cd backend && uv run pytest

lint: ## Lint et vérif de types, back et front
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm check && pnpm lint

format: ## Formate le code, back et front
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && pnpm format
