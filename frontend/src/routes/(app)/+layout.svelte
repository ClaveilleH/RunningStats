<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api.ts';
	import Brand from '#lib/components/Brand.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const initials = $derived(
		data.me.display_name
			.split(/\s+/)
			.map((w) => w[0])
			.join('')
			.slice(0, 2)
			.toUpperCase()
	);

	async function logout() {
		await api('/auth/logout', { method: 'POST' }).catch(() => {});
		await invalidateAll();
		await goto(resolve('/(public)/login'), { replaceState: true });
	}
</script>

<!-- Bandeau provisoire : la navigation des maquettes viendra avec les pages. -->
<header>
	<Brand />
	<div class="right">
		<span class="avatar" title={data.me.display_name} aria-hidden="true">{initials}</span>
		<button class="button-ghost" type="button" onclick={logout}>Se déconnecter</button>
	</div>
</header>

<main>
	{@render children()}
</main>

<style>
	header {
		background: var(--header);
		border-bottom: 4px solid var(--accent);
		min-height: 68px;
		padding: 0 24px;
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 16px;
	}

	.right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.avatar {
		width: 40px;
		height: 40px;
		border-radius: var(--radius);
		background: #2f6f8f;
		color: #ffffff;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 17px;
	}

	main {
		max-width: 1400px;
		margin: 0 auto;
		padding: 28px 24px;
	}
</style>
