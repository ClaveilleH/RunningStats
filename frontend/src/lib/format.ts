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
