/** Types et libellés des activités (réponses de /api/users/{id}/activities). */

import { isoDate } from '#lib/format.ts';

export type Category = 'road' | 'short_trail' | 'long_trail' | 'mixed';

export const CATEGORY_LABELS: Record<Category, string> = {
	road: 'Route',
	short_trail: 'Trail court',
	long_trail: 'Trail long',
	mixed: 'Mixte'
};

export interface ActivityItem {
	id: number;
	name: string | null;
	activity_type: string;
	category: Category | null;
	start_time: string;
	start_time_local: string;
	location_name: string | null;
	distance_m: number | null;
	duration_s: number | null;
	elevation_gain_m: number | null;
	avg_hr: number | null;
	pace_s_per_km: number | null;
	pinned: boolean;
	track: [number, number][] | null;
}

export interface ActivityList {
	items: ActivityItem[];
	total: number;
	page: number;
	page_size: number;
	summary: { count: number; distance_m: number; elevation_gain_m: number; duration_s: number };
}

export interface Week {
	week_start: string;
	count: number;
	distance_m: number;
	elevation_gain_m: number;
	current: boolean;
}

/** Tracé [lat, lon] → chemin SVG dans une boîte w × h, proportions gardées. */
export function trackPath(track: [number, number][], w: number, h: number, pad = 6): string {
	if (track.length < 2) return '';
	const meanLat = (track.reduce((s, p) => s + p[0], 0) / track.length) * (Math.PI / 180);
	const xs = track.map((p) => p[1] * Math.cos(meanLat));
	const ys = track.map((p) => -p[0]);
	const [minX, maxX, minY, maxY] = [
		Math.min(...xs),
		Math.max(...xs),
		Math.min(...ys),
		Math.max(...ys)
	];
	const scale = Math.min((w - 2 * pad) / (maxX - minX || 1), (h - 2 * pad) / (maxY - minY || 1));
	const offX = (w - (maxX - minX) * scale) / 2;
	const offY = (h - (maxY - minY) * scale) / 2;
	return xs
		.map((x, i) => {
			const px = offX + (x - minX) * scale;
			const py = offY + (ys[i] - minY) * scale;
			return `${i ? 'L' : 'M'}${px.toFixed(1)} ${py.toFixed(1)}`;
		})
		.join(' ');
}

export const PERIODS = [
	['7d', '7 j'],
	['30d', '30 j'],
	['3m', '3 mois'],
	['year', 'Année'],
	['all', 'Tout'],
	['custom', 'Dates…']
] as const;
export type Period = (typeof PERIODS)[number][0];

export const PAGE_SIZE = 20;

/** Première date de la période (incluse), ou null pour tout l'historique. */
export function periodStart(period: Period, today: Date): string | null {
	const d = new Date(today);
	if (period === '7d') d.setDate(d.getDate() - 6);
	else if (period === '30d') d.setDate(d.getDate() - 29);
	else if (period === '3m') d.setMonth(d.getMonth() - 3);
	else if (period === 'year') d.setFullYear(d.getFullYear() - 1);
	else return null;
	return isoDate(d);
}
