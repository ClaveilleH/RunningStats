import { redirect } from '@sveltejs/kit';
import { fetchMe, safeNext } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
	// Déjà connecté : pas besoin de cette page.
	if (await fetchMe(fetch)) redirect(307, safeNext(url.searchParams.get('next')));
};
