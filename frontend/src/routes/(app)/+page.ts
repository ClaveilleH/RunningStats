import { api } from '#lib/api.ts';
import type { Garmin } from '#lib/garmin.svelte.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	return { garmin: await api<Garmin>('/me/garmin', { fetch }) };
};
