import { error } from '@sveltejs/kit';
import { api, ApiError } from '#lib/api.ts';
import type { Activity, Points } from '#lib/activities.ts';
import type { PageLoad } from './$types';

// Environ 500 points par sortie, quelle que soit sa longueur (au moins un tous les 10 m).
const TARGET_POINTS = 500;

export const load: PageLoad = async ({ fetch, params }) => {
	try {
		const activity = await api<Activity>(`/activities/${params.id}`, { fetch });
		const step = Math.max(10, Math.round((activity.distance_m ?? 0) / TARGET_POINTS));
		const points = activity.processed
			? await api<Points>(`/activities/${params.id}/points?step=${step}`, { fetch })
			: null;
		return { activity, points };
	} catch (e) {
		if (e instanceof ApiError && e.status === 404) error(404, 'Activité introuvable.');
		throw e;
	}
};
