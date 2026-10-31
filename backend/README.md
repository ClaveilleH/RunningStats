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
│   ├── main.py      app FastAPI, routeur /api, gestion des erreurs métier
│   ├── config.py    réglages (DATABASE_URL, durées de session…), lus depuis ../.env
│   ├── db.py        Base des modèles, convention de nommage des contraintes, session, get_db
│   ├── models/      un fichier par groupe de tables (tous importés dans __init__ pour Alembic)
│   ├── schemas.py   entrées / sorties Pydantic des routes
│   ├── security.py  hash argon2, jetons, normalisation d'email
│   ├── accounts.py  règles d'accès : membres (5 max), invitations, sessions
│   ├── cli.py       commandes d'administration (create-admin)
│   └── api/         un module par groupe de routes ; deps.py = session DB, membre connecté, admin
├── migrations/      Alembic (env.py lit l'URL depuis app.config)
├── tests/           conftest.py crée et migre la base <nom>_test
└── pyproject.toml   dépendances, config ruff et pytest
```

## Connexion et accès

- **Premier compte** : `make admin` (ou `uv run python -m app.cli create-admin`) crée l'admin. Les autres membres arrivent par invitation.
- **Invitation** : l'admin crée un lien (`POST /api/admin/invitations`), valable 7 jours et utilisable une fois. Le groupe est limité à 5 membres, invitations en attente comprises.
- **Session** : à la connexion, un jeton aléatoire est posé dans un cookie `HttpOnly`, `SameSite=Lax`, valable 30 jours. `Secure` s'active par `SESSION_COOKIE_SECURE=true` en production.
- **Stockage** : la base ne garde que le hash SHA-256 des jetons (sessions et invitations), et les mots de passe en argon2. Une copie de la base ne permet donc pas d'ouvrir une session.
- **Mot de passe** : 8 caractères minimum, réglé uniquement par `MIN_PASSWORD_LENGTH` dans `app/security.py` (le front lit la valeur dans les réponses de l'API). Le changer déconnecte les autres appareils.
- **Dépendances de route** : `CurrentUser` (401 sans session) et `AdminUser` (403 si non admin), dans `app/api/deps.py`.

## Garmin

- **Source** : l'API personnelle officielle de Garmin, via la bibliothèque [`garmin-connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python). Elle est synchrone (requests), comme le reste du back.
- **Clé du membre** : saisie dans Réglages (`PUT /api/me/garmin`). Elle est testée tout de suite auprès de Garmin, puis stockée **chiffrée** (Fernet). Une clé refusée n'est pas enregistrée.
- **Jeton** : la clé s'échange contre un jeton JWT de 24 h, lui aussi stocké chiffré. `garmin.ensure_token()` le renouvelle s'il expire dans moins d'1 h. Si Garmin refuse la clé, le statut passe à `key_expired` (date de fin dépassée) ou `error`.
- **Échange de la clé** : fait dans `app/garmin.py`, pas avec `PersonalApiAuthenticator` de la bibliothèque, qui écrirait le jeton en clair dans un fichier de `~/.config`.
- **Clé maître** : `GARMIN_ENCRYPTION_KEY` dans `.env` (voir `.env.example` pour la générer). La perdre rend les clés enregistrées illisibles, et chaque membre devra ressaisir la sienne.
- **Tests** : `_request_token` est remplacé par un faux, aucun appel réseau.

## Commandes

```bash
uv sync                                          # installer
uv run fastapi dev app/main.py                   # API sur :8000, doc sur /api/docs
uv run pytest                                    # tests (base de dev démarrée)
uv run ruff check . && uv run ruff format .      # lint et format
uv run alembic revision --autogenerate -m "..."  # nouvelle migration
uv run alembic upgrade head                      # appliquer
```

Les tests tournent sur une base à part, `runningstats_test`, créée au besoin et migrée par les vraies migrations Alembic. Les tables sont vidées après chaque test. Le conteneur `db` doit tourner (`make db`).

## Règles à respecter

Résumées dans `CLAUDE.md` à la racine : unités (m, s), dates en UTC, filtre de confidentialité sur les données des autres membres, trace de chaque calcul, réglages métier dans `app_settings`, clés Garmin chiffrées avec une clé maître en variable d'environnement.
