<script lang="ts">
	import { nearestIndex, projector, type Points } from '#lib/activities.ts';

	// idx : point survolé sur le profil ou les courbes (partagé avec la page).
	let { points, idx }: { points: Points; idx: number | null } = $props();

	const W = 800;
	const H = 420;

	// Points avec GPS seulement (piste d'athlétisme sans GPS, tunnel…).
	const gps = $derived(
		points.lat
			.map((lat, i) => [lat, points.lon[i], i] as const)
			.filter((p): p is readonly [number, number, number] => p[0] !== null && p[1] !== null)
	);
	const project = $derived(
		projector(
			gps.map(([lat, lon]) => [lat, lon]),
			W,
			H,
			36
		)
	);
	const path = $derived(
		gps
			.map(([lat, lon], i) => {
				const [x, y] = project(lat, lon);
				return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
			})
			.join(' ')
	);

	/** Position sur la carte du point d'indice i (ou du point GPS le plus proche). */
	function at(i: number): [number, number] | null {
		const lat = points.lat[i];
		const lon = points.lon[i];
		if (lat !== null && lon !== null) return project(lat, lon);
		return null;
	}

	const total = $derived(points.distance_m.at(-1) ?? 0);
	// Un repère tous les 5 km (tous les km pour une sortie de moins de 8 km).
	const every = $derived(total < 8000 ? 1000 : total < 30000 ? 5000 : 10000);
	const marks = $derived.by(() => {
		const result: { label: string; x: number; y: number }[] = [];
		for (let d = every; d < total - every / 4; d += every) {
			const pos = at(nearestIndex(points.distance_m, d));
			if (pos) result.push({ label: String(d / 1000), x: pos[0], y: pos[1] });
		}
		return result;
	});
	const start = $derived(gps.length ? project(gps[0][0], gps[0][1]) : null);
	const finish = $derived(gps.length ? project(gps.at(-1)![0], gps.at(-1)![1]) : null);
	const selected = $derived(idx === null ? null : at(idx));
</script>

{#if gps.length > 1}
	<div class="map">
		<svg
			viewBox="0 0 {W} {H}"
			preserveAspectRatio="xMidYMid meet"
			role="img"
			aria-label="Carte du parcours"
		>
			<path d={path} class="casing" />
			<path d={path} class="route" />
			{#each marks as m (m.label)}
				<circle cx={m.x} cy={m.y} r="13" class="mark" />
				<text x={m.x} y={m.y + 5} class="mark-label">{m.label}</text>
			{/each}
			{#if finish}
				<circle cx={finish[0]} cy={finish[1]} r="7" class="finish" />
			{/if}
			{#if start}
				<!-- Damier : départ. -->
				<rect x={start[0] - 9} y={start[1] - 9} width="18" height="18" class="flag-dark" />
				<rect x={start[0] - 9} y={start[1] - 9} width="9" height="9" class="flag-light" />
				<rect x={start[0]} y={start[1]} width="9" height="9" class="flag-light" />
			{/if}
			{#if selected}
				<circle cx={selected[0]} cy={selected[1]} r="9" class="selected" />
			{/if}
		</svg>
		<div class="legend">
			<span><strong>Damier</strong> départ</span>
			<span><strong>Rond</strong> arrivée</span>
			<span><strong>Repères</strong> tous les {every / 1000} km</span>
		</div>
	</div>
{:else}
	<p class="no-gps">Pas de tracé GPS pour cette sortie.</p>
{/if}

<style>
	.map {
		position: relative;
		background: var(--map);
	}

	svg {
		display: block;
		width: 100%;
		height: 420px;
	}

	.casing {
		fill: none;
		stroke: var(--surface);
		stroke-width: 9;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.route {
		fill: none;
		stroke: var(--accent);
		stroke-width: 5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.mark {
		fill: var(--surface);
		stroke: var(--ink);
		stroke-width: 2;
	}

	.mark-label {
		text-anchor: middle;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 14px;
		fill: var(--ink);
	}

	.flag-dark,
	.finish {
		fill: var(--ink);
	}

	.finish {
		stroke: var(--surface);
		stroke-width: 3;
	}

	.flag-light {
		fill: var(--surface);
	}

	.selected {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 3;
	}

	.legend {
		position: absolute;
		left: 14px;
		bottom: 14px;
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 6px 10px;
		font-size: 13px;
		color: var(--muted);
	}

	.legend strong {
		color: var(--ink);
	}

	.no-gps {
		margin: 0;
		padding: 40px;
		text-align: center;
		color: var(--muted);
		background: var(--map);
	}

	@media (max-width: 600px) {
		svg {
			height: 300px;
		}
	}
</style>
