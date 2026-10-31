# RunningStats

Site privé de statistiques Garmin, course et trail uniquement, pour un groupe de 5 amis maximum.
Stats perso, profil, comparaison entre amis, courses à venir, prédiction de temps et fiche de course, analyses IA.

## Documents de conception (source de vérité)

- Besoins du back (tables, endpoints, tâches de fond) : https://claude.ai/artifact/DHRGJpKJtagCU7ASJghoBD
- Prédiction et conseils : https://claude.ai/artifact/De8tLPuXtpcBxH3hxnWLPt
- Maquettes (13 écrans) : https://claude.ai/artifact/MAHSw1opRbUcHhiJN14qf6

En cas de doute sur une règle métier, se référer à ces docs plutôt qu'improviser.

## Stack

- `backend/` : Python 3.12+, FastAPI, SQLAlchemy 2 (sync, psycopg 3) + Alembic, PostgreSQL. Géré avec **uv**.
  - `app/main.py` (app + routeur `/api`), `app/config.py` (réglages lus depuis le `.env` racine), `app/db.py` (`Base`, session, `get_db`), `app/models/` (tables, toutes importées dans `__init__`), `app/schemas.py` (Pydantic), `app/api/` (un module par groupe de routes, `deps.py` pour `DbSession` / `CurrentUser` / `AdminUser`), logique métier dans des modules `app/<domaine>.py` (ex. `accounts.py`), `migrations/` (Alembic), `tests/`.
  - Erreurs métier : lever `AccessError(message_fr, status)` ; les routes restent fines et font le `commit`.
  - Tests : base `runningstats_test` créée et migrée par `tests/conftest.py`, tables vidées après chaque test.
  - Migrations : `uv run alembic revision --autogenerate -m "..."` puis `uv run alembic upgrade head`.
- `frontend/` : SvelteKit 3 + Svelte 5 (runes) en **SPA**, TypeScript, ESLint + Prettier. Géré avec **pnpm 10** (épinglé dans `packageManager` ; pnpm 8 refuse d'installer).
  - Config Vite + SvelteKit dans `vite.config.ts` : adapter-static avec `fallback: 'index.html'`, proxy `/api` → `:8000` en dev.
  - `src/routes/+layout.ts` : `ssr = false`, `prerender = false`. Alias d'import `#lib/*` → `src/lib/*`, **avec l'extension** (`#lib/api.ts`).
  - Routes : `(public)/` sans connexion (login, invitation), `(app)/` réservé aux membres (redirection vers `/login?next=`).
  - Liens et `goto()` via `resolve()` de `$app/paths` avec l'id de route (`resolve('/(public)/login')`). Appels API via `#lib/api.ts`.
  - Style : variables CSS de `src/app.css` reprises des maquettes (clair / sombre), polices Barlow / Barlow Condensed en local.
- `docker-compose.yml` : PostgreSQL 17 pour le dev, exposé sur le port **5433**.
- Tâches de fond : un processus worker à part (`app/worker.py`), APScheduler + file dans la table `jobs` (`SELECT … FOR UPDATE SKIP LOCKED`). Pas de Redis. Nouvelle tâche = une fonction `@task(...)` dans `app/tasks/`, importée dans `app/tasks/__init__.py` ; `RetryableError` pour un échec passager.

## Commandes

```bash
cp .env.example .env              # une fois
docker compose up -d db           # base de dev

# backend
cd backend && uv sync
uv run fastapi dev app/main.py    # API sur :8000
uv run python -m app.worker       # worker des tâches de fond
uv run pytest
uv run ruff check . && uv run ruff format .

# frontend
cd frontend && pnpm install
pnpm dev                          # :5173, /api proxifié vers :8000
pnpm check && pnpm lint
```

## Conventions

### Langue
- Code, noms de tables/colonnes, routes, commits : anglais.
- Textes de l'interface, docs et commentaires utiles au métier : français.

### Données
- Unités en base : distances en **m**, durées en **s**, dénivelés en **m**.
- Dates en **UTC** en base ; le fuseau local de l'activité est gardé à part.
- Périmètre : types Garmin `running`, `trail_running` et `track_running` seulement (`trail_running` ajouté le 31/10/2026, absent de la doc du back). Tout le reste est ignoré, tapis (`treadmill_running`) compris.
- Chaque valeur calculée garde sa trace : méthode, paramètres, version (sert au futur bouton « Explication »).
- Seuils et réglages métier (route/trail, sommeil 50/30/20, règles de conseils…) vivent dans `app_settings`, jamais en dur dans le code.

### API
- Toutes les routes sous `/api`. Session par cookie HttpOnly ; tout exige un membre connecté, `/api/admin/*` exige le rôle admin.
- Confidentialité : toute donnée d'un autre membre passe par le filtre serveur des `privacy_settings`. Une stat masquée revient en `null` + `hidden: true`, jamais en clair.
- Tâches longues (synchro, analyse IA, prédiction) : la route répond `202` + id de tâche, suivi par `GET /api/jobs/{id}`.

### IA
- Le code calcule et détecte ; le LLM explique et rédige. La synthèse des prédictions est un calcul, pas une sortie du LLM.
- Prompts : modèles fixes versionnés dans le code (Jinja2), remplis avec des données structurées.
- Chaque appel LLM est tracé dans `ai_analyses` (modèle, version du prompt, jetons, coût).

### Secrets
- Clés et jetons Garmin chiffrés en base ; la clé maître est une variable d'environnement, jamais en base ni dans le dépôt.
- `.env` n'est jamais commité ; `.env.example` liste les variables.

## Façon de travailler

- Avancer par petites étapes et attendre la validation avant de passer à la suivante.
- Pas de logique métier sans la doc correspondante ; signaler les écarts avec les docs de conception.
