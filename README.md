# RunningStats

Site privé de statistiques Garmin (course et trail) pour un groupe de 5 amis maximum : stats perso, profils, comparaison, courses à venir, prédiction de temps, fiche de course et analyses IA.

## Organisation du dépôt

```
runningstats/
├── backend/            API FastAPI + PostgreSQL (Python, uv)        → backend/README.md
├── frontend/           SPA SvelteKit (TypeScript, pnpm)             → frontend/README.md
├── docker-compose.yml  PostgreSQL 17 pour le dev
├── Makefile            commandes courantes
├── .env.example        variables d'environnement (copier en .env)
└── CLAUDE.md           résumé du projet et conventions
```

## Infra en dev

```
navigateur ──► :5173  Vite (front SvelteKit)
                 │  /api/*  (proxy)
                 ▼
               :8000  FastAPI ──► :5433  PostgreSQL 17 (Docker, volume pgdata)
```

Le navigateur ne parle qu'à une seule origine : le front redirige `/api` vers le back. Le cookie de session reste donc sur le même domaine, sans configuration CORS.

| Service | Port | Lancé par |
| --- | --- | --- |
| Front (Vite) | 5173 | `make web` |
| API (FastAPI) | 8000 | `make api` |
| PostgreSQL | 5433 (5432 dans le conteneur) | `make db` |

Le port 5433 évite un conflit avec un autre PostgreSQL local sur le 5432 ; il se change dans `.env` (`POSTGRES_PORT` et `DATABASE_URL`).

## Prérequis

- Docker avec Docker Compose
- [uv](https://docs.astral.sh/uv/) (installe lui-même Python 3.12)
- Node.js 20.19 ou plus
- pnpm 10 (`npm i -g pnpm@10`) ; pnpm 8 refuse d'installer les dépendances

## Démarrage

```bash
make install   # .env + dépendances back et front
make dev       # base + API + front ; ouvrir http://localhost:5173
```

`make help` liste les autres commandes (`test`, `lint`, `format`, `migrate`, `db-stop`…).

## Conception

Les décisions fonctionnelles et techniques sont dans trois documents :

- [Besoins du back](https://claude.ai/artifact/DHRGJpKJtagCU7ASJghoBD) : tables, endpoints, tâches de fond
- [Prédiction et conseils](https://claude.ai/artifact/De8tLPuXtpcBxH3hxnWLPt)
- [Maquettes](https://claude.ai/artifact/MAHSw1opRbUcHhiJN14qf6) : 13 écrans

Le déploiement en production n'est pas encore décidé.
