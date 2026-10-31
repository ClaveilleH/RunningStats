<script lang="ts">
	import { resolve } from '$app/paths';
	import { CATEGORY_LABELS, type Category } from '#lib/activities.ts';
	import { api, ApiError } from '#lib/api.ts';
	import { avatarColor, initials } from '#lib/avatar.ts';
	import { formatDayMonth, formatInt, formatKm, formatLongDate, isoDate } from '#lib/format.ts';
	import { daysUntil, inMonths, type Race } from '#lib/races.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Copie locale : « J'y vais » met une course à jour sans tout recharger.
	let races = $derived(data.races);
	const today = new Date();

	let joinFilter = $state<'all' | 'mine' | 'other'>('all');
	let category = $state<'' | Category>('');
	let horizon = $state<'all' | '3' | '6'>('all');
	let view = $state<'list' | 'calendar'>('list');
	let error = $state<string | null>(null);
	let busy = $state<number | null>(null);

	const shown = $derived.by(() => {
		const limit = inMonths(today, Number(horizon));
		return races.filter(
			(r) =>
				(joinFilter === 'all' || (joinFilter === 'mine') === r.joined) &&
				(!category || r.category === category) &&
				(horizon === 'all' || r.date <= limit)
		);
	});

	async function toggle(race: Race) {
		error = null;
		busy = race.id;
		try {
			const updated = await api<Race>(`/races/${race.id}/participation`, {
				method: race.joined ? 'DELETE' : 'POST'
			});
			races = races.map((r) => (r.id === updated.id ? updated : r));
		} catch (e) {
			error = e instanceof ApiError ? e.message : 'La modification a échoué.';
		} finally {
			busy = null;
		}
	}

	// --- Calendrier : du mois en cours au mois de la dernière course affichée (3 à 12 mois). ---
	const MONTHS = $derived.by(() => {
		const last = shown.at(-1)?.date;
		const lastDate = last ? new Date(`${last}T00:00:00`) : today;
		const count = Math.min(
			12,
			Math.max(
				3,
				(lastDate.getFullYear() - today.getFullYear()) * 12 +
					lastDate.getMonth() -
					today.getMonth() +
					1
			)
		);
		const todayIso = isoDate(today);
		return Array.from({ length: count }, (_, k) => {
			const first = new Date(today.getFullYear(), today.getMonth() + k, 1);
			const offset = (first.getDay() + 6) % 7; // lundi en premier
			const days = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
			const cells = Array.from({ length: days }, (_, i) => {
				const iso = isoDate(new Date(first.getFullYear(), first.getMonth(), i + 1));
				const events = shown.filter((r) => r.date === iso);
				return {
					day: i + 1,
					iso,
					past: iso < todayIso,
					today: iso === todayIso,
					mine: events.some((r) => r.joined),
					group: events.length > 0,
					title: events.map((r) => r.name).join(', ')
				};
			});
			const events = shown.filter((r) => r.date.startsWith(isoDate(first).slice(0, 7)));
			return {
				label: first.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' }),
				offset,
				cells,
				events
			};
		});
	});

	// --- Courses passées : chargées à l'ouverture. ---
	let pastOpen = $state(false);
	let past = $state<Race[] | null>(null);
	async function togglePast() {
		pastOpen = !pastOpen;
		if (pastOpen && past === null) {
			try {
				past = await api<Race[]>('/races?past=true');
			} catch (e) {
				error = e instanceof ApiError ? e.message : 'Les courses passées n’ont pas pu être lues.';
			}
		}
	}

	const km = (m: number) => `${formatKm(m)} km`;
	const people = (r: Race) =>
		r.participants.length === 0
			? 'personne'
			: `${r.participants.length} inscrit${r.participants.length > 1 ? 's' : ''}`;
</script>

<svelte:head><title>Courses · RunningStats</title></svelte:head>

<div class="page">
	<div class="title-row">
		<div>
			<h1 class="display">Courses à venir</h1>
			<p class="muted">
				La liste partagée du groupe : rejoins une course pour suivre ta prépa avec les autres
			</p>
		</div>
		<a class="button add" href={resolve('/(app)/races/new')}>
			<svg
				width="18"
				height="18"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2.6"
				stroke-linecap="round"
				aria-hidden="true"><path d="M12 5v14" /><path d="M5 12h14" /></svg
			>
			Ajouter une course
		</a>
	</div>

	<div class="filters">
		<div class="segmented" role="group" aria-label="Filtrer par inscription">
			{#each [['all', 'Toutes'], ['mine', 'J’y vais'], ['other', 'Pas encore']] as const as [key, label] (key)}
				<button type="button" aria-pressed={joinFilter === key} onclick={() => (joinFilter = key)}
					>{label}</button
				>
			{/each}
		</div>
		<label class="filter">
			Type
			<select class="input" bind:value={category}>
				<option value="">Tous</option>
				{#each Object.entries(CATEGORY_LABELS) as [key, label] (key)}
					<option value={key}>{label}</option>
				{/each}
			</select>
		</label>
		<label class="filter">
			Période
			<select class="input" bind:value={horizon}>
				<option value="all">Toutes</option>
				<option value="3">3 prochains mois</option>
				<option value="6">6 prochains mois</option>
			</select>
		</label>
		<div class="segmented view" role="group" aria-label="Affichage">
			<button type="button" aria-pressed={view === 'list'} onclick={() => (view = 'list')}
				>Liste</button
			>
			<button type="button" aria-pressed={view === 'calendar'} onclick={() => (view = 'calendar')}
				>Calendrier</button
			>
		</div>
	</div>

	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if view === 'list'}
		<div class="list">
			{#each shown as r (r.id)}
				{@const days = daysUntil(r.date, today)}
				<article class="race panel">
					<div class="countdown" class:joined={r.joined}>
						<div class="j">{days === 0 ? 'Jour' : 'J -'}</div>
						<div class="days">{days === 0 ? 'J' : days}</div>
						<div class="short">{formatDayMonth(r.date)}</div>
					</div>
					<div class="info">
						<div>
							<div class="name-row">
								<h2 class="display">{r.name}</h2>
								<span class="tag">{CATEGORY_LABELS[r.category]}</span>
							</div>
							<div class="muted">
								{formatLongDate(r.date)}{r.start_time
									? ` à ${r.start_time.slice(0, 5)}`
									: ''}{r.location ? ` · ${r.location}` : ''}
							</div>
						</div>
						<dl class="figures">
							<div>
								<dt>Distance</dt>
								<dd>{km(r.distance_m)}</dd>
							</div>
							<div>
								<dt>Dénivelé</dt>
								<dd>{formatInt(r.elevation_gain_m)} m</dd>
							</div>
							<div>
								<dt>Inscrits</dt>
								<dd>{r.participants.length}</dd>
							</div>
						</dl>
						<div class="links muted">
							{#if r.created_by_name}<span>Ajoutée par {r.created_by_name}</span>{/if}
							{#if r.official_url}
								<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
								<a href={r.official_url} target="_blank" rel="noopener noreferrer"
									>Site officiel ↗</a
								>
							{/if}
							{#if r.can_edit}
								<a href={resolve('/(app)/races/[id]/edit', { id: String(r.id) })}>Modifier</a>
							{/if}
						</div>
					</div>
					<div class="people">
						<div class="people-head">
							<span class="label">Inscrits</span>
							<button
								type="button"
								class="join"
								class:on={r.joined}
								aria-pressed={r.joined}
								aria-label={r.joined
									? `Tu vas à ${r.name}. Cliquer pour quitter la course`
									: `Rejoindre ${r.name}`}
								disabled={busy === r.id}
								onclick={() => toggle(r)}
							>
								{#if r.joined}
									<svg
										width="14"
										height="14"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="3"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg
									>
									J’y vais
								{:else}
									Rejoindre
								{/if}
							</button>
						</div>
						{#each r.participants as p (p.user_id)}
							<div class="person">
								<span class="avatar" style:background={avatarColor(p.user_id, p.avatar_color)}
									>{initials(p.display_name)}</span
								>
								<span>{p.user_id === data.me.id ? 'Toi' : p.display_name}</span>
							</div>
						{:else}
							<p class="muted small">Personne pour l’instant.</p>
						{/each}
					</div>
				</article>
			{:else}
				<p class="panel empty">
					{races.length === 0
						? 'Aucune course à venir. Ajoute la prochaine du groupe !'
						: 'Aucune course pour ce filtre.'}
				</p>
			{/each}
		</div>
	{:else}
		<div class="panel calendar">
			<div class="legend muted small">
				<span><span class="key mine"></span>J’y vais</span>
				<span><span class="key group"></span>Course du groupe</span>
				<span><span class="key today"></span>Aujourd’hui</span>
			</div>
			<div class="months">
				{#each MONTHS as m (m.label)}
					<section class="month" aria-label={m.label}>
						<h2 class="display">{m.label}</h2>
						<div class="weekdays" aria-hidden="true">
							{#each ['L', 'M', 'M', 'J', 'V', 'S', 'D'] as d, i (i)}<span>{d}</span>{/each}
						</div>
						<div class="cells">
							{#each Array.from({ length: m.offset }, (_, i) => i) as i (i)}<span></span>{/each}
							{#each m.cells as c (c.iso)}
								<span
									class="cell"
									class:past={c.past}
									class:today={c.today}
									class:group={c.group}
									class:mine={c.mine}
									title={c.title || undefined}>{c.day}</span
								>
							{/each}
						</div>
						{#each m.events as r (r.id)}
							<div class="event">
								<span class="event-day" class:mine={r.joined}
									>{new Date(`${r.date}T00:00:00`).getDate()}</span
								>
								<div>
									<div class="event-name">{r.name}</div>
									<div class="muted small">
										{CATEGORY_LABELS[r.category]} · {km(r.distance_m)} · {people(r)}
									</div>
								</div>
							</div>
						{/each}
					</section>
				{/each}
			</div>
		</div>
	{/if}

	<section class="panel past">
		<button type="button" class="past-toggle" aria-expanded={pastOpen} onclick={togglePast}>
			<span class="arrow" class:open={pastOpen} aria-hidden="true">▸</span>
			Courses passées
		</button>
		{#if pastOpen}
			{#if past === null}
				<p class="muted pad">Chargement…</p>
			{:else if past.length === 0}
				<p class="muted pad">Aucune course passée.</p>
			{:else}
				{#each past as r (r.id)}
					{@const mine = r.participants.find((p) => p.user_id === data.me.id)}
					<div class="past-row">
						<div class="past-info">
							<div class="event-name">{r.name}</div>
							<div class="muted small">
								{formatLongDate(r.date)} · {CATEGORY_LABELS[r.category]} · {km(r.distance_m)}
							</div>
						</div>
						<div class="muted small">{people(r)}</div>
						{#if mine?.activity_id}
							<a
								class="past-link"
								href={resolve('/(app)/activities/[id]', { id: String(mine.activity_id) })}
								>Ma sortie</a
							>
						{/if}
					</div>
				{/each}
			{/if}
		{/if}
	</section>
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

	.add {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 8px;
		text-decoration: none;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: flex-end;
	}

	.filter {
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
	}

	.filter .input {
		min-height: 40px;
		min-width: 170px;
		color: var(--ink);
		font-size: 15px;
		font-weight: 400;
		text-transform: none;
		letter-spacing: 0;
	}

	.segmented {
		display: flex;
		border: 1px solid var(--line);
		border-radius: var(--radius);
		overflow: hidden;
		background: var(--surface);
	}

	.segmented.view {
		margin-left: auto;
	}

	.segmented button {
		min-height: 40px;
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

	.list {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.empty {
		margin: 0;
		padding: 28px;
		text-align: center;
		color: var(--muted);
	}

	.race {
		display: flex;
		flex-wrap: wrap;
		overflow: hidden;
	}

	.countdown {
		flex: 0 0 110px;
		padding: 16px 10px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		background: var(--ink);
		color: var(--bg);
		font-family: var(--font-display);
		text-transform: uppercase;
	}

	.countdown.joined {
		background: var(--accent);
		color: var(--on-accent);
	}

	.j {
		font-weight: 700;
		font-size: 16px;
		letter-spacing: 0.08em;
	}

	.days {
		font-weight: 800;
		font-size: 52px;
		line-height: 1;
	}

	.short {
		font-weight: 700;
		font-size: 15px;
	}

	.info {
		flex: 3 1 360px;
		min-width: 0;
		padding: 16px 18px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.name-row {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}

	h2 {
		margin: 0;
		font-weight: 800;
		font-size: 26px;
		line-height: 1.1;
		letter-spacing: 0;
	}

	.tag {
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 2px 8px;
		font-size: 13px;
		font-weight: 600;
		color: var(--muted);
	}

	.figures {
		margin: 0;
		display: flex;
		gap: 28px;
		flex-wrap: wrap;
	}

	dt,
	.label {
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
		font-size: 26px;
		line-height: 1.05;
	}

	.links {
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
		font-size: 14px;
	}

	.links a {
		color: var(--ink);
		font-weight: 700;
	}

	.people {
		flex: 2 1 260px;
		min-width: 0;
		padding: 16px 18px;
		border-left: 1px solid var(--line);
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.people-head {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 4px;
	}

	.join {
		margin-left: auto;
		min-height: 40px;
		padding: 0 14px;
		border: 1px solid var(--ink);
		border-radius: var(--radius);
		background: transparent;
		font-weight: 700;
		font-size: 14px;
		display: flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
	}

	.join.on {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--on-accent);
	}

	.join:disabled {
		opacity: 0.6;
		cursor: progress;
	}

	.person {
		display: flex;
		align-items: center;
		gap: 10px;
		font-weight: 600;
	}

	.avatar {
		width: 28px;
		height: 28px;
		border-radius: 3px;
		color: #ffffff;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 11px;
		font-weight: 700;
	}

	.people p {
		margin: 0;
	}

	.calendar {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.legend {
		display: flex;
		gap: 18px;
		flex-wrap: wrap;
	}

	.legend > span {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.key {
		width: 14px;
		height: 14px;
		border-radius: 3px;
	}

	.key.mine {
		background: var(--accent);
	}

	.key.group {
		border: 2px solid var(--accent);
	}

	.key.today {
		border: 2px solid var(--ink);
	}

	.months {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 22px;
	}

	.month h2 {
		font-size: 20px;
		margin-bottom: 6px;
	}

	.weekdays,
	.cells {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		gap: 3px;
	}

	.weekdays span {
		text-align: center;
		font-size: 11px;
		font-weight: 700;
		color: var(--muted);
	}

	.cell {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 30px;
		border-radius: 3px;
		font-size: 13px;
	}

	.cell.past {
		color: var(--muted);
		opacity: 0.55;
	}

	.cell.today {
		border: 2px solid var(--ink);
		font-weight: 800;
	}

	.cell.group {
		border: 2px solid var(--accent);
		color: var(--accent-text);
		font-weight: 800;
	}

	.cell.mine {
		background: var(--accent);
		color: var(--on-accent);
	}

	.event {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 10px;
	}

	.event-day {
		flex: 0 0 auto;
		width: 34px;
		height: 34px;
		border-radius: 3px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 18px;
		border: 2px solid var(--accent);
		color: var(--accent-text);
	}

	.event-day.mine {
		background: var(--accent);
		color: var(--on-accent);
	}

	.event-name {
		font-weight: 700;
	}

	.past {
		overflow: hidden;
	}

	.past-toggle {
		width: 100%;
		min-height: 52px;
		padding: 0 16px;
		border: 0;
		background: transparent;
		display: flex;
		align-items: center;
		gap: 10px;
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 20px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		cursor: pointer;
		text-align: left;
	}

	.arrow {
		display: inline-block;
		transition: transform 0.15s;
	}

	.arrow.open {
		transform: rotate(90deg);
	}

	.pad {
		margin: 0;
		padding: 0 16px 16px;
	}

	.past-row {
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		padding: 12px 16px;
		border-top: 1px solid var(--line);
	}

	.past-info {
		flex: 1 1 260px;
	}

	.past-link {
		font-weight: 700;
		color: var(--accent-text);
	}

	@media (max-width: 700px) {
		.people {
			border-left: 0;
			border-top: 1px solid var(--line);
		}

		.countdown {
			flex-basis: 100%;
			flex-direction: row;
			gap: 10px;
			padding: 10px;
		}

		.days {
			font-size: 34px;
		}
	}
</style>
