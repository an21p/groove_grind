<script>
  import { onMount } from 'svelte';
  const Pages = Object.freeze({
    Main: 'main',
    Artist: 'artist',
    Label: 'label',
  })
  let loading = false;

  // let page = Pages.Main;
  let artists = null;
  let labels = null;
  let searchTerm = "John Summit";
  let isOpenArtistsDetail = true;

  let artist = null;
  let artistLabelByDate = null;
  let artistTracksByLabel = null;
  let artistTop10 = null
  let isOpenArtistLabelByDate = false;
  let isOpenArtistTracksByLabel = false;
  let isOpenArtistTop10 = false;


  let label = null;
  let labelArtists = null;
  let labelTop10 = null;


  // function go_to_page(p) {
  //   page = p
  // }

  function setMainView() {
    isOpenArtistsDetail = true;
    isOpenArtistLabelByDate = false;
    isOpenArtistTracksByLabel = false;
    isOpenArtistTop10 = false;
  }

  function search() {
    // go_to_page(Pages.Main)
    loading = true;
    setMainView();
    artists = null;
    labels = null;
    fetch(`./search/${searchTerm}`)
      .then(d => d.json())
      .then(d => {        
        artists = d.artists;
        labels = d.labels;
        loading = false;
      });
  }

  function get_labels_by_date_for_artist(slug, id) {
    loading = true;
    artist = null;
    artistLabelByDate = null;
    artistTop10 = null;
    artistTracksByLabel = null;
    fetch(`./artist/${slug}/${id}/labels`)
      .then(d => d.json())
      .then(d => {
        artist = d.artist;
        artistLabelByDate = d.labelsByDate;
        artistTop10 = d.top10;
        artistTracksByLabel = d.all;
        isOpenArtistsDetail = false;
        isOpenArtistLabelByDate = true;
        loading = false;
      })
      // .then(() => go_to_page(Pages.Artist) );
  }

  function get_all_artists_for_label(slug, id) {
    fetch(`./label/${slug}/${id}/artists`)
      // .then(d => d.json())
      .then(d => ( console.log(d) ));
  }

  onMount(() => {
		console.log('the component has mounted');
    // go_to_page(Pages.Main)

	});

</script>

<input bind:value={searchTerm} placeholder="Enter an artist or label"/>
<button on:click={search}>Search</button>

{#if loading}
  Loading......
{/if}

<!-- {#if page === Pages.Main} -->
  {#if !!artists}
  <details open={isOpenArtistsDetail} 
          on:toggle={e => {            
            if (e.target.open) setMainView()
            }}>
    <summary><b>Artists</b></summary>
    {#each artists as artist}
      <div on:click={() => get_labels_by_date_for_artist(artist.slug, artist.id)}>
        <h4>{artist.name}</h4>
        <img width="128" src="{artist.image}" alt="{artist.slug}-img"> 
        <br>
      </div>
    {/each}
  </details>
  {/if}
<!-- {/if} -->



<!-- {#if page === Pages.Artist} -->

  {#if !!artist}
  <h1>Artist</h1>
  <div>
    <h4>{artist.name}</h4>
    <img width="256" src="{artist.image}" alt="{artist.slug}-img"> 
    {#if !!artist.bio} <br> <span>{artist.bio}</span> {/if}
    <hr>
  </div>

  <details open={isOpenArtistLabelByDate} 
          on:toggle={e => {
            if (e.target.open) {
              isOpenArtistsDetail = false;
              isOpenArtistLabelByDate = true;
            }
            }}>
    <summary><b>Labels By Date</b></summary>
    {#each artistLabelByDate as labelItem}
      <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
      <div>  
        <img width="48" src="{labelItem.label.image}" alt="{labelItem.label.slug}-img">
        <b>{labelItem.label.name}</b>
        <div>First Released on {labelItem.label.name} on {labelItem.date}</div>
      </div>
    {/each}
  </details>

  <details open={isOpenArtistTop10} 
          on:toggle={e => {
            if (e.target.open)
            {
              isOpenArtistsDetail = false;
              isOpenArtistTop10 = true;
            }
            }}>
    <summary><b>Top 10 Tracks</b></summary>
    {#each artistTop10 as track}
    <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
    <div>  
      <h4>{track.name}</h4>
      <div>Artists</div>
      {#each track.artists as artist}
      <div>
        <img width="36" src="{artist.image}" alt="{artist.slug}-img"> 
        <span>{artist.name}</span>
      </div>
      {/each}
      {#if !!track.remixers}
        <div>Remixed By</div>
        {#each track.remixers as artist}
        <div>
          <img width="36" src="{artist.image}" alt="{artist.slug}-img"> 
          <span>{artist.name}</span>
        </div>
        {/each}
      {/if}
      <br>
      <img width="128" src="{track.image}" alt="{track.slug}-img"> 
      <audio width="320" height="240" src="{track.sample}" controls> </audio>
    </div>
  {/each}
  </details>

  <details open={isOpenArtistTracksByLabel} 
          on:toggle={e => {
            if (e.target.open) {
              isOpenArtistsDetail = false;
              isOpenArtistTracksByLabel = true;
            }
            }}>
  <summary><b>All Tracks By Date</b></summary>
  {#each artistTracksByLabel as tracksByLabel}
    <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
    <div style="background-color: #efefef;">  
      <h4>{tracksByLabel.label.name}</h4>
      <img width="128" src="{tracksByLabel.label.image}" alt="{tracksByLabel.label.slug}-img"> 
    </div>
    {#each tracksByLabel.tracks as track}
      <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
      <div>  
        <h4>{track.name}</h4>
        <div>Artists</div>
        {#each track.artists as artist}
          <img width="36" src="{artist.image}" alt="{artist.slug}-img"> 
          <span>{artist.name}</span>
        {/each}
        <div>Remixed By</div>
        {#each track.remixers as artist}
          <img width="36" src="{artist.image}" alt="{artist.slug}-img"> 
          <span>{artist.name}</span>
        {/each}
        <br>
        <img width="128" src="{track.image}" alt="{track.slug}-img"> 
        <audio width="320" height="240" src="{track.sample}" controls> </audio>
      </div>
    {/each}
  {/each}
  </details>

  {/if}
<!-- {/if} -->



<style>

details {
  padding: 12px; 
  border: 12px solid #efefef;
  border-radius: 5px;
}
</style>