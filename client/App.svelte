<script>
  import { onMount } from 'svelte';
  let initialised = "";
  let result = "";
  let searchTerm = 'John Summit';

  function init() {
    fetch("./init")
      .then(d => d.text())
      .then(d => (initialised = d));
  }

  function search() {
    fetch(`./search/${searchTerm}`)
      .then(d => d.json())
      .then(d => (result = d));
  }

  onMount(() => {
		console.log('the component has mounted');
    init()
	});

</script>

<input value={searchTerm} />
<button on:click={search}>Search</button>
{initialised}
<div>{result}</div>