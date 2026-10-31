/** Appels à l'API FastAPI. Chemins relatifs : front et API partagent la même origine. */

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

type Fetch = typeof fetch;

interface ValidationIssue {
	loc: (string | number)[];
	msg: string;
	type: string;
}

// Erreurs de validation dont le backend écrit lui-même le message en français.
const SERVER_MESSAGE_TYPES = new Set(['password_too_short']);

// Messages pour les erreurs de validation de FastAPI (422), par champ.
const FIELD_MESSAGES: Record<string, string> = {
	email: 'Adresse email invalide.',
	display_name: 'Le nom est obligatoire.'
};

function errorMessage(status: number, body: unknown): string {
	const detail = (body as { detail?: unknown } | null)?.detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail) && detail.length > 0) {
		const issue = detail[0] as ValidationIssue;
		if (SERVER_MESSAGE_TYPES.has(issue.type)) return issue.msg;
		const field = String(issue.loc.at(-1));
		return FIELD_MESSAGES[field] ?? 'Certains champs sont invalides.';
	}
	if (status >= 500) return 'Erreur du serveur, réessaie dans un instant.';
	return 'La requête a échoué.';
}

export async function api<T = unknown>(
	path: string,
	options: { method?: string; body?: unknown; fetch?: Fetch } = {}
): Promise<T> {
	const { method = 'GET', body, fetch: f = fetch } = options;
	let response: Response;
	try {
		response = await f(`/api${path}`, {
			method,
			headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body),
			credentials: 'same-origin'
		});
	} catch {
		throw new ApiError(0, 'Serveur injoignable.');
	}
	const data = response.status === 204 ? null : await response.json().catch(() => null);
	if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, data));
	return data as T;
}

export interface Me {
	id: number;
	display_name: string;
	username: string | null;
	email: string;
	role: 'admin' | 'member';
	theme: string;
}

/** Membre connecté, ou null si personne n'est connecté. */
export async function fetchMe(f: Fetch = fetch): Promise<Me | null> {
	try {
		return await api<Me>('/me', { fetch: f });
	} catch (e) {
		if (e instanceof ApiError && e.status === 401) return null;
		throw e;
	}
}

/** Garde seulement les chemins internes, pour éviter les redirections vers un autre site. */
export function safeNext(next: string | null): string {
	return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}
