/** État de la connexion Garmin du membre et suivi de la synchro (bouton Synchroniser). */

import { api, ApiError } from '#lib/api.ts';

export type GarminStatus = 'ok' | 'key_expired' | 'error';

export interface Garmin {
	connected: boolean;
	source: 'personal_api' | 'garminconnect' | 'fit_import' | null;
	status: GarminStatus | null;
	api_key_expires_at: string | null;
	key_expires_soon: boolean;
	last_sync_at: string | null;
	last_error: string | null;
	sync_interval_minutes: number | null;
	sync_job_id: number | null;
}

interface Job {
	id: number;
	status: 'pending' | 'running' | 'done' | 'failed';
	attempts: number;
}

const POLL_MS = 2000;

export const SOURCE_LABELS: Record<NonNullable<Garmin['source']>, string> = {
	personal_api: 'API personnelle officielle de Garmin',
	garminconnect: 'bibliothèque garminconnect (secours)',
	fit_import: 'import de fichiers FIT'
};

/** Garmin du membre, rechargé après chaque synchro. Une instance par page. */
export class GarminSync {
	garmin = $state<Garmin | null>(null);
	syncing = $state(false);
	// Message à afficher sous le bouton quand la synchro n'a pas abouti.
	notice = $state<string | null>(null);
	#timer: ReturnType<typeof setTimeout> | undefined;

	constructor(initial: Garmin) {
		this.set(initial);
	}

	set(garmin: Garmin) {
		this.garmin = garmin;
		if (garmin.sync_job_id !== null) this.#follow(garmin.sync_job_id);
	}

	async refresh() {
		this.set(await api<Garmin>('/me/garmin'));
	}

	async start() {
		this.notice = null;
		try {
			const { job_id } = await api<{ job_id: number }>('/me/sync', { method: 'POST' });
			this.#follow(job_id);
		} catch (e) {
			this.notice = e instanceof ApiError ? e.message : 'La synchro n’a pas pu démarrer.';
		}
	}

	stop() {
		clearTimeout(this.#timer);
	}

	#follow(jobId: number) {
		this.stop();
		this.syncing = true;
		const poll = async () => {
			let job: Job;
			try {
				job = await api<Job>(`/jobs/${jobId}`);
			} catch {
				this.#timer = setTimeout(poll, POLL_MS * 3);
				return;
			}
			if (job.status === 'pending' && job.attempts > 0) {
				// Échec passager : le worker réessaiera tout seul plus tard.
				this.syncing = false;
				this.notice = 'Garmin ne répond pas. Nouvel essai automatique dans quelques minutes.';
				return;
			}
			if (job.status === 'pending' || job.status === 'running') {
				this.#timer = setTimeout(poll, POLL_MS);
				return;
			}
			this.syncing = false;
			if (job.status === 'failed') this.notice = 'La synchro a échoué.';
			const garmin = await api<Garmin>('/me/garmin').catch(() => null);
			if (garmin) this.garmin = { ...garmin, sync_job_id: null };
		};
		this.#timer = setTimeout(poll, POLL_MS);
	}
}
