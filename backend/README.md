# RunningStats — backend

API REST du site, sous `/api`. Elle synchronise les données Garmin, calcule les stats et prédictions, et appelle le LLM pour les analyses.

## Stack et choix

| Brique | Choix | Pourquoi |
| --- | --- | --- |
| Gestion du projet | uv | Un seul outil pour Python, le venv, les dépendances et le lockfile (`uv.lock`). |
| Python | 3.12 (`.python-version`) | Version stable déjà présente sur la machine. |
| Framework web | FastAPI | Validation par types (Pydantic), doc OpenAPI générée, simple à tester. |
| Base | PostgreSQL 17 | Volume modeste (~600 000 points GPS par membre), JSON natif, et sert aussi de file de tâches. |
| Accès aux données | SQLAlchemy 2 en mode **synchrone**, pilote psycopg 3 | À 5 utilisateurs, l'async n'apporte rien. Le sync est plus simple à écrire et à tester, et le worker réutilise le même code. |
| Migrations | Alembic | Migrations générées depuis les modèles, nommées par date. |
| Configuration | pydantic-settings | Réglages typés, lus depuis le `.env` à la racine du monorepo. |
| Qualité | pytest, ruff | Tests et lint/format en un outil. |

## Infra

- **API** : un processus FastAPI (`fastapi dev` en dev, sur :8000).
- **Worker** (à venir) : un second processus qui exécute les tâches longues (synchro Garmin, traitement des activités, prédictions, analyses IA). Elles sont planifiées par APScheduler et mises en file dans la table `jobs`, lue avec `SELECT … FOR UPDATE SKIP LOCKED`. Pas de Redis : à cette échelle, PostgreSQL suffit.
- **Base** : le conteneur `db` du `docker-compose.yml` à la racine.

Les routes qui lancent une tâche longue répondent `202` avec un id de tâche, suivi par `GET /api/jobs/{id}`.

## Structure

```
backend/
├── app/
│   ├── main.py      app FastAPI, routeur /api
│   ├── config.py    réglages (DATABASE_URL…), lus depuis ../.env
│   ├── db.py        Base des modèles, convention de nommage des contraintes, session, get_db
│   └── api/         un module par groupe de routes (health pour l'instant)
├── migrations/      Alembic (env.py lit l'URL depuis app.config)
├── tests/
└── pyproject.toml   dépendances, config ruff et pytest
```

## Commandes

```bash
uv sync                                          # installer
uv run fastapi dev app/main.py                   # API sur :8000, doc sur /api/docs
uv run pytest                                    # tests (base de dev démarrée)
uv run ruff check . && uv run ruff format .      # lint et format
uv run alembic revision --autogenerate -m "..."  # nouvelle migration
uv run alembic upgrade head                      # appliquer
```

Les tests utilisent pour l'instant la base de dev : `make db` doit tourner.

## Règles à respecter

Résumées dans `CLAUDE.md` à la racine : unités (m, s), dates en UTC, filtre de confidentialité sur les données des autres membres, trace de chaque calcul, réglages métier dans `app_settings`, clés Garmin chiffrées avec une clé maître en variable d'environnement.
