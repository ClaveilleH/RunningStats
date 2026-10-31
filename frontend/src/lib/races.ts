/** Courses à venir (réponses de /api/races). */

import type { Category } from '#lib/activities.ts';
import { isoDate } from '#lib/format.ts';

export interface RaceParticipant {
	user_id: number;
	display_name: string;
	avatar_color: string | null;
	joined_at: string;
	activity_id: number | null;
}

export interface Race {
	id: number;
	name: string;
	date: string;
	start_time: string | null;
	location: string | null;
	distance_m: number;
	elevation_gain_m: number;
	category: Category;
	km_effort: number;
	official_url: string | null;
	created_by: number | null;
	created_by_name: string | null;
	can_edit: boolean;
	joined: boolean;
	participants: RaceParticipant[];
}

/** Corps de POST / PUT /api/races. */
export interface RaceInput {
	name: string;
	date: string;
	start_time: string | null;
	location: string | null;
	distance_m: number;
	elevation_gain_m: number;
	official_url: string | null;
}

/** Jours entre aujourd'hui et la date de la course (0 le jour J). */
export function daysUntil(isoDate: string, today: Date): number {
	const target = new Date(`${isoDate}T00:00:00`);
	const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
	return Math.round((target.getTime() - start.getTime()) / 86_400_000);
}

/** Date dans n mois, au format AAAA-MM-JJ. */
export function inMonths(today: Date, months: number): string {
	const d = new Date(today);
	d.setMonth(d.getMonth() + months);
	return isoDate(d);
}
