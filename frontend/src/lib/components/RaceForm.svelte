<script lang="ts">
	import { untrack } from 'svelte';
	import type { Race, RaceInput } from '#lib/races.ts';

	/** Formulaire d'ajout ou de modification d'une course (page sans maquette). */
	let {
		race = null,
		submitLabel,
		onsubmit
	}: {
		race?: Race | null;
		submitLabel: string;
		onsubmit: (input: RaceInput) => Promise<string | null>;
	} = $props();

	// Valeurs de départ du formulaire : on ne le réinitialise pas si la page change la course.
	const initial = untrack(() => race);
	let name = $state(initial?.name ?? '');
	let date = $state(initial?.date ?? '');
	let startTime = $state(initial?.start_time?.slice(0, 5) ?? '');
	let location = $state(initial?.location ?? '');
	let distanceKm = $state(
		initial ? String(Math.round(initial.distance_m / 10) / 100).replace('.', ',') : ''
	);
	let elevation = $state(initial ? String(Math.round(initial.elevation_gain_m)) : '');
	let url = $state(initial?.official_url ?? '');
	let saving = $state(false);
	let error = $state<string | null>(null);

	/** « 21,1 » ou « 21.1 » → 21.1 ; vide ou invalide → NaN. */
	const parse = (value: string) => Number(value.trim().replace(',', '.').replace(/\s/g, ''));

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = null;
		const km = parse(distanceKm);
		const dplus = elevation.trim() ? parse(elevation) : 0;
		if (!(km > 0)) {
			error = 'La distance doit être un nombre de km positif.';
			return;
		}
		if (!(dplus >= 0)) {
			error = 'Le dénivelé doit être un nombre de mètres positif.';
			return;
		}
		saving = true;
		error = await onsubmit({
			name: name.trim(),
			date,
			start_time: startTime || null,
			location: location.trim() || null,
			distance_m: Math.round(km * 1000),
			elevation_gain_m: Math.round(dplus),
			official_url: url.trim() || null
		});
		saving = false;
	}
</script>

<form class="form" onsubmit={submit}>
	<div class="field wide">
		<label for="race-name">Nom de la course</label>
		<input id="race-name" class="input" required maxlength="120" bind:value={name} />
	</div>
	<div class="field">
		<label for="race-date">Date</label>
		<input id="race-date" class="input" type="date" required bind:value={date} />
	</div>
	<div class="field">
		<label for="race-time">Heure de départ</label>
		<input id="race-time" class="input" type="time" bind:value={startTime} />
		<span class="hint">Facultative</span>
	</div>
	<div class="field wide">
		<label for="race-location">Lieu</label>
		<input id="race-location" class="input" maxlength="120" bind:value={location} />
	</div>
	<div class="field">
		<label for="race-distance">Distance (km)</label>
		<input
			id="race-distance"
			class="input"
			inputmode="decimal"
			required
			placeholder="21,1"
			bind:value={distanceKm}
		/>
	</div>
	<div class="field">
		<label for="race-elevation">Dénivelé positif (m)</label>
		<input
			id="race-elevation"
			class="input"
			inputmode="numeric"
			placeholder="0"
			bind:value={elevation}
		/>
		<span class="hint">Le type (route, trail court, trail long, mixte) en est déduit.</span>
	</div>
	<div class="field wide">
		<label for="race-url">Site officiel</label>
		<input
			id="race-url"
			class="input"
			type="url"
			placeholder="https://…"
			maxlength="500"
			bind:value={url}
		/>
	</div>
	<p class="hint wide">
		Le GPX officiel, les ravitos et les barrières horaires arrivent avec la fiche de course.
	</p>
	{#if error}<p class="error wide" role="alert">{error}</p>{/if}
	<div class="wide">
		<button class="button" type="submit" disabled={saving}>
			{saving ? 'Enregistrement…' : submitLabel}
		</button>
	</div>
</form>

<style>
	.form {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px;
	}

	.wide {
		grid-column: 1 / -1;
	}

	p.hint {
		margin: 0;
		font-size: 13px;
		color: var(--muted);
	}

	@media (max-width: 560px) {
		.form {
			grid-template-columns: 1fr;
		}
	}
</style>
