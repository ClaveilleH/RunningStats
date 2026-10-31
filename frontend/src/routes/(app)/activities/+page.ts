import { api } from '#lib/api.ts';
import {
	PAGE_SIZE,
	PERIODS,
	periodStart,
	type ActivityList,
	type Period,
	type Week
} from '#lib/activities.ts';
import type { PageLoad } from './$types';

// Les filtres vivent dans l'URL : la page se recharge quand ils changent, et le lien se partage.
export const load: PageLoad = async ({ fetch, url, parent }) => {
	const { me } = await parent();
	const p = url.searchParams;
	const periodParam = p.get('period');
	const period: Period = PERIODS.some(([key]) => key === periodParam)
		? (periodParam as Period)
		: '3m';
	const view = p.get('view') === 'cards' ? 'cards' : 'table';
	const page = Math.max(1, Number(p.get('page')) || 1);

	const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
	for (const key of ['q', 'category', 'sort'] as const) {
		const value = p.get(key);
		if (value) query.set(key, value);
	}
	if (period === 'custom') {
		for (const key of ['from', 'to'] as const) {
			const value = p.get(key);
			if (value) query.set(key, value);
		}
	} else {
		const from = periodStart(period, new Date());
		if (from) query.set('from', from);
	}
	if (view === 'cards') query.set('with_track', 'true');

	const base = `/users/${me.id}/activities`;
	const [list, weeks] = await Promise.all([
		api<ActivityList>(`${base}?${query}`, { fetch }),
		api<Week[]>(`${base}/weekly?weeks=12`, { fetch })
	]);
	return {
		list,
		weeks,
		filters: {
			q: p.get('q') ?? '',
			category: p.get('category') ?? '',
			sort: p.get('sort') ?? 'date',
			period,
			from: p.get('from') ?? '',
			to: p.get('to') ?? ''
		},
		view,
		page
	};
};
