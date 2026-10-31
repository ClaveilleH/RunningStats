<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { api, ApiError } from '#lib/api.ts';
	import SyncButton from '#lib/components/SyncButton.svelte';
	import { everyLabel, formatDate, timeAgo } from '#lib/format.ts';
	import { GarminSync, SOURCE_LABELS, type Garmin } from '#lib/garmin.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const sync = new GarminSync(untrack(() => data.garmin));
	onDestroy(() => sync.stop());

	// Données lues pendant la synchro (doc « Besoins du back »).
	const DATA_KINDS = [
		'Activités et tracés',
		'FC',
		'Sommeil',
		'Pas',
		'Poids',
		'Body Battery',
		'VFC',
		'FC au repos'
	];

	const STATUS_TEXT = {
		ok: 'Connecté à Garmin Connect',
		key_expired: 'Clé Garmin expirée',
		error: 'Garmin refuse la clé'
	} as const;

	let replacing = $state(false);
	let apiKey = $state('');
	let expiresOn = $state('');
	let saving = $state(false);
	let formError = $state<string | null>(null);

	const garmin = $derived(sync.garmin);
	const showForm = $derived(!garmin?.connected || replacing);

	async function saveKey(event: SubmitEvent) {
		event.preventDefault();
		saving = true;
		formError = null;
		try {
			const saved = await api<Garmin>('/me/garmin', {
				method: 'PUT',
				body: { api_key: apiKey, api_key_expires_on: expiresOn || null }
			});
			sync.set(saved);
			replacing = false;
			apiKey = '';
			expiresOn = '';
		} catch (e) {
			formError = e instanceof ApiError ? e.message : 'L’enregistrement a échoué.';
		} finally {
			saving = false;
		}
	}

	async function disconnect() {
		if (!confirm('Déconnecter Garmin ? Tes données déjà synchronisées restent sur le site.'))
			return;
		try {
			await api('/me/garmin', { method: 'DELETE' });
			await sync.refresh();
		} catch (e) {
			sync.notice = e instanceof ApiError ? e.message : 'La déconnexion a échoué.';
		}
	}
</script>

<svelte:head><title>Réglages · RunningStats</title></svelte:head>

<div class="layout">
	<nav aria-label="Sections des réglages">
		<h1 class="display">Réglages</h1>
		<!-- Les autres sections (profil, confidentialité…) arrivent avec leurs étapes. -->
		<a href="#garmin" class="current">Garmin et données</a>
	</nav>

	<div class="sections">
		<section id="garmin" aria-labelledby="h-garmin">
			<h2 id="h-garmin" class="display">Garmin et données</h2>

			{#if garmin?.connected && garmin.status}
				<div class="status" data-status={garmin.status}>
					<div class="status-text">
						<div class="status-title">
							<span class="dot" aria-hidden="true"></span>{STATUS_TEXT[garmin.status]}
						</div>
						{#if garmin.source}
							<div class="muted">Source : {SOURCE_LABELS[garmin.source]}</div>
						{/if}
						<div class="muted">
							{garmin.last_sync_at
								? `Dernière synchro ${timeAgo(garmin.last_sync_at)}`
								: 'Première synchro en attente'}
							{#if garmin.sync_interval_minutes && garmin.status === 'ok'}
								· synchro auto {everyLabel(garmin.sync_interval_minutes)}
							{/if}
						</div>
						{#if garmin.api_key_expires_at}
							<div class="muted" class:warning={garmin.key_expires_soon}>
								Clé valable jusqu’au {formatDate(garmin.api_key_expires_at)}
								{#if garmin.key_expires_soon && garmin.status === 'ok'}
									: elle expire bientôt, pense à en créer une nouvelle.
								{/if}
							</div>
						{/if}
						{#if garmin.status !== 'ok'}
							<p class="error">
								{garmin.last_error ?? 'La synchro est suspendue.'} Saisis une nouvelle clé pour la reprendre.
							</p>
						{/if}
					</div>
					<div class="actions">
						{#if garmin.status === 'ok'}
							<SyncButton {sync} label="Synchroniser maintenant" />
						{/if}
						<div class="secondary">
							<button
								class="button-line"
								type="button"
								onclick={() => (replacing = !replacing)}
								aria-expanded={replacing}>Changer de clé</button
							>
							<button class="button-line" type="button" onclick={disconnect}>Déconnecter</button>
						</div>
					</div>
				</div>
			{/if}

			{#if showForm}
				<form onsubmit={saveKey}>
					<p class="muted">
						{garmin?.connected
							? 'La nouvelle clé remplace l’ancienne. Elle est testée auprès de Garmin avant d’être enregistrée.'
							: 'Colle ta clé personnelle Garmin Connect. Elle est testée auprès de Garmin, puis gardée chiffrée. La première synchro récupère tout ton historique.'}
					</p>
					<div class="fields">
						<div class="field key">
							<label for="api-key">Clé personnelle Garmin</label>
							<input
								id="api-key"
								class="input"
								type="password"
								autocomplete="off"
								spellcheck="false"
								required
								bind:value={apiKey}
							/>
						</div>
						<div class="field">
							<label for="expires-on">Valable jusqu’au</label>
							<input id="expires-on" class="input" type="date" bind:value={expiresOn} />
							<span class="hint">Facultatif : date donnée par Garmin, pour te prévenir avant.</span>
						</div>
					</div>
					{#if formError}<p class="error" role="alert">{formError}</p>{/if}
					<div class="form-actions">
						<button class="button" type="submit" disabled={saving}>
							{saving ? 'Vérification…' : garmin?.connected ? 'Enregistrer la clé' : 'Connecter'}
						</button>
						{#if replacing}
							<button class="button-line" type="button" onclick={() => (replacing = false)}
								>Annuler</button
							>
						{/if}
					</div>
				</form>
			{/if}

			<div>
				<h3 class="label">Données récupérées</h3>
				<ul class="chips">
					{#each DATA_KINDS as kind (kind)}<li>{kind}</li>{/each}
				</ul>
				<p class="muted small">
					Le poids vient de Garmin : balance connectée ou saisie dans Garmin Connect.
				</p>
			</div>
		</section>
	</div>
</div>

<style>
	.layout {
		max-width: 1180px;
		margin: 0 auto;
		display: flex;
		flex-wrap: wrap;
		gap: 28px;
		align-items: flex-start;
	}

	nav {
		flex: 1 1 200px;
		max-width: 240px;
		min-width: 180px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	nav h1 {
		margin: 0 0 10px;
		font-weight: 800;
		font-size: 36px;
		line-height: 1;
		letter-spacing: 0;
	}

	nav a {
		min-height: 42px;
		padding: 0 12px;
		display: flex;
		align-items: center;
		border-left: 4px solid transparent;
		text-decoration: none;
		font-weight: 600;
	}

	nav a.current {
		border-left-color: var(--accent);
		background: var(--surface);
		font-weight: 700;
	}

	.sections {
		flex: 999 1 600px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 22px;
	}

	section {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	h2 {
		margin: 0;
		font-weight: 800;
		font-size: 26px;
		letter-spacing: 0;
	}

	.muted {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}

	.small {
		font-size: 13px;
		margin-top: 6px;
	}

	.warning {
		color: var(--accent-text);
		font-weight: 600;
	}

	.status {
		--status: var(--ok);
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
		align-items: flex-start;
		border: 1px solid var(--line);
		border-left: 5px solid var(--status);
		border-radius: var(--radius);
		padding: 14px;
	}

	.status[data-status='key_expired'],
	.status[data-status='error'] {
		--status: var(--danger);
	}

	.status-text {
		flex: 1 1 260px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.status-text .error {
		margin-top: 8px;
	}

	.status-title {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 800;
		font-size: 17px;
	}

	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--status);
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 240px;
	}

	.secondary {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}

	.button-line {
		min-height: 44px;
		padding: 0 14px;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		background: transparent;
		font-weight: 600;
		font-size: 14px;
		cursor: pointer;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 14px;
	}

	.key {
		grid-column: span 2;
	}

	@media (max-width: 560px) {
		.key {
			grid-column: auto;
		}
	}

	.form-actions {
		display: flex;
		gap: 10px;
		flex-wrap: wrap;
		align-items: center;
	}

	.label {
		margin: 0 0 6px;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
	}

	.chips {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.chips li {
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 3px 10px;
		font-size: 14px;
		font-weight: 600;
	}
</style>
