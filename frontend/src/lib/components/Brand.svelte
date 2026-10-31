<script lang="ts">
	import { resolve } from '$app/paths';
</script>

<a href={resolve('/(app)')} class="brand">
	<svg
		width="30"
		height="30"
		viewBox="0 0 24 24"
		fill="none"
		stroke="var(--accent)"
		stroke-width="2.4"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"><path d="M2 20l7-12 4 6 3-4 6 10z" /></svg
	>
	RunningStats
</a>

<style>
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--header-ink);
		text-decoration: none;
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 26px;
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}
</style>
