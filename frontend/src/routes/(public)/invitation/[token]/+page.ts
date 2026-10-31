import { api, ApiError } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	try {
		const check = await api<{ valid: boolean; expires_at: string }>(
			`/auth/invitations/${encodeURIComponent(params.token)}`,
			{ fetch }
		);
		return { token: params.token, valid: check.valid, problem: null };
	} catch (e) {
		const problem =
			e instanceof ApiError && e.status === 404
				? 'Ce lien d’invitation est invalide, déjà utilisé ou expiré. Demande un nouveau lien à l’admin du groupe.'
				: e instanceof ApiError
					? e.message
					: 'Impossible de vérifier le lien.';
		return { token: params.token, valid: false, problem };
	}
};
