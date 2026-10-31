import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// SPA : une seule page index.html, le routage se fait côté navigateur.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// En dev, l'API FastAPI tourne à part sur :8000.
		proxy: {
			'/api': 'http://localhost:8000'
		}
	}
});
