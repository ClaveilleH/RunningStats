<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, ApiError } from '#lib/api.ts';
	import RaceForm from '#lib/components/RaceForm.svelte';
	import type { Race, RaceInput } from '#lib/races.ts';

	async function create(input: RaceInput): Promise<string | null> {
		try {
			await api<Race>('/races', { method: 'POST', body: input });
		} catch (e) {
			return e instanceof ApiError ? e.message : 'L’enregistrement a échoué.';
		}
		await goto(resolve('/(app)/races'));
		return null;
	}
</script>

<svelte:head><title>Ajouter une course · RunningStats</title></svelte:head>

<div class="page">
	<a href={resolve('/(app)/races')} class="back">← Courses</a>
	<h1 class="display">Ajouter une course</h1>
	<p class="muted">Elle apparaît tout de suite dans la liste du groupe.</p>
	<div class="panel">
		<RaceForm submitLabel="Ajouter la course" onsubmit={create} />
	</div>
</div>

<style>
	.page {
		max-width: 760px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.back {
		font-size: 14px;
		font-weight: 600;
		color: var(--muted);
		text-decoration: none;
	}

	h1 {
		margin: 0;
		font-weight: 800;
		font-size: 36px;
		letter-spacing: 0;
	}

	.muted {
		margin: 0 0 8px;
		color: var(--muted);
	}

	.panel {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 20px;
	}
</style>
