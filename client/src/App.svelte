<script>
  import { onMount } from 'svelte';
  const Details = Object.freeze({
    Main: 'main',
    ArtistTop10: 'at10',
    ArtistLabels: 'al',
    ArtistTracks: 'all',
  })

  let loading = false;

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

  function toggleDetails(detail) {
    switch (detail) {
      case Details.Main:
        setMainView()
        break;
      case Details.ArtistLabels:
        isOpenArtistsDetail = false;
        isOpenArtistLabelByDate = true;
        break;   
      case Details.ArtistTop10:
        isOpenArtistsDetail = false;
        isOpenArtistTop10 = true;
        break;   
      case Details.ArtistTracks:
        isOpenArtistsDetail = false;
        isOpenArtistTracksByLabel = true;
        break;   
      default:
        break;
    }
  }

  function setMainView() {
    isOpenArtistsDetail = true;
    isOpenArtistLabelByDate = false;
    isOpenArtistTracksByLabel = false;
    isOpenArtistTop10 = false;
  }

  function search() {
    loading = true;
    toggleDetails(Details.Main)
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
  }

  function get_all_artists_for_label(slug, id) {
    fetch(`./label/${slug}/${id}/artists`)
      .then(d => ( console.log(d) ));
  }

  onMount(() => {
		console.log('the component has mounted');
	});

</script>

<input bind:value={searchTerm} placeholder="Enter an artist or label"/>
<button on:click={search}>Search</button>

{#if loading}
  Loading......
{/if}

  {#if !!artists}
  <details open={isOpenArtistsDetail} 
    on:toggle={e => {
      if (e.target.open) 
        toggleDetails(Details.Main)
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
    if (e.target.open) 
      toggleDetails(Details.ArtistLabels)
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

  <details class="detail" id='artist-top-10' open={isOpenArtistTop10} 
    on:toggle={e => {
      if (e.target.open) 
        toggleDetails(Details.ArtistTop10)
      }}>
    <summary><b>Top 10 Tracks</b></summary>
    <div class="tracks flex">

    {#each artistTop10 as track}
    <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
    <div class="track">  
        <img width="128" src="{track.image}" alt="{track.slug}-img"> 
        <audio width="320" height="240" src="{track.sample}" controls> </audio>
        <div class="track-info">
          <h4>{track.name}</h4>
          <div class="title">Artists</div>
          {#each track.artists as artist}
          <div>
            <div><img width="48" src="{artist.image}" alt="{artist.slug}-img"> </div>
            <div>{artist.name}</div>
          </div>
          {/each}
          {#if track.remixers.length > 0}
          <div class="title">Remixed By</div>
            {#each track.remixers as artist}
            <div>
              <div><img width="48" src="{artist.image}" alt="{artist.slug}-img"> </div>
              <div>{artist.name}</div>
            </div>
            {/each}
          {/if}
        </div>
      </div>
    {/each}
    </div>
  </details>

  <details open={isOpenArtistTracksByLabel} 
    on:toggle={e => {
      if (e.target.open) 
        toggleDetails(Details.ArtistTracks)
      }}>
  <summary><b>All Tracks By Date</b></summary>
  {#each artistTracksByLabel as tracksByLabel}
    <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
    <div style="background-color: #efefef;">  
      <h4>{tracksByLabel.label.name}</h4>
      <img width="128" src="{tracksByLabel.label.image}" alt="{tracksByLabel.label.slug}-img"> 
    </div>

    <div class="tracks flex">
      {#each tracksByLabel.tracks as track}
      <!-- <div on:click={() => get_labels(artist.slug, artist.id)}> -->
      <div class="track">  
          <img width="128" src="{track.image}" alt="{track.slug}-img"> 
          <audio width="320" height="240" src="{track.sample}" controls> </audio>
          <div class="track-info">
            <h4>{track.name}</h4>
            <div class="title">Artists</div>
            {#each track.artists as artist}
            <div>
              <div><img width="48" src="{artist.image}" alt="{artist.slug}-img"> </div>
              <div>{artist.name}</div>
            </div>
            {/each}
            {#if track.remixers.length > 0}
            <div class="title">Remixed By</div>
              {#each track.remixers as artist}
              <div>
                <div><img width="48" src="{artist.image}" alt="{artist.slug}-img"> </div>
                <div>{artist.name}</div>
              </div>
              {/each}
            {/if}
          </div>
        </div>
      {/each}
      </div>
  {/each}
  </details>

  {/if}