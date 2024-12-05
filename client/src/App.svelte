<script>
  let rand = -1;

  function getRand() {
    fetch("./rand")
      .then(d => d.text())
      .then(d => (rand = d));
  }
</script>

<button on:click={getRand}>Get a random number</button>
<button> <a href={rand}>Link</a> </button>
