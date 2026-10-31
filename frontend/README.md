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
│   │   └── components/          composants partagés (Brand…)
│   └── routes/
│       ├── +layout.ts           ssr = false, prerender = false (mode SPA)
│       ├── +layout.svelte       polices et CSS globaux
│       ├── (public)/            pages sans connexion : /login, /invitation/[token]
│       └── (app)/               pages réservées aux membres ; +layout.ts redirige vers /login sinon
├── static/
├── vite.config.ts               config Vite et SvelteKit (adapter, proxy)
└── package.json
```

## Connexion

- `(app)/+layout.ts` appelle `GET /api/me`. Sans session, il redirige vers `/login?next=<page demandée>`, puis on revient sur cette page après connexion.
- `/invitation/[token]` vérifie le lien, puis crée le compte. Le nouveau membre est connecté directement.
- Le cookie de session est `HttpOnly` : le front ne le lit jamais, il sait qu'il est connecté parce que `/api/me` répond.

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
