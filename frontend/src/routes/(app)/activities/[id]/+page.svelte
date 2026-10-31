<script lang="ts">
	import { resolve } from '$app/paths';
	import { api, ApiError } from '#lib/api.ts';
	import {
		CATEGORY_LABELS,
		robustRange,
		seriesPath,
		type ActivityItem,
		type Split
	} from '#lib/activities.ts';
	import DistanceChart from '#lib/components/DistanceChart.svelte';
	import RouteMap from '#lib/components/RouteMap.svelte';
	import { formatDuration, formatInt, formatKm, formatPace } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const a = $derived(data.activity);
	const pts = $derived(data.points);

	// Point survolé, partagé entre la carte, le profil et les courbes.
	let idx = $state<number | null>(null);
	let tab = $state<'summary' | 'stats' | 'charts'>('summary');
	let splitKind = $state<'km' | 'laps'>('km');

	// --- En-tête ---
	const startLabel = $derived(
		new Date(a.start_time_local).toLocaleString('fr-FR', {
			weekday: 'long',
			day: 'numeric',
			month: 'long',
			year: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		})
	);
	const meta = $derived(
		[startLabel, a.category ? CATEGORY_LABELS[a.category] : null, a.location_name]
			.filter(Boolean)
			.join(' · ')
	);

	let pinned = $derived(a.pinned);
	let pinError = $state<string | null>(null);
	async function togglePin() {
		pinError = null;
		try {
			const item = await api<ActivityItem>(`/activities/${a.id}/pin`, {
				method: pinned ? 'DELETE' : 'PUT'
			});
			pinned = item.pinned;
		} catch (e) {
			pinError = e instanceof ApiError ? e.message : 'L’épingle n’a pas pu être changée.';
		}
	}

	// --- Lecture du point survolé ---
	const at = $derived.by(() => {
		if (!pts || idx === null) return null;
		return {
			km: ((pts.distance_m[idx] ?? 0) / 1000).toFixed(2).replace('.', ','),
			alt: pts.altitude_m[idx],
			pace: pts.pace_s_per_km[idx],
			hr: pts.hr[idx],
			cadence: pts.cadence_spm[idx]
		};
	});

	// --- Profil d'altitude ---
	const PROFILE_H = 160;
	const altRange = $derived(pts ? robustRange(pts.altitude_m) : null);
	const profileLine = $derived(
		pts && altRange
			? seriesPath(pts.distance_m, pts.altitude_m, 800, PROFILE_H, {
					min: altRange[0] - 10,
					max: altRange[1] + 10
				})
			: ''
	);
	const profileArea = $derived(
		profileLine ? `${profileLine} L800 ${PROFILE_H} L0 ${PROFILE_H} Z` : ''
	);
	const totalKm = $derived(pts ? (pts.distance_m.at(-1) ?? 0) / 1000 : 0);
	const axisKm = $derived.by(() => {
		const step = totalKm > 30 ? 10 : totalKm > 8 ? 5 : totalKm > 3 ? 1 : 0.5;
		const ticks: number[] = [];
		for (let k = step; k < totalKm - step / 3; k += step) ticks.push(k);
		return ticks;
	});

	// --- Résumé ---
	const bigNumbers = $derived([
		['Temps', a.duration_s === null ? '—' : formatDuration(a.duration_s), ''],
		['Distance', a.distance_m === null ? '—' : formatKm(a.distance_m), 'km'],
		['Dénivelé', a.elevation_gain_m === null ? '—' : formatInt(a.elevation_gain_m), 'm D+'],
		['Allure moy.', a.pace_s_per_km === null ? '—' : formatPace(a.pace_s_per_km), '/km'],
		['FC moy.', a.avg_hr === null ? '—' : String(a.avg_hr), 'bpm']
	]);

	// --- Statistiques ---
	const splits = $derived(splitKind === 'km' ? a.km_splits : a.laps);
	function splitLabel(s: Split, i: number, all: Split[]): string {
		if (splitKind === 'laps') return `Tour ${s.index + 1}`;
		const dist = (s.end_distance_m ?? 0) - (s.start_distance_m ?? 0);
		const partial = i === all.length - 1 && dist < 990;
		return partial ? `km ${formatKm(s.end_distance_m ?? 0)}` : `km ${s.index + 1}`;
	}
	function splitPace(s: Split): string {
		const dist = (s.end_distance_m ?? 0) - (s.start_distance_m ?? 0);
		return s.duration_s && dist > 0 ? formatPace(s.duration_s / (dist / 1000)) : '—';
	}

	const zones = $derived.by(() => {
		const z = a.hr_zones_s;
		if (!z || z.length === 0) return [];
		const total = z.reduce((s, v) => s + v, 0) || 1;
		const max = Math.max(...z) || 1;
		return z.map((seconds, i) => ({
			name: `Z${i + 1}`,
			time: seconds >= 60 ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds)} s`,
			pct: `${Math.round((seconds / total) * 100)} %`,
			width: (seconds / max) * 100
		}));
	});

	const d = $derived(a.details);
	const detailItems = $derived(
		[
			['D−', a.elevation_loss_m === null ? null : `${formatInt(a.elevation_loss_m)} m`],
			[
				'Temps en mouvement',
				a.moving_duration_s === null ? null : formatDuration(a.moving_duration_s)
			],
			['Temps arrêté', d.stopped_s === null ? null : formatDuration(d.stopped_s)],
			['Temps écoulé', d.elapsed_s === null ? null : formatDuration(d.elapsed_s)],
			['FC max', a.max_hr === null ? null : `${a.max_hr} bpm`],
			['Cadence moy.', d.avg_cadence_spm === null ? null : `${Math.round(d.avg_cadence_spm)} ppm`],
			[
				'Altitude min / max',
				d.min_altitude_m === null || d.max_altitude_m === null
					? null
					: `${formatInt(d.min_altitude_m)} / ${formatInt(d.max_altitude_m)} m`
			],
			['Km-effort', a.km_effort === null ? null : formatKm(a.km_effort * 1000)],
			['Calories', d.calories === null ? null : `${formatInt(d.calories)} kcal`]
		].filter((item): item is [string, string] => item[1] !== null)
	);

	// --- Graphiques ---
	const CHART_H = 300;
	type SeriesKey = 'pace' | 'hr' | 'alt' | 'cadence';
	let shown = $state<Record<SeriesKey, boolean>>({
		pace: true,
		hr: true,
		alt: true,
		cadence: false
	});
	const series = $derived.by(() => {
		if (!pts) return [];
		const defs: {
			key: SeriesKey;
			label: string;
			values: (number | null)[];
			invert: boolean;
			format: (v: number) => string;
		}[] = [
			{
				key: 'pace',
				label: 'Allure',
				values: pts.pace_s_per_km,
				invert: true,
				format: (v) => `${formatPace(v)} /km`
			},
			{ key: 'hr', label: 'FC', values: pts.hr, invert: false, format: (v) => `${v} bpm` },
			{
				key: 'alt',
				label: 'Altitude',
				values: pts.altitude_m,
				invert: false,
				format: (v) => `${formatInt(v)} m`
			},
			{
				key: 'cadence',
				label: 'Cadence',
				values: pts.cadence_spm,
				invert: false,
				format: (v) => `${v} ppm`
			}
		];
		return defs
			.filter((s) => s.values.some((v) => v !== null))
			.map((s) => {
				const range = robustRange(s.values);
				return {
					...s,
					path: range
						? seriesPath(pts.distance_m, s.values, 800, CHART_H, {
								min: range[0],
								max: range[1],
								invert: s.invert,
								pad: 14
							})
						: ''
				};
			});
	});
</script>

<svelte:head><title>{a.name ?? 'Sortie'} · RunningStats</title></svelte:head>

<div class="page">
	<div class="title-row">
		<div class="title">
			<a href={resolve('/(app)/activities')} class="back">← Activités</a>
			<h1 class="display">{a.name ?? 'Sortie'}</h1>
			<p class="muted">{meta}</p>
		</div>
		<div class="actions">
			<button type="button" class="action" aria-pressed={pinned} onclick={togglePin}>
				<svg
					width="16"
					height="16"
					viewBox="0 0 24 24"
					fill={pinned ? 'currentColor' : 'none'}
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"><path d="M12 17v5" /><path d="M9 3h6l-1 7 4 3H6l4-3z" /></svg
				>
				{pinned ? 'Épinglée' : 'Épingler'}
			</button>
		</div>
	</div>
	{#if pinError}<p class="error" role="alert">{pinError}</p>{/if}

	{#if !pts}
		<p class="panel notice">
			Le fichier de la montre n’a pas encore été lu : la carte, les courbes et les splits
			apparaîtront après la prochaine synchro.
		</p>
	{:else}
		<section class="panel route" aria-label="Parcours">
			<RouteMap points={pts} {idx} />
			<div class="profile">
				<div class="profile-head">
					<span class="section-label">Profil d’altitude</span>
					<span class="muted small">Survole la courbe pour suivre le point sur la carte</span>
					{#if at}
						<span class="readout">
							km {at.km}{at.alt !== null ? ` · ${formatInt(at.alt)} m` : ''}{at.pace !== null
								? ` · ${formatPace(at.pace)} /km`
								: ''}{at.hr !== null ? ` · FC ${at.hr}` : ''}
						</span>
					{/if}
				</div>
				<DistanceChart
					distances={pts.distance_m}
					bind:idx
					height={PROFILE_H}
					label="Profil d’altitude : flèches gauche et droite pour avancer"
				>
					<path d={profileArea} class="area" />
					<path d={profileLine} class="line" />
				</DistanceChart>
				<div class="axis" aria-hidden="true">
					<span>0 km</span>
					{#each axisKm as k (k)}<span style:left="{(k / totalKm) * 100}%"
							>{String(k).replace('.', ',')}</span
						>{/each}
					<span class="end">{formatKm(totalKm * 1000)} km</span>
				</div>
			</div>
		</section>
	{/if}

	<div class="tabs" role="tablist" aria-label="Sections de l’activité">
		{#each [['summary', 'Résumé'], ['stats', 'Statistiques'], ['charts', 'Graphiques']] as const as [key, label] (key)}
			<button
				type="button"
				role="tab"
				id="tab-{key}"
				aria-selected={tab === key}
				aria-controls="panel-{key}"
				onclick={() => (tab = key)}>{label}</button
			>
		{/each}
	</div>

	{#if tab === 'summary'}
		<div id="panel-summary" role="tabpanel" aria-labelledby="tab-summary">
			<dl class="panel big-numbers">
				{#each bigNumbers as [label, value, unit] (label)}
					<div>
						<dt>{label}</dt>
						<dd>
							{value}{#if unit}<span> {unit}</span>{/if}
						</dd>
					</div>
				{/each}
			</dl>
		</div>
	{:else if tab === 'stats'}
		<div id="panel-stats" role="tabpanel" aria-labelledby="tab-stats" class="stats">
			<section class="panel splits" aria-labelledby="splits-title">
				<div class="splits-head">
					<h2 id="splits-title" class="display">Temps intermédiaires</h2>
					<div class="segmented" role="group" aria-label="Découpage">
						<button
							type="button"
							aria-pressed={splitKind === 'km'}
							onclick={() => (splitKind = 'km')}>Par km</button
						>
						<button
							type="button"
							aria-pressed={splitKind === 'laps'}
							onclick={() => (splitKind = 'laps')}>Par tour</button
						>
					</div>
				</div>
				{#if splits.length === 0}
					<p class="muted pad">Pas de découpage pour cette sortie.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th scope="col" class="left">{splitKind === 'km' ? 'Km' : 'Tour'}</th>
									<th scope="col">Distance</th>
									<th scope="col">D+</th>
									<th scope="col">D−</th>
									<th scope="col">Temps</th>
									<th scope="col">Allure</th>
									<th scope="col">FC moy.</th>
								</tr>
							</thead>
							<tbody>
								{#each splits as s, i (s.index)}
									<tr>
										<th scope="row" class="left">{splitLabel(s, i, splits)}</th>
										<td>{formatKm((s.end_distance_m ?? 0) - (s.start_distance_m ?? 0))} km</td>
										<td
											>{s.elevation_gain_m === null
												? '—'
												: `${formatInt(s.elevation_gain_m)} m`}</td
										>
										<td
											>{s.elevation_loss_m === null
												? '—'
												: `${formatInt(s.elevation_loss_m)} m`}</td
										>
										<td>{s.duration_s === null ? '—' : formatDuration(s.duration_s)}</td>
										<td>{splitPace(s)}</td>
										<td>{s.avg_hr ?? '—'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>

			<div class="side">
				{#if zones.length}
					<section class="panel box" aria-labelledby="zones-title">
						<h2 id="zones-title" class="display">Zones de FC</h2>
						<p class="muted small">Zones de la montre Garmin.</p>
						{#each zones as z, i (z.name)}
							<div class="zone">
								<span class="zone-name">{z.name}</span>
								<div class="zone-track">
									<div
										class="zone-bar"
										style:width="{z.width}%"
										style:background="var(--z{i + 1})"
									></div>
								</div>
								<span class="zone-value"><strong>{z.time}</strong> · {z.pct}</span>
							</div>
						{/each}
					</section>
				{/if}
				<section class="panel box" aria-labelledby="details-title">
					<h2 id="details-title" class="display">Détails</h2>
					<dl class="details">
						{#each detailItems as [label, value] (label)}
							<div>
								<dt>{label}</dt>
								<dd>{value}</dd>
							</div>
						{/each}
					</dl>
				</section>
			</div>
		</div>
	{:else}
		<div id="panel-charts" role="tabpanel" aria-labelledby="tab-charts" class="panel box charts">
			{#if !pts}
				<p class="muted">Les courbes apparaîtront quand le fichier de la montre aura été lu.</p>
			{:else}
				<div class="charts-head">
					<h2 class="display">Courbes</h2>
					<div class="series-buttons" role="group" aria-label="Courbes affichées">
						{#each series as s (s.key)}
							<button
								type="button"
								aria-pressed={shown[s.key]}
								onclick={() => (shown[s.key] = !shown[s.key])}
							>
								<span class="swatch" style:border-color="var(--series-{s.key})"></span>{s.label}
							</button>
						{/each}
					</div>
				</div>
				<div class="charts-readout" aria-live="polite">
					{#if idx !== null && at}
						<strong class="readout">km {at.km}</strong>
						{#each series.filter((s) => shown[s.key]) as s (s.key)}
							{@const v = s.values[idx]}
							<span>
								<span class="swatch" style:border-color="var(--series-{s.key})"></span>
								{s.label} <strong>{v === null ? '—' : s.format(v)}</strong>
							</span>
						{/each}
					{:else}
						<span class="muted">Survole les courbes pour lire les valeurs.</span>
					{/if}
				</div>
				<DistanceChart
					distances={pts.distance_m}
					bind:idx
					height={CHART_H}
					label="Courbes : flèches gauche et droite pour avancer"
				>
					{#each [0.25, 0.5, 0.75] as f (f)}
						<line x1="0" x2="800" y1={CHART_H * f} y2={CHART_H * f} class="grid" />
					{/each}
					{#each series.filter((s) => shown[s.key]) as s (s.key)}
						<path d={s.path} class="series" style:stroke="var(--series-{s.key})" />
					{/each}
				</DistanceChart>
				<div class="axis" aria-hidden="true">
					<span>0 km</span>
					{#each axisKm as k (k)}<span style:left="{(k / totalKm) * 100}%"
							>{String(k).replace('.', ',')}</span
						>{/each}
					<span class="end">{formatKm(totalKm * 1000)} km</span>
				</div>
				<p class="muted small">
					Chaque courbe a sa propre échelle verticale. Pour l’allure, plus haut veut dire plus
					rapide. L’allure est lissée sur 200 m et ne compte pas les pauses.
				</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	.page {
		max-width: 1320px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 20px;
		/* Couleurs des courbes (maquette « Détail d'une activité »). */
		--series-pace: var(--accent);
		--series-hr: var(--blue);
		--series-alt: var(--alt);
		--series-cadence: var(--purple);
	}

	.panel {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
	}

	.muted {
		color: var(--muted);
	}

	.small {
		font-size: 14px;
	}

	.title-row {
		display: flex;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}

	.title {
		flex: 1 1 420px;
		min-width: 0;
	}

	.back {
		font-size: 14px;
		font-weight: 600;
		color: var(--muted);
		text-decoration: none;
	}

	h1 {
		margin: 4px 0 0;
		font-weight: 800;
		font-size: 44px;
		line-height: 1;
		letter-spacing: 0;
	}

	.title p {
		margin: 4px 0 0;
		font-size: 15px;
	}

	.actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}

	.action {
		min-height: 44px;
		padding: 0 14px;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		background: var(--surface);
		font-weight: 700;
		font-size: 14px;
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
	}

	.action[aria-pressed='true'] {
		border-color: var(--accent);
		color: var(--accent-text);
	}

	.notice {
		margin: 0;
		padding: 20px;
		color: var(--muted);
	}

	.route {
		overflow: hidden;
	}

	.profile {
		padding: 14px 16px 16px;
		border-top: 1px solid var(--line);
	}

	.profile-head {
		display: flex;
		align-items: baseline;
		gap: 14px;
		flex-wrap: wrap;
		margin-bottom: 8px;
	}

	.section-label {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 17px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
	}

	.readout {
		margin-left: auto;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 19px;
	}

	.area {
		fill: var(--soft);
	}

	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2.5;
		vector-effect: non-scaling-stroke;
	}

	.axis {
		position: relative;
		height: 18px;
		margin-top: 4px;
		font-size: 12px;
		color: var(--muted);
	}

	.axis span {
		position: absolute;
		transform: translateX(-50%);
		white-space: nowrap;
	}

	.axis span:first-child {
		left: 0;
		transform: none;
	}

	.axis .end {
		right: 0;
		transform: none;
	}

	.tabs {
		display: flex;
		gap: 4px;
		border-bottom: 2px solid var(--line);
		flex-wrap: wrap;
	}

	.tabs button {
		min-height: 48px;
		padding: 0 20px;
		margin-bottom: -2px;
		border: 0;
		border-bottom: 4px solid transparent;
		background: transparent;
		color: var(--muted);
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 21px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		cursor: pointer;
	}

	.tabs button[aria-selected='true'] {
		border-bottom-color: var(--accent);
		color: var(--ink);
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
	}

	.big-numbers {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
	}

	.big-numbers > div {
		padding: 14px 18px;
		border-left: 1px solid var(--line);
		margin-left: -1px;
	}

	.big-numbers dd {
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 40px;
		line-height: 1.05;
	}

	.big-numbers dd span {
		font-size: 19px;
		color: var(--muted);
	}

	.stats {
		display: flex;
		flex-wrap: wrap;
		gap: 20px;
		align-items: flex-start;
	}

	.splits {
		flex: 2 1 560px;
		min-width: 0;
	}

	.splits-head,
	.charts-head {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}

	.splits-head {
		padding: 14px 16px;
	}

	h2 {
		margin: 0;
		font-weight: 800;
		font-size: 24px;
		letter-spacing: 0;
	}

	.segmented {
		margin-left: auto;
		display: flex;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		overflow: hidden;
	}

	.segmented button {
		min-height: 38px;
		padding: 0 14px;
		border: 0;
		background: transparent;
		font-weight: 500;
		font-size: 14px;
		cursor: pointer;
	}

	.segmented button + button {
		border-left: 1px solid var(--line);
	}

	.segmented button[aria-pressed='true'] {
		background: var(--ink);
		color: var(--bg);
		font-weight: 700;
	}

	.pad {
		margin: 0;
		padding: 0 16px 16px;
	}

	.table-wrap {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 620px;
		border-collapse: collapse;
	}

	thead th {
		padding: 10px 12px;
		text-align: right;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
		border-bottom: 2px solid var(--ink);
	}

	tbody tr {
		border-bottom: 1px solid var(--line);
	}

	tbody td {
		padding: 10px 12px;
		text-align: right;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 19px;
		white-space: nowrap;
	}

	tbody th {
		padding: 10px 16px;
		font-weight: 700;
		font-size: 15px;
		white-space: nowrap;
	}

	.left {
		text-align: left;
		padding-left: 16px;
	}

	.side {
		flex: 1 1 320px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.box {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.box p {
		margin: 0;
	}

	.zone {
		display: grid;
		grid-template-columns: 34px minmax(0, 1fr) 96px;
		align-items: center;
		gap: 10px;
	}

	.zone-name {
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 18px;
	}

	.zone-track {
		height: 16px;
		background: var(--track);
		border-radius: 2px;
	}

	.zone-bar {
		height: 100%;
		border-radius: 2px;
	}

	.zone-value {
		font-size: 14px;
		text-align: right;
	}

	.details {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px 16px;
	}

	.details dd {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 24px;
		line-height: 1.1;
	}

	.charts {
		gap: 12px;
	}

	.series-buttons {
		margin-left: auto;
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	.series-buttons button {
		min-height: 38px;
		padding: 0 12px;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		background: transparent;
		color: var(--muted);
		font-weight: 500;
		font-size: 14px;
		display: flex;
		align-items: center;
		cursor: pointer;
	}

	.series-buttons button[aria-pressed='true'] {
		border-color: var(--ink);
		background: var(--surface);
		color: var(--ink);
		font-weight: 700;
	}

	.series-buttons button[aria-pressed='false'] .swatch {
		opacity: 0.4;
	}

	.swatch {
		display: inline-block;
		width: 16px;
		height: 0;
		margin-right: 6px;
		border-top: 3px solid;
		vertical-align: middle;
	}

	.charts-readout {
		display: flex;
		gap: 18px;
		flex-wrap: wrap;
		align-items: baseline;
		min-height: 26px;
		font-size: 15px;
	}

	.charts-readout .readout {
		margin-left: 0;
	}

	.grid {
		stroke: var(--line);
		stroke-width: 1;
		vector-effect: non-scaling-stroke;
	}

	.series {
		fill: none;
		stroke-width: 2.5;
		stroke-linejoin: round;
		vector-effect: non-scaling-stroke;
	}
</style>
