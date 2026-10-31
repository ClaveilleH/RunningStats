<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import SyncButton from '#lib/components/SyncButton.svelte';
	import { GarminSync } from '#lib/garmin.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const sync = new GarminSync(untrack(() => data.garmin));
	onDestroy(() => sync.stop());
</script>

<!-- Accueil provisoire, en attendant la page des maquettes. -->
<h1 class="display">Bonjour {data.me.display_name}</h1>

<aside aria-label="Accès rapides">
	{#if sync.garmin?.connected && sync.garmin.status === 'ok'}
		<SyncButton {sync} />
	{:else if sync.garmin?.connected}
		<p class="muted">La synchro Garmin est suspendue.</p>
		<a href={resolve('/(app)/settings')}>Voir dans les réglages</a>
	{:else}
		<p class="muted">Connecte ton compte Garmin pour récupérer tes sorties.</p>
		<a href={resolve('/(app)/settings')}>Connecter Garmin</a>
	{/if}
</aside>

<style>
	h1 {
		margin: 0 0 20px;
		font-size: 32px;
	}

	aside {
		max-width: 280px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.muted {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}

	a {
		font-weight: 700;
		color: var(--accent-text);
	}
</style>
