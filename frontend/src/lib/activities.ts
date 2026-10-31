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

/**
 * Projection [lat, lon] → [x, y] dans une boîte w × h, proportions gardées et tracé centré.
 * Projection simple (longitude × cos de la latitude moyenne) : assez juste à l'échelle d'une sortie.
 */
export function projector(
	track: [number, number][],
	w: number,
	h: number,
	pad = 6
): (lat: number, lon: number) => [number, number] {
	const meanLat = (track.reduce((s, p) => s + p[0], 0) / (track.length || 1)) * (Math.PI / 180);
	const k = Math.cos(meanLat);
	const xs = track.map((p) => p[1] * k);
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
	return (lat, lon) => [offX + (lon * k - minX) * scale, offY + (-lat - minY) * scale];
}

/** Tracé [lat, lon] → chemin SVG dans une boîte w × h. */
export function trackPath(track: [number, number][], w: number, h: number, pad = 6): string {
	if (track.length < 2) return '';
	const project = projector(track, w, h, pad);
	return track
		.map(([lat, lon], i) => {
			const [x, y] = project(lat, lon);
			return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
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

export interface Split {
	index: number;
	start_distance_m: number | null;
	end_distance_m: number | null;
	duration_s: number | null;
	elevation_gain_m: number | null;
	elevation_loss_m: number | null;
	avg_hr: number | null;
}

export interface Activity extends ActivityItem {
	user_id: number;
	moving_duration_s: number | null;
	elevation_loss_m: number | null;
	max_hr: number | null;
	km_effort: number | null;
	hr_zones_s: number[] | null;
	details: {
		elapsed_s: number | null;
		stopped_s: number | null;
		avg_cadence_spm: number | null;
		calories: number | null;
		min_altitude_m: number | null;
		max_altitude_m: number | null;
	};
	km_splits: Split[];
	laps: Split[];
	processed: boolean;
}

/** Points allégés, en colonnes de même longueur (GET /api/activities/{id}/points). */
export interface Points {
	step_m: number;
	distance_m: (number | null)[];
	timer_s: (number | null)[];
	lat: (number | null)[];
	lon: (number | null)[];
	altitude_m: (number | null)[];
	hr: (number | null)[];
	cadence_spm: (number | null)[];
	pace_s_per_km: (number | null)[];
}

/** Indice du point le plus proche d'une distance (distances croissantes). */
export function nearestIndex(distances: (number | null)[], target: number): number {
	let lo = 0;
	let hi = distances.length - 1;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if ((distances[mid] ?? 0) < target) lo = mid + 1;
		else hi = mid;
	}
	if (
		lo > 0 &&
		Math.abs((distances[lo - 1] ?? 0) - target) < Math.abs((distances[lo] ?? 0) - target)
	)
		return lo - 1;
	return lo;
}

/**
 * Courbe SVG d'une série en fonction de la distance, dans une boîte w × h.
 * Les trous (null) coupent la ligne. invert : plus petit en haut (allure).
 */
export function seriesPath(
	distances: (number | null)[],
	values: (number | null)[],
	w: number,
	h: number,
	opts: { min?: number; max?: number; invert?: boolean; pad?: number } = {}
): string {
	const pad = opts.pad ?? 6;
	const known = values.filter((v): v is number => v !== null);
	if (known.length < 2) return '';
	const min = opts.min ?? Math.min(...known);
	const max = opts.max ?? Math.max(...known);
	const span = max - min || 1;
	const total = distances.at(-1) ?? 1;
	let path = '';
	let pen = false;
	values.forEach((v, i) => {
		const d = distances[i];
		if (v === null || d === null) {
			pen = false;
			return;
		}
		let n = (v - min) / span;
		if (opts.invert) n = 1 - n;
		const x = (d / total) * w;
		const y = h - pad - n * (h - 2 * pad);
		path += `${pen ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
		pen = true;
	});
	return path;
}

/** Bornes d'une série en ignorant les 2 % extrêmes (pics d'allure à l'arrêt, FC parasite). */
export function robustRange(values: (number | null)[]): [number, number] | null {
	const sorted = values.filter((v): v is number => v !== null).sort((a, b) => a - b);
	if (sorted.length < 2) return null;
	const cut = Math.floor(sorted.length * 0.02);
	return [sorted[cut], sorted[sorted.length - 1 - cut]];
}
