<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, ApiError } from '#lib/api.ts';
	import RaceForm from '#lib/components/RaceForm.svelte';
	import type { Race, RaceInput } from '#lib/races.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let deleteError = $state<string | null>(null);

	async function save(input: RaceInput): Promise<string | null> {
		try {
			await api<Race>(`/races/${data.race.id}`, { method: 'PUT', body: input });
		} catch (e) {
			return e instanceof ApiError ? e.message : 'L’enregistrement a échoué.';
		}
		await goto(resolve('/(app)/races'));
		return null;
	}

	async function remove() {
		const others = data.race.participants.length;
		const warning = others ? ` Elle a ${others} inscrit${others > 1 ? 's' : ''}.` : '';
		if (!confirm(`Supprimer « ${data.race.name} » pour tout le groupe ?${warning}`)) return;
		try {
			await api(`/races/${data.race.id}`, { method: 'DELETE' });
			await goto(resolve('/(app)/races'));
		} catch (e) {
			deleteError = e instanceof ApiError ? e.message : 'La suppression a échoué.';
		}
	}
</script>

<svelte:head><title>Modifier une course · RunningStats</title></svelte:head>

<div class="page">
	<a href={resolve('/(app)/races')} class="back">← Courses</a>
	<h1 class="display">Modifier la course</h1>
	<div class="panel">
		<RaceForm race={data.race} submitLabel="Enregistrer" onsubmit={save} />
	</div>
	<div class="danger">
		{#if deleteError}<p class="error" role="alert">{deleteError}</p>{/if}
		<button type="button" class="delete" onclick={remove}>Supprimer la course</button>
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
		margin: 0 0 8px;
		font-weight: 800;
		font-size: 36px;
		letter-spacing: 0;
	}

	.panel {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 20px;
	}

	.danger {
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: flex-start;
		margin-top: 10px;
	}

	.delete {
		min-height: 44px;
		padding: 0 16px;
		border: 1px solid var(--danger);
		border-radius: var(--radius);
		background: transparent;
		color: var(--danger);
		font-weight: 700;
		font-size: 14px;
		cursor: pointer;
	}
</style>
