import { error } from '@sveltejs/kit';
import { api, ApiError } from '#lib/api.ts';
import type { Race } from '#lib/races.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	try {
		const race = await api<Race>(`/races/${params.id}`, { fetch });
		if (!race.can_edit) error(403, 'Seul l’auteur de la course ou l’admin peut la modifier.');
		return { race };
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) error(404, 'Course introuvable.');
		throw e;
	}
};
