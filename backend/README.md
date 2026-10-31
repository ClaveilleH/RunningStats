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
- **Worker** (`make worker`, ou `uv run python -m app.worker`) : un second processus qui exécute les tâches longues (synchro Garmin, traitement des activités, prédictions, analyses IA). Pas de Redis : à cette échelle, PostgreSQL suffit comme file.
  - **File** : table `jobs`. `app/jobs.py` gère la mise en file (`enqueue`, `enqueue_unless_queued`), la prise d'une tâche avec `SELECT … FOR UPDATE SKIP LOCKED` et les réessais.
  - **Tâches** : une fonction par type dans `app/tasks/`, enregistrée avec `@task("nom", retry_delays=…)`. Elle lève `RetryableError` pour un échec passager (relancée après 1, 5 puis 30 min pour Garmin). Toute autre exception la met en échec tout de suite, et ses écritures sont annulées.
  - **Planificateur** : APScheduler tourne dans le worker et se contente de mettre des tâches en file (maintenance chaque nuit à 3 h, fuseau `TIMEZONE`, par défaut Europe/Paris).
  - **Arrêt** : `Ctrl+C` / `SIGTERM` termine la tâche en cours puis s'arrête. Au redémarrage, une tâche coupée en plein milieu est remise en file.
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
- **Appels** : toujours via `garmin.call(db, account, fn)`. La fonction attend 0,5 s entre deux requêtes, renouvelle le jeton une fois sur un 401, et traduit les erreurs : 429, 5xx et réseau deviennent `GarminUnavailable` (tâche réessayée) ; un refus répété devient `GarminKeyRejected` (statut `error`).
- **Synchro** (`app/tasks/garmin_sync.py`) :
  1. `garmin_sync` parcourt la liste des activités, des plus récentes aux plus anciennes, et ne garde que `running`, `trail_running` et `track_running`. Tant que l'historique n'a pas été lu en entier (`sync_cursor.history_complete`), elle lit toutes les pages. Ensuite, elle s'arrête à la première activité déjà connue. Chaque page est commitée, donc une synchro coupée reprend sans rien perdre.
  2. Chaque nouvelle activité met en file une tâche `process_activity`. Elle télécharge le FIT, le garde brut dans `DATA_DIR/fit/<membre>/<id Garmin>.zip`, puis enregistre les points (`activity_points`, environ 1 par seconde) et les tours de la montre (`activity_laps`, type `lap`).
  3. À la fin, `garmin_sync` met en file `garmin_health` (`app/tasks/garmin_health.py`, conversion dans `app/health.py`). C'est une tâche à part : si elle échoue, les activités sont quand même gardées.
- **Santé** :
  - Tables :
    - `sleep_nights` : une nuit par date de réveil, avec les durées par phase, le score et le JSON brut ;
    - `daily_health` : pas, FC au repos, Body Battery min / max et VFC ;
    - `weights` : une ligne par pesée Garmin, en kg (Garmin envoie des grammes).
  - Lecture : tout l'historique la première fois (depuis la première activité, ou un an s'il n'y en a pas), puis les 3 derniers jours, comme le prévoit la doc. Si le worker a été arrêté, la lecture reprend depuis la dernière date lue (`sync_cursor.health_until`).
  - Limites de Garmin pour un appel, mesurées le 31/10/2026 :

    | Appel | Période max |
    |---|---|
    | sommeil | 31 jours |
    | résumés du jour (pas, FC au repos, Body Battery) | 366 jours |
    | VFC, poids | longues périodes acceptées |

  - L'appel « pas » (28 jours max) n'est pas utilisé : les pas sont déjà dans les résumés du jour.
  - Garmin répond HTTP 429 au-delà d'environ 100 appels par minute. L'historique est donc lu par tranches d'un an (environ 15 appels), chacune enregistrée tout de suite ; après une erreur 429, la tâche réessaie et reprend à la tranche suivante.
  - VFC : la montre testée n'en fournit pas (Garmin renvoie `null`). Le format lu (`hrvSummaries[].lastNightAvg`) est donc supposé, et `hrv_ms` reste vide sinon.
  - L'enregistrement est un upsert : une valeur absente ne vient pas effacer une valeur connue.
- **Déclenchement** :
  - à l'enregistrement de la clé (`PUT /api/me/garmin` renvoie `sync_job_id`) ;
  - par le bouton (`POST /api/me/sync`, réponse 202 avec l'id de la tâche) ;
  - **automatiquement** : toutes les 5 min, le worker regarde quels membres sont dus (`app/sync_schedule.py`). Un membre est dû quand sa fréquence est écoulée (la sienne ou celle du groupe, 1 h par défaut) depuis sa dernière synchro réussie **ou** lancée : une synchro qui échoue n'est donc pas relancée toutes les 5 min. Rien pendant la pause de nuit (0 h – 6 h, fuseau du groupe). Les comptes en statut `error` ou `key_expired` sont suspendus. Le passage à 10 min les jours de course attend les tables des courses.
- **Clés qui expirent** : la tâche `check_garmin_keys` (chaque jour à 7 h) passe les clés expirées en `key_expired`. La ligne dans le journal admin viendra avec `audit_log`.
- **Retraitement sans Garmin** : `process_activity` avec `use_local_fit: true` relit le FIT gardé sur disque.

## Calculs sur les activités (`app/metrics.py`)

Lancés à la fin de `process_activity`, et pour toutes les activités par la tâche `recompute_metrics` (mise en file automatiquement quand l'admin change les seuils).

- **Catégorie** (`road`, `short_trail`, `long_trail`, `mixed`), d'après le type Garmin et le D+ par km :
  - piste : route ;
  - D+/km au-dessus du seuil trail : trail ;
  - D+/km sous le seuil route : route ;
  - entre les deux : mixte.
  - Une sortie marquée « trail » sur la montre passe d'un cran vers le trail : vallonnée, elle compte comme trail ; plate, elle compte comme mixte.
  - Un trail est long à partir d'un certain km-effort.
- **km-effort** : km + D+ / 100.
- **Splits par km** (`activity_laps`, type `km`) : bornes interpolées entre deux points, durée en **temps chrono** (sans les pauses lues dans les événements `timer` du FIT). Le D+ / D- suit le profil d'altitude du FIT (seuil de 1 m), puis il est mis à l'échelle pour que le total égale le D+ / D- officiel de Garmin.
- **Trace** : `activities.calc_trace` garde la méthode, la version, les paramètres et les entrées de chaque calcul.

## Liste des activités (`app/activity_list.py`)

- `GET /api/users/{id}/activities` : filtres `category` (road, short_trail, long_trail, mixed), `q` (nom ou lieu), `from` / `to` (dates locales de la montre, incluses), tri `sort` (date, distance, elevation, duration) et `order`, pagination `page` / `page_size` (20 par défaut, 100 max).
  - La réponse donne aussi `summary`, les totaux de toute la sélection (sorties, distance, D+, temps), pas seulement ceux de la page.
  - L'allure (`pace_s_per_km`) se calcule sur `duration_s` : chez Garmin, c'est le temps chrono, pauses exclues.
  - `with_track=true` ajoute un tracé simplifié d'environ 60 points par activité, pour les vignettes de la vue cartes.
- `GET /api/users/{id}/activities/weekly?weeks=12` : km, D+ et nombre de sorties par semaine (lundi → dimanche, heure locale), semaines vides comprises, la semaine en cours en dernier (`current`).
- Pour l'instant, chacun ne voit que ses activités (403 sinon). Celles des amis passeront par le filtre de `privacy_settings`, pas encore construit.

## Fiche d'une activité (`app/activity_detail.py`)

- `GET /api/activities/{id}` : le résumé, les splits par km (`km_splits`), les tours de la montre (`laps`), les zones FC de Garmin, et des détails tirés du résumé Garmin (temps écoulé et arrêté, cadence, calories, altitude min / max). `processed` vaut faux tant que le FIT n'a pas été lu.
- `GET /api/activities/{id}/points?step=25` : un point tous les `step` mètres (5 à 1 000), en colonnes (distance, temps chrono, lat / lon, altitude, FC, cadence, allure). Le dernier point est toujours gardé.
  - L'allure est le temps chrono sur ±100 m autour du point : les pauses n'y comptent pas. Au-delà de 30 min/km (arrêt, marche très lente), elle reste vide.
- `PUT` / `DELETE /api/activities/{id}/pin` : épingle ou désépingle la sortie sur le profil.
- L'activité d'un autre membre répond 404, comme si elle n'existait pas, en attendant la confidentialité.

## Réglages du groupe (`app/settings.py`)

- Table `app_settings` : une ligne par réglage, avec une valeur JSON. Chaque réglage est un modèle Pydantic dont les valeurs par défaut viennent de la doc ; la base ne garde que ce que l'admin a changé.
- `GET /api/admin/settings` renvoie tout, valeurs par défaut comprises. `PUT /api/admin/settings` modifie un réglage en partie, après validation (seuils dans le bon ordre, champs connus).
- Réglages existants : `activity_categories` (route < 10 m/km, trail ≥ 25 m/km, trail long ≥ 42 km-effort) et `sync_schedule` (toutes les 60 min, pause de 0 h à 6 h, 10 min les jours de course).
- À ne pas confondre avec `app/config.py`, qui contient la configuration technique lue dans l'environnement.
- **Tests** : faux Garmin dans `tests/garmin_fakes.py` (liste d'activités, FIT synthétiques générés avec `fit-tool`, erreurs HTTP à la demande). Aucun appel réseau.

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
