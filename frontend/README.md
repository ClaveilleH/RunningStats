# RunningStats — frontend

Interface du site : une application d'une seule page (SPA) qui appelle l'API sous `/api`.

## Stack et choix

| Brique    | Choix                                    | Pourquoi                                                                                                                                           |
| --------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Framework | SvelteKit 3 + Svelte 5 (runes)           | Routage par fichiers, peu de code pour des pages riches en graphiques, bon outillage TypeScript.                                                   |
| Rendu     | **SPA**, sans SSR                        | Site privé derrière une connexion : pas de référencement à gérer, aucun serveur Node en production. Le build est un dossier de fichiers statiques. |
| Adapter   | adapter-static, `fallback: 'index.html'` | Toutes les URL renvoient vers `index.html` et le routage se fait dans le navigateur.                                                               |
| Langage   | TypeScript                               | Les réponses de l'API sont typées.                                                                                                                 |
| Qualité   | svelte-check, ESLint, Prettier           | Vérif de types, lint et format.                                                                                                                    |
| Paquets   | pnpm 10, épinglé dans `packageManager`   | Rapide et strict. Une dépendance d'ESLint refuse pnpm 8.                                                                                           |

## Infra

- **En dev** : Vite sur :5173. Le proxy de `vite.config.ts` envoie `/api/*` vers FastAPI sur :8000.
- **En production** (à décider) : `pnpm build` produit `build/`, à servir en statique sur le même domaine que l'API.

Front et API partagent une seule origine. Le cookie de session HttpOnly marche donc sans CORS, et le code appelle toujours des chemins relatifs (`fetch('/api/...')`).

## Structure

```
frontend/
├── src/
│   ├── app.html                 page HTML de base (lang="fr")
│   ├── app.css                  couleurs des maquettes (clair / sombre), polices, styles de formulaire
│   ├── lib/
│   │   ├── api.ts               appels /api, messages d'erreur en français, fetchMe, safeNext
│   │   ├── garmin.svelte.ts     état Garmin du membre et suivi de la synchro (GarminSync)
│   │   ├── format.ts            nombres, distances, durées, allures et dates en français
│   │   ├── activities.ts        types et libellés des activités, périodes, vignette du tracé
│   │   ├── races.ts             types des courses, compte à rebours
│   │   ├── avatar.ts            initiales et couleur d'un membre
│   │   └── components/          composants partagés (Brand, SyncButton, RouteMap, DistanceChart…)
│   └── routes/
│       ├── +layout.ts           ssr = false, prerender = false (mode SPA)
│       ├── +layout.svelte       polices et CSS globaux
│       ├── (public)/            pages sans connexion : /login, /invitation/[token]
│       └── (app)/               pages réservées aux membres ; +layout.ts redirige vers /login sinon
│           ├── activities/      liste des activités (filtres, résumé, graphique, tableau / cartes)
│           │   └── [id]/        fiche d'une activité (carte, profil, onglets)
│           ├── races/           courses à venir (liste, calendrier, passées), new/ et [id]/edit/
│           └── settings/        Réglages (pour l'instant : Garmin et données)
├── static/
├── vite.config.ts               config Vite et SvelteKit (adapter, proxy)
└── package.json
```

## Connexion

- `(app)/+layout.ts` appelle `GET /api/me`. Sans session, il redirige vers `/login?next=<page demandée>`, puis on revient sur cette page après connexion.
- `/invitation/[token]` vérifie le lien, puis crée le compte. Le nouveau membre est connecté directement.
- Le cookie de session est `HttpOnly` : le front ne le lit jamais, il sait qu'il est connecté parce que `/api/me` répond.

## Garmin et synchro

- **Réglages › Garmin et données** (`/settings`) : saisie de la clé personnelle et de sa date de fin (facultative), statut de la connexion, fréquence de la synchro auto, alerte quand la clé expire dans moins de 7 jours, changement de clé et déconnexion. Une clé expirée ou refusée affiche le message du back et suspend le bouton.
- **Bouton Synchroniser** (`SyncButton`, sur l'accueil et dans Réglages) : `POST /api/me/sync` répond 202 avec l'id de la tâche, puis la page interroge `GET /api/jobs/{id}` toutes les 2 s jusqu'à la fin, et recharge l'état Garmin.
  - Une synchro déjà en cours est retrouvée au chargement (`sync_job_id` dans `GET /api/me/garmin`), par exemple juste après l'enregistrement de la clé.
  - Si Garmin ne répond pas, la tâche est remise en file par le worker : le bouton s'arrête et l'indique, sans attendre le nouvel essai.
- La maquette ne montre que l'état « connecté » ; le formulaire de clé reprend ses styles de champs.

## Activités

- **Liste** (`/activities`) : tous les filtres sont dans l'URL (`q`, `category`, `period`, `from` / `to`, `sort`, `view`, `page`). Changer un filtre réécrit l'URL et relance le `load`. Le lien se partage, et le bouton retour marche.
- **Périodes** : 7 j, 30 j, 3 mois (par défaut), 12 mois, tout, ou des dates choisies. Le front les traduit en `from` / `to`.
- **Vue cartes** : elle demande `with_track=true`. La vignette est dessinée en SVG à partir des points [lat, lon], en projection simple (longitude × cos de la latitude moyenne).
- **Graphique par semaine** : barres en CSS sur les 12 dernières semaines. La semaine en cours est hachurée.
- **Fiche** (`/activities/[id]`) : environ 500 points demandés par sortie (`step` = distance / 500, au moins 10 m).
  - `RouteMap` dessine le tracé en SVG (même projection que les vignettes), avec le départ (damier), l'arrivée et un repère tous les 1, 5 ou 10 km selon la longueur.
  - `DistanceChart` est la zone commune au profil d'altitude et aux courbes. Le survol, ou les flèches du clavier, donne le point le plus proche, et ce point est partagé avec la carte.
  - Chaque courbe a sa propre échelle, sans les 2 % de valeurs extrêmes, pour qu'un arrêt ne l'écrase pas.
  - Onglets : Résumé (grands chiffres, et « Forme avant la sortie » via `ReadinessCard`), Statistiques (splits par km ou par tour de la montre, zones FC de Garmin, détails), Graphiques (allure, FC, altitude, cadence).
- **Pas encore là** : filtre par personne (attend la confidentialité), filtre entraînements / courses officielles et badge « Course » (attendent les courses), colonne « Analyse IA » (attend l'IA). Sur la fiche : analyse IA, résultat et découpage par segments de course, GAP (attend la courbe allure-pente de la prédiction), et partage.

## Courses

- **Liste** (`/races`) : compte à rebours J-, infos, inscrits et bouton « Rejoindre » / « J'y vais ». Les filtres (inscription, type, horizon) s'appliquent dans la page : la liste du groupe est courte.
- **Calendrier** : du mois en cours au mois de la dernière course affichée (3 à 12 mois). Une course où je vais est pleine, une course du groupe est entourée.
- **Courses passées** : repliées, chargées à l'ouverture, avec un lien vers ma sortie du jour J si elle a été reliée.
- **Formulaire** (`RaceForm`, sans maquette) : nom, date, heure, lieu, distance en km (virgule acceptée), D+ et site officiel. Le type est calculé par le back.
- **Pas encore là** :
  - la fiche d'une course : GPX, ravitos, barrières, entraînement (prochaine étape) ;
  - la jauge de préparation : la maquette l'affiche, mais la doc ne la définit pas.

## Conventions

- Imports internes par l'alias `#lib/…` **avec l'extension** (`#lib/api.ts`, `#lib/components/Brand.svelte`).
- Liens et `goto()` passent par `resolve()` de `$app/paths`, qui prend l'identifiant de la route, groupe compris : `resolve('/(public)/login')`. ESLint le vérifie.
- Couleurs : uniquement les variables de `app.css` (`var(--accent)`…), pour que le thème sombre suive. Polices Barlow et Barlow Condensed installées en local (`@fontsource`), sans appel à Google Fonts.

Les pages à construire suivent les [maquettes](https://claude.ai/artifact/MAHSw1opRbUcHhiJN14qf6) : accueil, profil, activités, courses, fiche de course, amis, comparer, réglages, admin.

## Commandes

```bash
pnpm install
pnpm dev          # :5173, API attendue sur :8000
pnpm check        # types
pnpm lint         # prettier + eslint
pnpm format
pnpm build        # → build/
```
