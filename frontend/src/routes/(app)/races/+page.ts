import { api } from '#lib/api.ts';
import type { Race } from '#lib/races.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	return { races: await api<Race[]>('/races', { fetch }) };
};
