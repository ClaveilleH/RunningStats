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
- Node.js 22.17 minimum dans la branche 22.x, ou 24+ (SvelteKit 3 ne supporte pas Node 20)
- pnpm 10 (`npm i -g pnpm@10.34.9`), version épinglée dans `frontend/package.json`

`make install` installe les dépendances du projet, mais suppose ces outils déjà disponibles dans le `PATH`.
Sur Linux/macOS, si `uv` manque :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

Installer ensuite pnpm avec la commande ci-dessus, puis lancer `make doctor` pour vérifier les outils et la version de Node.

## Démarrage

```bash
make install   # .env + dépendances back et front
make admin     # une seule fois : base + migrations, puis création du premier compte
make dev       # base + migrations + API + worker + front ; ouvrir http://localhost:5173
```

Se connecter avec le compte créé par `make admin`. Le site est privé : il n'existe pas de formulaire d'inscription libre.
Les lancements suivants ne nécessitent que `make dev` ; les migrations sont appliquées avant le démarrage du worker et de l'API.

Avant de connecter Garmin dans les réglages, générer la clé maître depuis la racine :

```bash
uv run --project backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copier la valeur dans `GARMIN_ENCRYPTION_KEY` du `.env`, puis redémarrer `make dev`.
Conserver cette clé : la remplacer rend illisibles les clés Garmin déjà enregistrées. Elle n'est pas nécessaire pour lancer le site et se connecter.

`make help` liste les autres commandes (`test`, `lint`, `format`, `migrate`, `db-stop`…).

## Dépannage du premier lancement

| Symptôme | Cause et action |
| --- | --- |
| `uv: command not found` ou `pnpm: command not found` | Installer l'outil manquant et vérifier le `PATH` avec `make doctor`. |
| `ERR_PNPM_UNSUPPORTED_ENGINE` | Vérifier Node (22.17+ en 22.x, ou 24+) et pnpm (`10.34.9`). |
| `relation "jobs" does not exist` ou `relation "users" does not exist` | Base non migrée ; lancer `make migrate`. `make dev` et `make admin` le font automatiquement. |
| Page de connexion sans compte utilisable | Lancer `make admin` dans un terminal à la racine. |
| `GARMIN_ENCRYPTION_KEY n'est pas définie` | Renseigner la clé maître comme indiqué ci-dessus, puis redémarrer API et worker. |

## Conception

Les décisions fonctionnelles et techniques sont dans trois documents :

- [Besoins du back](https://claude.ai/artifact/DHRGJpKJtagCU7ASJghoBD) : tables, endpoints, tâches de fond
- [Prédiction et conseils](https://claude.ai/artifact/De8tLPuXtpcBxH3hxnWLPt)
- [Maquettes](https://claude.ai/artifact/MAHSw1opRbUcHhiJN14qf6) : 13 écrans

Le déploiement en production n'est pas encore décidé.
