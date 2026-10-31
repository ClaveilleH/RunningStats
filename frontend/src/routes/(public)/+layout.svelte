<script lang="ts">
	import Brand from '#lib/components/Brand.svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<!-- Pages accessibles sans être connecté : connexion, invitation. -->
<header>
	<Brand />
</header>

<main>
	<div class="card">
		{@render children()}
	</div>
</main>

<style>
	header {
		background: var(--header);
		border-bottom: 4px solid var(--accent);
		min-height: 68px;
		padding: 0 24px;
		display: flex;
		align-items: center;
	}

	main {
		padding: 48px 16px;
		display: flex;
		justify-content: center;
	}

	.card {
		width: 100%;
		max-width: 420px;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--radius);
		padding: 28px 24px;
	}
</style>
