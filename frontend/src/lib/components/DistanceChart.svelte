<script lang="ts">
	import type { Snippet } from 'svelte';
	import { nearestIndex } from '#lib/activities.ts';

	/**
	 * Zone de graphique en fonction de la distance : le survol (souris ou doigt) donne
	 * l'indice du point le plus proche. Le contenu SVG est dessiné dans une boîte 800 × height.
	 */
	let {
		distances,
		idx = $bindable(null),
		height,
		label,
		children
	}: {
		distances: (number | null)[];
		idx: number | null;
		height: number;
		label: string;
		children: Snippet;
	} = $props();

	const total = $derived(distances.at(-1) ?? 0);
	const cursor = $derived(idx === null || !total ? null : ((distances[idx] ?? 0) / total) * 100);

	function track(event: PointerEvent) {
		const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
		const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
		idx = nearestIndex(distances, ratio * total);
	}

	function step(event: KeyboardEvent) {
		const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1 };
		if (!(event.key in moves)) return;
		event.preventDefault();
		const next = (idx ?? 0) + moves[event.key] * Math.max(1, Math.round(distances.length / 100));
		idx = Math.min(distances.length - 1, Math.max(0, next));
	}
</script>

<!-- Les flèches gauche / droite déplacent aussi le curseur, pour le clavier. -->
<div
	class="chart"
	style:height="{height}px"
	role="slider"
	tabindex="0"
	aria-label={label}
	aria-valuemin={0}
	aria-valuemax={Math.round(total)}
	aria-valuenow={idx === null ? undefined : Math.round(distances[idx] ?? 0)}
	aria-valuetext={idx === null
		? undefined
		: `km ${((distances[idx] ?? 0) / 1000).toFixed(2).replace('.', ',')}`}
	onpointermove={track}
	onpointerdown={track}
	onkeydown={step}
>
	<svg viewBox="0 0 800 {height}" preserveAspectRatio="none" aria-hidden="true">
		{@render children()}
	</svg>
	{#if cursor !== null}
		<div class="cursor" style:left="{cursor}%"></div>
	{/if}
</div>

<style>
	.chart {
		position: relative;
		touch-action: pan-y;
		cursor: crosshair;
	}

	.chart:focus-visible {
		outline-offset: 4px;
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
		overflow: visible;
	}

	.cursor {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		margin-left: -1px;
		background: var(--ink);
		pointer-events: none;
	}
</style>
