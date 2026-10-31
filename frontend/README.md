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
│   ├── app.html         page HTML de base (lang="fr")
│   ├── lib/             code partagé, importé via l'alias #lib/*
│   └── routes/
│       ├── +layout.ts   ssr = false, prerender = false (mode SPA)
│       ├── +layout.svelte
│       └── +page.svelte page provisoire : affiche l'état de l'API
├── static/              fichiers servis tels quels
├── vite.config.ts       config Vite et SvelteKit (adapter, proxy)
└── package.json
```

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
