<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { CATEGORY_LABELS, PERIODS, trackPath, type Category } from '#lib/activities.ts';
	import {
		formatDay,
		formatDayMonth,
		formatDuration,
		formatInt,
		formatKm,
		formatPace
	} from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const PERIOD_TITLES: Record<string, string> = {
		'7d': '7 derniers jours',
		'30d': '30 derniers jours',
		'3m': '3 derniers mois',
		year: '12 derniers mois',
		all: 'tout l’historique',
		custom: 'dates choisies'
	};
	const SORTS = [
		['date', 'Date'],
		['distance', 'Distance'],
		['elevation', 'D+'],
		['duration', 'Durée']
	] as const;

	let metric = $state<'km' | 'dplus'>('km');
	// Suit l'URL, mais reste modifiable pendant la saisie.
	let search = $derived(data.filters.q);

	/** Change des paramètres de l'URL ; la page se recharge avec les nouveaux filtres. */
	function setParams(changes: Record<string, string | null>, resetPage = true) {
		const url = new URL(page.url.href);
		for (const [key, value] of Object.entries(changes)) {
			if (value) url.searchParams.set(key, value);
			else url.searchParams.delete(key);
		}
		if (resetPage) url.searchParams.delete('page');
		// L'URL vient de la page en cours : resolve() n'apporterait rien ici.
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		goto(url, { reset: false, replace: true });
	}

	let searchTimer: ReturnType<typeof setTimeout> | undefined;
	function onSearch() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => setParams({ q: search.trim() || null }), 300);
	}

	const summary = $derived(data.list.summary);
	const first = $derived((data.page - 1) * data.list.page_size + 1);
	const last = $derived(first + data.list.items.length - 1);
	const pages = $derived(Math.max(1, Math.ceil(data.list.total / data.list.page_size)));

	const bars = $derived.by(() => {
		const values = data.weeks.map((w) =>
			metric === 'km' ? w.distance_m / 1000 : w.elevation_gain_m
		);
		const max = Math.max(...values, 1);
		return data.weeks.map((w, i) => ({
			week: formatDayMonth(w.week_start),
			current: w.current,
			height: Math.max(values[i] > 0 ? 4 : 0, Math.round((values[i] / max) * 150)),
			label:
				metric === 'km'
					? String(Math.round(values[i]))
					: values[i] >= 1000
						? `${(values[i] / 1000).toFixed(1).replace('.', ',')}k`
						: String(Math.round(values[i]))
		}));
	});

	const categoryLabel = (c: Category | null) => (c ? CATEGORY_LABELS[c] : '—');
	const km = (m: number | null) => (m === null ? '—' : `${formatKm(m)} km`);
	const dplus = (m: number | null) => (m === null ? '—' : `${formatInt(m)} m`);
	const time = (s: number | null) => (s === null ? '—' : formatDuration(s));
	const pace = (s: number | null) => (s === null ? '—' : `${formatPace(s)} /km`);
</script>

<svelte:head><title>Activités · RunningStats</title></svelte:head>

<div class="page">
	<div class="title-row">
		<div>
			<h1 class="display">Activités</h1>
			<p class="muted">Toutes tes sorties synchronisées depuis Garmin</p>
		</div>
		<div class="segmented" role="group" aria-label="Affichage">
			<button
				type="button"
				aria-pressed={data.view === 'table'}
				onclick={() => setParams({ view: null }, false)}>Tableau</button
			>
			<button
				type="button"
				aria-pressed={data.view === 'cards'}
				onclick={() => setParams({ view: 'cards' }, false)}>Cartes</button
			>
		</div>
	</div>

	<form
		class="filters panel"
		role="search"
		aria-label="Filtrer les activités"
		onsubmit={(e) => e.preventDefault()}
	>
		<label class="filter grow">
			Recherche
			<input
				class="input"
				type="search"
				placeholder="Nom ou lieu"
				bind:value={search}
				oninput={onSearch}
			/>
		</label>
		<label class="filter">
			Type
			<select
				class="input"
				value={data.filters.category}
				onchange={(e) => setParams({ category: e.currentTarget.value || null })}
			>
				<option value="">Tous</option>
				{#each Object.entries(CATEGORY_LABELS) as [key, label] (key)}
					<option value={key}>{label}</option>
				{/each}
			</select>
		</label>
		<div class="filter period">
			<span id="period-label">Période</span>
			<div class="segmented" role="group" aria-labelledby="period-label">
				{#each PERIODS as [key, label] (key)}
					<button
						type="button"
						aria-pressed={data.filters.period === key}
						onclick={() => setParams({ period: key === '3m' ? null : key })}>{label}</button
					>
				{/each}
			</div>
		</div>
		{#if data.filters.period === 'custom'}
			<label class="filter">
				Du
				<input
					class="input"
					type="date"
					value={data.filters.from}
					onchange={(e) => setParams({ from: e.currentTarget.value || null })}
				/>
			</label>
			<label class="filter">
				Au
				<input
					class="input"
					type="date"
					value={data.filters.to}
					onchange={(e) => setParams({ to: e.currentTarget.value || null })}
				/>
			</label>
		{/if}
		<label class="filter">
			Trier par
			<select
				class="input"
				value={data.filters.sort}
				onchange={(e) =>
					setParams({ sort: e.currentTarget.value === 'date' ? null : e.currentTarget.value })}
			>
				{#each SORTS as [key, label] (key)}
					<option value={key}>{label}</option>
				{/each}
			</select>
		</label>
	</form>

	<section class="panel overview" aria-labelledby="sel-title">
		<div class="selection">
			<h2 id="sel-title" class="section-label">
				Sélection · {PERIOD_TITLES[data.filters.period]}
			</h2>
			<dl class="totals">
				<div>
					<dt>Sorties</dt>
					<dd>{summary.count}</dd>
				</div>
				<div>
					<dt>Distance</dt>
					<dd>{formatInt(summary.distance_m / 1000)}<span> km</span></dd>
				</div>
				<div>
					<dt>Dénivelé</dt>
					<dd>{formatInt(summary.elevation_gain_m)}<span> m D+</span></dd>
				</div>
				<div>
					<dt>Temps</dt>
					<dd>{formatInt(summary.duration_s / 3600)}<span> h</span></dd>
				</div>
			</dl>
		</div>
		<div class="chart">
			<div class="chart-head">
				<span class="section-label">Par semaine</span>
				<div class="segmented" role="group" aria-label="Mesure du graphique">
					<button type="button" aria-pressed={metric === 'km'} onclick={() => (metric = 'km')}
						>Distance</button
					>
					<button type="button" aria-pressed={metric === 'dplus'} onclick={() => (metric = 'dplus')}
						>D+</button
					>
				</div>
			</div>
			<div
				class="bars"
				role="img"
				aria-label={metric === 'km'
					? 'Kilomètres par semaine sur 12 semaines, semaine en cours hachurée'
					: 'Dénivelé positif par semaine sur 12 semaines, semaine en cours hachurée'}
			>
				{#each bars as bar (bar.week)}
					<div class="bar-col">
						<span class="bar-value" class:muted={bar.current}>{bar.label}</span>
						<div class="bar" class:current={bar.current} style:height="{bar.height}px"></div>
					</div>
				{/each}
			</div>
			<div class="weeks" aria-hidden="true">
				{#each bars as bar (bar.week)}<span>{bar.week}</span>{/each}
			</div>
		</div>
	</section>

	{#if data.list.items.length === 0}
		<p class="panel empty">Aucune activité pour ces filtres.</p>
	{:else if data.view === 'table'}
		<div class="panel table-wrap">
			<table>
				<thead>
					<tr>
						<th scope="col">Date</th>
						<th scope="col">Activité</th>
						<th scope="col">Type</th>
						<th scope="col" class="num">Distance</th>
						<th scope="col" class="num">D+</th>
						<th scope="col" class="num">Durée</th>
						<th scope="col" class="num">Allure</th>
						<th scope="col" class="num">FC moy.</th>
					</tr>
				</thead>
				<tbody>
					{#each data.list.items as a (a.id)}
						<tr>
							<td class="muted nowrap">{formatDay(a.start_time_local)}</td>
							<td>
								<a class="name" href={resolve('/(app)/activities/[id]', { id: String(a.id) })}
									>{a.name ?? 'Sortie'}</a
								>
								{#if a.location_name}<span class="muted small"> · {a.location_name}</span>{/if}
							</td>
							<td><span class="tag">{categoryLabel(a.category)}</span></td>
							<td class="num figure">{km(a.distance_m)}</td>
							<td class="num figure">{dplus(a.elevation_gain_m)}</td>
							<td class="num figure">{time(a.duration_s)}</td>
							<td class="num figure">{pace(a.pace_s_per_km)}</td>
							<td class="num figure">{a.avg_hr ?? '—'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<ul class="cards">
			{#each data.list.items as a (a.id)}
				<li class="panel card">
					<div>
						<a class="card-title" href={resolve('/(app)/activities/[id]', { id: String(a.id) })}
							>{a.name ?? 'Sortie'}</a
						>
						<div class="muted small">
							{formatDay(a.start_time_local)} · {categoryLabel(a.category)}
						</div>
					</div>
					<svg viewBox="0 0 280 90" class="track" aria-hidden="true">
						{#if a.track && a.track.length > 1}
							<path d={trackPath(a.track, 280, 90)} />
						{/if}
					</svg>
					<dl class="card-figures">
						<div>
							<dt>Dist.</dt>
							<dd>{km(a.distance_m)}</dd>
						</div>
						<div>
							<dt>D+</dt>
							<dd>{dplus(a.elevation_gain_m)}</dd>
						</div>
						<div>
							<dt>Durée</dt>
							<dd>{time(a.duration_s)}</dd>
						</div>
						<div>
							<dt>Allure</dt>
							<dd>{pace(a.pace_s_per_km)}</dd>
						</div>
					</dl>
				</li>
			{/each}
		</ul>
	{/if}

	<nav class="pagination" aria-label="Pagination">
		<span class="muted small">
			{data.list.total ? `${first} – ${last} sur ${data.list.total} activités` : ''}
		</span>
		<div class="pages">
			<button
				type="button"
				class="page-button"
				disabled={data.page <= 1}
				onclick={() => setParams({ page: String(data.page - 1) }, false)}>Précédent</button
			>
			<button
				type="button"
				class="page-button next"
				disabled={data.page >= pages}
				onclick={() => setParams({ page: String(data.page + 1) }, false)}>Suivant</button
			>
		</div>
	</nav>
</div>

<style>
	.page {
		max-width: 1320px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 20px;
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
		font-size: 13px;
	}

	.nowrap {
		white-space: nowrap;
	}

	.title-row {
		display: flex;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}

	h1 {
		margin: 0;
		font-weight: 800;
		font-size: 40px;
		line-height: 1;
		letter-spacing: 0;
	}

	.title-row p {
		margin: 0;
	}

	.title-row > .segmented {
		margin-left: auto;
		background: var(--surface);
	}

	/* Boutons groupés façon maquette : celui choisi est plein. */
	.segmented {
		display: flex;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		overflow: hidden;
	}

	.segmented button {
		flex: 1;
		min-height: 40px;
		padding: 0 14px;
		border: 0;
		background: transparent;
		font-weight: 500;
		font-size: 14px;
		white-space: nowrap;
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

	.filters {
		padding: 14px;
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: flex-end;
	}

	.filter {
		flex: 1 1 140px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
	}

	.filter.grow {
		flex: 2 1 220px;
	}

	.filter.period {
		flex: 3 1 360px;
	}

	.filter .input {
		min-height: 40px;
		color: var(--ink);
		font-size: 15px;
		font-weight: 400;
		text-transform: none;
		letter-spacing: 0;
	}

	.filter .segmented {
		overflow-x: auto;
	}

	.filter .segmented button {
		color: var(--ink);
		text-transform: none;
		letter-spacing: 0;
	}

	.section-label {
		margin: 0;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 18px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
	}

	.overview {
		display: flex;
		flex-wrap: wrap;
	}

	.selection {
		flex: 1 1 260px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		border-right: 1px solid var(--line);
	}

	.totals {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 14px;
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

	.totals dd {
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 34px;
		line-height: 1.05;
	}

	.totals dd span {
		font-size: 17px;
		color: var(--muted);
	}

	.chart {
		flex: 3 1 520px;
		min-width: 0;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.chart-head {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}

	.chart-head .segmented {
		margin-left: auto;
	}

	.bars,
	.weeks {
		display: grid;
		grid-template-columns: repeat(12, minmax(0, 1fr));
		gap: 8px;
	}

	.bars {
		align-items: end;
		height: 190px;
	}

	.bar-col {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: flex-end;
		gap: 4px;
		height: 100%;
	}

	.bar-value {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 15px;
	}

	.bar {
		width: 100%;
		max-width: 46px;
		border-radius: 2px 2px 0 0;
		background: var(--accent);
	}

	/* Semaine en cours : hachurée, elle n'est pas finie. */
	.bar.current {
		background: repeating-linear-gradient(135deg, var(--accent) 0 4px, var(--surface) 4px 7px);
	}

	.weeks {
		border-top: 1px solid var(--line);
		padding-top: 6px;
	}

	.weeks span {
		text-align: center;
		font-size: 12px;
		color: var(--muted);
		white-space: nowrap;
		overflow: hidden;
	}

	.empty {
		margin: 0;
		padding: 28px;
		text-align: center;
		color: var(--muted);
	}

	.table-wrap {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 900px;
		border-collapse: collapse;
	}

	th {
		padding: 12px 14px;
		text-align: left;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
		border-bottom: 2px solid var(--ink);
	}

	td {
		padding: 12px 14px;
		border-bottom: 1px solid var(--line);
	}

	.num {
		text-align: right;
	}

	.figure {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 19px;
		white-space: nowrap;
	}

	.name {
		font-weight: 700;
	}

	.tag {
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 2px 8px;
		font-size: 13px;
		font-weight: 600;
		color: var(--muted);
		white-space: nowrap;
	}

	.cards {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 14px;
	}

	/* Toute la carte est cliquable : le lien du titre la recouvre. */
	.card {
		position: relative;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.card-title {
		display: block;
		text-decoration: none;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 21px;
		text-transform: uppercase;
		line-height: 1.1;
	}

	.card-title::after {
		content: '';
		position: absolute;
		inset: 0;
	}

	.card:hover {
		border-color: var(--ink);
	}

	.track {
		width: 100%;
		height: 90px;
		background: var(--map);
		border-radius: 3px;
	}

	.track path {
		fill: none;
		stroke: var(--accent);
		stroke-width: 2.5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.card-figures {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 8px;
	}

	.card-figures dt {
		font-size: 11px;
	}

	.card-figures dd {
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 19px;
		white-space: nowrap;
	}

	.pagination {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}

	.pages {
		margin-left: auto;
		display: flex;
		gap: 8px;
	}

	.page-button {
		min-height: 42px;
		padding: 0 16px;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		background: transparent;
		font-weight: 600;
		font-size: 14px;
		cursor: pointer;
	}

	.page-button.next:not(:disabled) {
		border-color: var(--ink);
		background: var(--ink);
		color: var(--bg);
		font-weight: 700;
	}

	.page-button:disabled {
		color: var(--muted);
		cursor: default;
	}

	@media (max-width: 700px) {
		.selection {
			border-right: 0;
			border-bottom: 1px solid var(--line);
		}

		.weeks span:nth-child(odd) {
			visibility: hidden;
		}
	}
</style>
