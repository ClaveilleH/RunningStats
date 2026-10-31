<script lang="ts">
	import '@fontsource/barlow/400.css';
	import '@fontsource/barlow/600.css';
	import '@fontsource/barlow/700.css';
	import '@fontsource/barlow-condensed/700.css';
	import '@fontsource/barlow-condensed/800.css';
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>RunningStats</title>
</svelte:head>

{@render children()}
