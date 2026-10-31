/** Pastille d'un membre : initiales et couleur (celle choisie, sinon une couleur fixe par membre). */

// Couleurs des avatars des maquettes, toutes lisibles avec du texte blanc.
const PALETTE = ['#2f6f8f', '#6b4fa0', '#a03c6b', '#7a6a2a', '#2f7d4f'];

export function initials(name: string): string {
	return name
		.split(/\s+/)
		.filter(Boolean)
		.map((w) => w[0])
		.join('')
		.slice(0, 2)
		.toUpperCase();
}

export function avatarColor(userId: number, chosen: string | null = null): string {
	return chosen ?? PALETTE[(userId - 1) % PALETTE.length];
}
