<script lang="ts">
	import type { Readiness } from '#lib/activities.ts';
	import { eveningBefore } from '#lib/format.ts';

	let { readiness }: { readiness: Readiness } = $props();

	// Barre pleine à 9 h de sommeil.
	const FULL_NIGHT_S = 9 * 3600;

	function hours(seconds: number): string {
		const minutes = Math.round(seconds / 60);
		const h = Math.floor(minutes / 60);
		const m = minutes % 60;
		return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`;
	}

	const weights = $derived(readiness.trace.params.sleep_weights);
	const lastShare = $derived(Math.round((weights[0] / weights.reduce((s, w) => s + w, 0)) * 100));
	// De la plus ancienne à la veille, comme on les lit dans le temps.
	const nights = $derived([...readiness.nights].reverse());
	const delta = $derived(readiness.resting_hr_delta);
	const hasData = $derived(
		readiness.nights.some((n) => n.total_s !== null) ||
			readiness.resting_hr !== null ||
			readiness.body_battery_max !== null
	);
</script>

<section class="card" aria-labelledby="readiness-title">
	<h2 id="readiness-title" class="display">Forme avant la sortie</h2>
	{#if !hasData}
		<p class="muted">Pas de données de sommeil ni de santé Garmin pour ces jours-là.</p>
	{:else}
		<div>
			<h3 class="label">Sommeil des {readiness.nights.length} nuits précédentes</h3>
			{#each nights as n (n.date)}
				<div class="night">
					<span class="muted day">{eveningBefore(n.date)}</span>
					<div class="track">
						{#if n.total_s}
							<div
								class="bar"
								style:width="{Math.min(100, (n.total_s / FULL_NIGHT_S) * 100)}%"
							></div>
						{/if}
					</div>
					<span class="hours">{n.total_s ? hours(n.total_s) : '—'}</span>
				</div>
			{/each}
			<p class="score">
				{#if readiness.sleep_score !== null}
					Score pondéré <strong>{readiness.sleep_score} / 100</strong> · la veille compte pour {lastShare ===
					50
						? 'moitié'
						: `${lastShare} %`}
				{:else}
					Pas de score de sommeil pour ces nuits.
				{/if}
			</p>
		</div>
		<dl class="figures">
			<div>
				<dt>FC repos du jour</dt>
				<dd>
					{readiness.resting_hr ?? '—'}
					{#if readiness.resting_hr !== null}
						<span
							>bpm{delta !== null
								? ` · ${delta > 0 ? '+' : delta < 0 ? '−' : '±'}${Math.abs(delta)}`
								: ''}</span
						>
					{/if}
				</dd>
				{#if delta !== null}
					<p class="muted small">
						par rapport à la moyenne des {readiness.trace.params.resting_hr_baseline_days} jours d’avant
					</p>
				{/if}
			</div>
			<div>
				<dt>Body Battery</dt>
				<dd>
					{readiness.body_battery_max ?? '—'}
					{#if readiness.body_battery_max !== null}<span>max du jour</span>{/if}
				</dd>
			</div>
		</dl>
	{/if}
</section>

<style>
	.card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	h2 {
		margin: 0;
		font-weight: 800;
		font-size: 24px;
		letter-spacing: 0;
	}

	.muted {
		color: var(--muted);
	}

	p {
		margin: 0;
	}

	.small {
		font-size: 12px;
	}

	.label {
		margin: 0 0 6px;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
	}

	.night {
		display: grid;
		grid-template-columns: 76px minmax(0, 1fr) 64px;
		align-items: center;
		gap: 8px;
		padding: 3px 0;
	}

	.day {
		font-size: 13px;
	}

	.track {
		height: 10px;
		background: var(--track);
		border-radius: 2px;
	}

	.bar {
		height: 100%;
		background: var(--blue);
		border-radius: 2px;
	}

	.hours {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 17px;
		text-align: right;
		white-space: nowrap;
	}

	.score {
		font-size: 14px;
		margin-top: 6px;
	}

	.figures {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
		border-top: 1px solid var(--line);
		padding-top: 10px;
	}

	dt {
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
	}

	dd {
		margin: 0;
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 28px;
		line-height: 1.05;
	}

	dd span {
		font-size: 15px;
		color: var(--muted);
	}
</style>
