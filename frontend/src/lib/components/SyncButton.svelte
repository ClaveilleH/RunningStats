<script lang="ts">
	import { timeAgo } from '#lib/format.ts';
	import type { GarminSync } from '#lib/garmin.svelte.ts';

	let { sync, label = 'Synchroniser' }: { sync: GarminSync; label?: string } = $props();
</script>

<div class="sync">
	<button class="button" type="button" onclick={() => sync.start()} disabled={sync.syncing}>
		<svg
			width="18"
			height="18"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2.4"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
			class:spin={sync.syncing}
			><path d="M21 12a9 9 0 01-15.5 6.2L3 16" /><path d="M3 12a9 9 0 0115.5-6.2L21 8" /><path
				d="M21 3v5h-5"
			/><path d="M3 21v-5h5" /></svg
		>
		{label}
	</button>
	<p class="state" role="status">
		{#if sync.syncing}
			<span class="running"><span class="dot"></span>Synchronisation en cours…</span>
		{:else if sync.notice}
			<span class="notice">{sync.notice}</span>
		{:else if sync.garmin?.last_sync_at}
			Dernière synchro {timeAgo(sync.garmin.last_sync_at)}
		{:else}
			Pas encore synchronisé
		{/if}
	</p>
</div>

<style>
	.sync {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 10px;
	}

	.button:disabled {
		cursor: progress;
	}

	.state {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}

	.running {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
		color: var(--accent-text);
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
	}

	.notice {
		color: var(--danger);
		font-weight: 600;
	}

	.spin {
		animation: spin 1.2s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.spin {
			animation: none;
		}
	}
</style>
