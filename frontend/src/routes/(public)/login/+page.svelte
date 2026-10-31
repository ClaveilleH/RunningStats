<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api, ApiError, safeNext } from '#lib/api.ts';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let pending = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		pending = true;
		try {
			await api('/auth/login', { method: 'POST', body: { email, password } });
			await invalidateAll();
			// Chemin interne déjà filtré par safeNext, pas une route connue à l'avance.
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			await goto(safeNext(page.url.searchParams.get('next')), { replaceState: true });
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'La connexion a échoué.';
			pending = false;
		}
	}
</script>

<svelte:head>
	<title>Connexion · RunningStats</title>
</svelte:head>

<h1 class="display">Connexion</h1>

<form onsubmit={submit} novalidate>
	<div class="field">
		<label for="email">Email</label>
		<input id="email" class="input" type="email" autocomplete="email" required bind:value={email} />
	</div>
	<div class="field">
		<label for="password">Mot de passe</label>
		<input
			id="password"
			class="input"
			type="password"
			autocomplete="current-password"
			required
			bind:value={password}
		/>
	</div>

	<div aria-live="polite">
		{#if error}<p class="error">{error}</p>{/if}
	</div>

	<button class="button" type="submit" disabled={pending}>
		{pending ? 'Connexion…' : 'Se connecter'}
	</button>
</form>

<p class="note">Pas de compte ? L'accès se fait sur invitation de l'admin du groupe.</p>

<style>
	h1 {
		margin: 0 0 20px;
		font-size: 30px;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.note {
		margin: 20px 0 0;
		font-size: 14px;
		color: var(--muted);
	}
</style>
