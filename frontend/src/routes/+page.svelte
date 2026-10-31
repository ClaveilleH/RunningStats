<script lang="ts">
	// Page provisoire : vérifie seulement que le front joint l'API.
	let apiStatus = $state('…');

	$effect(() => {
		fetch('/api/health')
			.then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
			.then((body: { status: string }) => (apiStatus = body.status))
			.catch(() => (apiStatus = 'injoignable'));
	});
</script>

<svelte:head>
	<title>RunningStats</title>
</svelte:head>

<h1>RunningStats</h1>
<p>API : {apiStatus}</p>
