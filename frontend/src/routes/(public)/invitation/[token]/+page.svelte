<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, ApiError } from '#lib/api.ts';
	import type { PageProps } from './$types';

	const MIN_PASSWORD = 10;

	let { data }: PageProps = $props();

	let displayName = $state('');
	let email = $state('');
	let password = $state('');
	let confirm = $state('');
	let error = $state('');
	let pending = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (password.length < MIN_PASSWORD) {
			error = `Le mot de passe doit faire au moins ${MIN_PASSWORD} caractères.`;
			return;
		}
		if (password !== confirm) {
			error = 'Les deux mots de passe ne sont pas identiques.';
			return;
		}
		pending = true;
		try {
			await api(`/auth/invitations/${encodeURIComponent(data.token)}`, {
				method: 'POST',
				body: { display_name: displayName, email, password }
			});
			// Le compte est créé et la session ouverte.
			await invalidateAll();
			await goto(resolve('/(app)'), { replaceState: true });
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'La création du compte a échoué.';
			pending = false;
		}
	}
</script>

<svelte:head>
	<title>Invitation · RunningStats</title>
</svelte:head>

<h1 class="display">Rejoindre le groupe</h1>

{#if !data.valid}
	<p class="error">{data.problem}</p>
	<p class="note"><a href={resolve('/(public)/login')}>Aller à la connexion</a></p>
{:else}
	<p class="lead">Crée ton compte pour voir tes stats et celles de tes amis.</p>

	<form onsubmit={submit} novalidate>
		<div class="field">
			<label for="name">Nom affiché</label>
			<input
				id="name"
				class="input"
				autocomplete="name"
				maxlength="80"
				required
				bind:value={displayName}
			/>
		</div>
		<div class="field">
			<label for="email">Email</label>
			<input
				id="email"
				class="input"
				type="email"
				autocomplete="email"
				required
				bind:value={email}
			/>
			<span class="hint">Il servira à te connecter.</span>
		</div>
		<div class="field">
			<label for="password">Mot de passe</label>
			<input
				id="password"
				class="input"
				type="password"
				autocomplete="new-password"
				minlength={MIN_PASSWORD}
				required
				aria-describedby="password-hint"
				bind:value={password}
			/>
			<span id="password-hint" class="hint">{MIN_PASSWORD} caractères minimum.</span>
		</div>
		<div class="field">
			<label for="confirm">Confirmer le mot de passe</label>
			<input
				id="confirm"
				class="input"
				type="password"
				autocomplete="new-password"
				required
				bind:value={confirm}
			/>
		</div>

		<div aria-live="polite">
			{#if error}<p class="error">{error}</p>{/if}
		</div>

		<button class="button" type="submit" disabled={pending}>
			{pending ? 'Création…' : 'Créer mon compte'}
		</button>
	</form>
{/if}

<style>
	h1 {
		margin: 0 0 12px;
		font-size: 30px;
	}

	.lead {
		margin: 0 0 20px;
		color: var(--muted);
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.note {
		margin: 16px 0 0;
		font-size: 14px;
	}
</style>
