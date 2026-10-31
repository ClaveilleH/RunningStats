import { redirect } from '@sveltejs/kit';
import { fetchMe } from '#lib/api.ts';
import type { LayoutLoad } from './$types';

// Toutes les pages du groupe (app) exigent un membre connecté.
export const load: LayoutLoad = async ({ fetch, url }) => {
	const me = await fetchMe(fetch);
	if (!me) {
		const next = url.pathname + url.search;
		redirect(307, next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`);
	}
	return { me };
};
