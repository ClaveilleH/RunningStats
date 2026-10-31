<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
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

<!-- L'entrée Amis arrive avec sa page. -->
<header>
	<Brand />
	<nav aria-label="Navigation principale">
		<a href={resolve('/(app)')} aria-current={page.route.id === '/(app)' ? 'page' : undefined}
			>Accueil</a
		>
		<a
			href={resolve('/(app)/activities')}
			aria-current={page.route.id?.startsWith('/(app)/activities') ? 'page' : undefined}
			>Activités</a
		>
		<a
			href={resolve('/(app)/races')}
			aria-current={page.route.id?.startsWith('/(app)/races') ? 'page' : undefined}>Courses</a
		>
	</nav>
	<div class="right">
		<a
			href={resolve('/(app)/settings')}
			class="settings"
			aria-label="Réglages"
			aria-current={page.route.id === '/(app)/settings' ? 'page' : undefined}
		>
			<svg
				width="20"
				height="20"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"
				><circle cx="12" cy="12" r="3" /><path
					d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"
				/></svg
			>
		</a>
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
		gap: 28px;
	}

	nav {
		display: flex;
		gap: 2px;
		flex-wrap: wrap;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 18px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	nav a {
		padding: 8px 12px;
		color: var(--header-muted);
		text-decoration: none;
		border-bottom: 3px solid transparent;
	}

	nav a[aria-current='page'] {
		color: var(--header-ink);
		border-bottom-color: var(--accent);
	}

	.right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.settings {
		width: 44px;
		height: 44px;
		border-radius: var(--radius);
		border: 1px solid var(--header-line);
		color: var(--header-ink);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.settings[aria-current='page'] {
		border-color: var(--accent);
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
