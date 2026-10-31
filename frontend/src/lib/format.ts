/** Dates et durées affichées en français. */

/** « il y a 14 min », « il y a 3 h », « hier à 18:02 », « le 12 oct. ». */
export function timeAgo(iso: string, now = new Date()): string {
	const date = new Date(iso);
	const minutes = Math.round((now.getTime() - date.getTime()) / 60000);
	if (minutes < 1) return 'à l’instant';
	if (minutes < 60) return `il y a ${minutes} min`;
	if (minutes < 12 * 60) return `il y a ${Math.round(minutes / 60)} h`;
	const yesterday = new Date(now);
	yesterday.setDate(now.getDate() - 1);
	const time = date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
	if (date.toDateString() === now.toDateString()) return `aujourd’hui à ${time}`;
	if (date.toDateString() === yesterday.toDateString()) return `hier à ${time}`;
	return `le ${formatDate(iso)}`;
}

export function formatDate(iso: string): string {
	return new Date(iso).toLocaleDateString('fr-FR', {
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});
}

/** 60 → « toutes les heures », 30 → « toutes les 30 min », 120 → « toutes les 2 h ». */
export function everyLabel(minutes: number): string {
	if (minutes === 60) return 'toutes les heures';
	if (minutes % 60 === 0) return `toutes les ${minutes / 60} h`;
	return `toutes les ${minutes} min`;
}

const NBSP = ' '; // espace fine insécable, séparateur de milliers en français

/** 1380 → « 1 380 ». */
export function formatInt(value: number): string {
	return Math.round(value)
		.toString()
		.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

/** 7834 m → « 7,8 ». Au-delà de 100 km, sans décimale. */
export function formatKm(meters: number): string {
	const km = meters / 1000;
	return km >= 100 ? formatInt(km) : km.toFixed(1).replace('.', ',');
}

/** 2660 s → « 44:20 », 11885 s → « 3:18:05 ». */
export function formatDuration(seconds: number): string {
	const total = Math.round(seconds);
	const h = Math.floor(total / 3600);
	const m = Math.floor((total % 3600) / 60);
	const s = total % 60;
	const mm = h ? String(m).padStart(2, '0') : String(m);
	return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

/** Allure en s/km → « 5:41 ». */
export function formatPace(secondsPerKm: number): string {
	const total = Math.round(secondsPerKm);
	return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

/** Date locale de la montre (sans fuseau) → « lun. 26 oct. », avec l'année si ce n'est pas l'année en cours. */
export function formatDay(localIso: string, now = new Date()): string {
	const date = new Date(localIso);
	return date.toLocaleDateString('fr-FR', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric'
	});
}

/** « 26 oct. » (semaine du graphique). */
export function formatDayMonth(isoDate: string): string {
	return new Date(`${isoDate}T00:00:00`).toLocaleDateString('fr-FR', {
		day: 'numeric',
		month: 'short'
	});
}

/** Date du jour au format AAAA-MM-JJ, dans le fuseau du navigateur. */
export function isoDate(date: Date): string {
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Nuit datée par Garmin du jour du réveil → soir du coucher, « ven. 23 » (comme la maquette).
 */
export function eveningBefore(wakeDate: string): string {
	const d = new Date(`${wakeDate}T12:00:00`);
	d.setDate(d.getDate() - 1);
	return d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric' });
}
