<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<!-- Accueil provisoire, en attendant la page des maquettes. -->
<h1 class="display">Bonjour {data.me.display_name}</h1>
<p>Tu es connecté{data.me.role === 'admin' ? ' en tant qu’admin' : ''}.</p>

<style>
	h1 {
		margin: 0 0 8px;
		font-size: 32px;
	}
</style>
