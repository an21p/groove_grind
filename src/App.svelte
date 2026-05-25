<script>
	import { onMount } from 'svelte';
	import { tweened } from 'svelte/motion';
	import { cubicOut } from 'svelte/easing';
	import { client, session, loginPopup, setManualToken, setManualSession, logout, refreshSession, manualTokenSnippet, manualSessionSnippet } from './stores/session';
	import { streamArtist } from './beatport/catalog';

	let connected = false;
	const unsubSession = session.subscribe((s) => (connected = s.connected));

	// Login-gate UI state. The popup relay is locked to beatport.com's origin, so
	// the manual /api/auth/session path is primary; the popup is a fallback.
	let manualTokenInput = '';
	let enableRefresh = true;
	let loginError = null;
	let showPopupFallback = false;

	$: manualSnippet = enableRefresh ? manualSessionSnippet : manualTokenSnippet;

	async function connect() {
		loginError = null;
		try {
			await loginPopup();
		} catch (e) {
			loginError = (e && e.userMessage) || 'Popup login did not complete. Use the manual setup above.';
		}
	}

	function submitManual() {
		const v = manualTokenInput.trim();
		if (!v) return;
		loginError = null;
		if (enableRefresh) {
			let parsed;
			try {
				parsed = JSON.parse(v);
			} catch (_) {
				parsed = null;
			}
			if (!parsed || !parsed.access_token) {
				loginError = "That doesn't look like a session blob. With auto-refresh on, paste the full output of the command (a {access_token, refresh_token} object).";
				return;
			}
			setManualSession(parsed.access_token, parsed.refresh_token || '');
		} else {
			setManualToken(v);
		}
		manualTokenInput = '';
	}

	function clearToken() {
		logout();
		loginError = null;
		manualTokenInput = '';
	}

	let cmdCopied = false;
	async function copyCmd() {
		try {
			await navigator.clipboard.writeText(manualSnippet);
			cmdCopied = true;
			setTimeout(() => (cmdCopied = false), 2000);
		} catch (_e) {
			loginError = 'Could not copy automatically — select the command and copy it manually.';
		}
	}

	const tweenedTracks = tweened(0, { duration: 500, easing: cubicOut });
	const tweenedLabels = tweened(0, { duration: 500, easing: cubicOut });
	const tweenedTop10 = tweened(0, { duration: 700, easing: cubicOut });

	let loading = false;
	let searchTerm = '';
	let hasSearched = false;

	let artists = null;
	let labels = null;
	let searchError = null;   // string | null

	let artist = null;
	let artistTop10 = null;
	let artistLabelByDate = null;
	let artistTracksByLabel = null;
	let artistView = 'labels';

	// Streaming state for /artist/.../labels (NDJSON)
	let streamingCatalog = false;
	let tracksLoaded = 0;
	let progressiveCatalog = [];   // [{label, tracks}]
	let streamError = null;
	let activeStreamController = null;

	// Audio player — single global element, swaps src per track
	let audioEl;
	let currentTrackId = null;
	let isPlaying = false;
	let currentTime = 0;
	let duration = 0;

	// Marquee clock for the masthead
	let clock = '';
	onMount(() => {
		const tick = () => {
			const d = new Date();
			clock = d.toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
		};
		tick();
		const id = setInterval(tick, 1000);
		return () => { clearInterval(id); unsubSession(); };
	});

	function handleKeydown(e) {
		if (e.key === 'Enter' && searchTerm.trim()) search();
	}

	function search() {
		if (!searchTerm.trim()) return;
		loading = true;
		hasSearched = true;
		artist = null;
		artists = null;
		labels = null;
		searchError = null;
		streamError = null;
		(async () => {
			try {
				const { artists: a, labels: l } = await client.search(searchTerm.trim());
				artists = a;
				labels = l;
				loading = false;
			} catch (e) {
				searchError = (e && e.userMessage) || 'Beatport is temporarily unavailable. Please try again in a moment.';
				if (e && e.code === 'auth') refreshSession();
				loading = false;
			}
		})();
	}

	async function openArtist(slug, id) {
		if (activeStreamController) activeStreamController.abort();
		const controller = new AbortController();
		activeStreamController = controller;

		loading = true;
		artist = null;
		artistTop10 = null;
		artistLabelByDate = null;
		artistTracksByLabel = null;
		artistView = 'labels';
		streamingCatalog = true;
		tracksLoaded = 0;
		progressiveCatalog = [];
		streamError = null;
		searchError = null;

		try {
			await streamArtist(client, id, handleStreamEvent, controller.signal);
		} catch (err) {
			if (err && err.name !== 'AbortError') {
				streamError = (err && err.userMessage) || (err && err.message) || String(err);
				if (err && err.code === 'auth') refreshSession();
			}
		} finally {
			if (activeStreamController === controller) activeStreamController = null;
			loading = false;
			streamingCatalog = false;
		}
	}

	function handleStreamEvent(evt) {
		if (evt.type === 'artist') {
			artist = evt.artist;
			artistTop10 = evt.top10;
			loading = false;
			window.scrollTo({ top: 0, behavior: 'smooth' });
		} else if (evt.type === 'tracks') {
			tracksLoaded = evt.cumulative;
			mergeProgressiveTracks(evt.tracks);
		} else if (evt.type === 'done') {
			artistLabelByDate = evt.labelsByDate;
			artistTracksByLabel = evt.all;
			streamingCatalog = false;
		} else if (evt.type === 'error') {
			streamError = evt.message || 'Beatport is temporarily unavailable. Please try again in a moment.';
			streamingCatalog = false;
			// streamArtist emits auth failures as events (never throws), so the gate
			// must be re-shown from here, not from openArtist's outer catch.
			if (evt.code === 'auth') refreshSession();
		}
	}

	function mergeProgressiveTracks(newTracks) {
		const next = progressiveCatalog.slice();
		const indexById = new Map(next.map((g, i) => [g.label.id, i]));
		for (const t of newTracks) {
			const lid = t.label && t.label.id;
			if (lid == null) continue;
			const idx = indexById.get(lid);
			if (idx === undefined) {
				next.push({ label: t.label, tracks: [t] });
				indexById.set(lid, next.length - 1);
			} else {
				next[idx] = { label: next[idx].label, tracks: [...next[idx].tracks, t] };
			}
		}
		progressiveCatalog = next;
	}

	function backToSearch() {
		if (activeStreamController) { activeStreamController.abort(); activeStreamController = null; }
		streamingCatalog = false;
		streamError = null;
		searchError = null;
		artist = null;
		stopAudio();
	}

	function setView(v) { artistView = v; }

	// Audio handling
	function togglePlay(track) {
		if (!track.sample) return;
		if (currentTrackId === track.id) {
			if (isPlaying) audioEl.pause();
			else audioEl.play();
		} else {
			currentTrackId = track.id;
			audioEl.src = track.sample;
			audioEl.play();
		}
	}
	function stopAudio() {
		if (audioEl) { audioEl.pause(); audioEl.currentTime = 0; }
		currentTrackId = null;
		isPlaying = false;
	}
	function onAudioPlay() { isPlaying = true; }
	function onAudioPause() { isPlaying = false; }
	function onAudioEnded() { isPlaying = false; }
	function onAudioTime() { currentTime = audioEl.currentTime || 0; duration = audioEl.duration || 0; }

	function seek(e, track) {
		if (currentTrackId !== track.id || !duration) return;
		const rect = e.currentTarget.getBoundingClientRect();
		const ratio = (e.clientX - rect.left) / rect.width;
		audioEl.currentTime = Math.max(0, Math.min(1, ratio)) * duration;
	}

	function fmt(sec) {
		if (!sec || isNaN(sec)) return '0:00';
		const m = Math.floor(sec / 60);
		const s = Math.floor(sec % 60).toString().padStart(2, '0');
		return `${m}:${s}`;
	}

	function pad2(n) { return String(n).padStart(2, '0'); }
	function pad3(n) { return String(n).padStart(3, '0'); }

	function formatDate(iso) {
		if (!iso) return '';
		const d = new Date(iso);
		if (isNaN(d)) return iso;
		const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
		return `${pad2(d.getDate())} ${months[d.getMonth()]} ${d.getFullYear()}`;
	}

	function yearOf(iso) {
		if (!iso) return '';
		const d = new Date(iso);
		return isNaN(d) ? '' : String(d.getFullYear());
	}

	$: progressPct = duration ? (currentTime / duration) * 100 : 0;

	$: totalTracks = artistTracksByLabel
		? artistTracksByLabel.reduce((a, g) => a + g.tracks.length, 0)
		: tracksLoaded;

	$: totalLabels = artistLabelByDate
		? artistLabelByDate.length
		: progressiveCatalog.length;

	$: firstActiveYear = artistLabelByDate && artistLabelByDate.length
		? yearOf(artistLabelByDate[0].date)
		: (progressiveCatalog.length
			? (function () {
				let earliest = null;
				for (const g of progressiveCatalog) {
					for (const t of g.tracks) {
						if (!earliest || (t.release_date && t.release_date < earliest)) earliest = t.release_date;
					}
				}
				return earliest ? yearOf(earliest) : '—';
			})()
			: '—');

	$: catalogForDisplay = artistTracksByLabel || progressiveCatalog;

	// Drive tweened counters — instant-snap on artist reset (value 0), animate on increase.
	$: tweenedTracks.set(totalTracks, totalTracks === 0 ? { duration: 0 } : undefined);
	$: tweenedLabels.set(totalLabels, totalLabels === 0 ? { duration: 0 } : undefined);
	$: tweenedTop10.set(artistTop10 ? artistTop10.length : 0, (!artistTop10) ? { duration: 0 } : undefined);
</script>

<div class="frame">
	<!-- Top band -->
	<header class="band">
		<div class="band-left">
			<span class="caps">Vol. 01 · No. 04</span>
		</div>
		<div class="band-center">
			<span class="caps">An archive of electronic catalogs</span>
		</div>
		<div class="band-right">
			<span class="caps">{clock}</span>
		</div>
	</header>

	<!-- Masthead -->
	<section class="masthead">
		<div class="masthead-row">
			<div class="mark">
				<div class="mark-top caps">The</div>
				<h1 class="mark-word">Groove<span class="mark-ampersand">&amp;</span>Grind</h1>
				<div class="mark-sub caps">— a research instrument for the Beatport catalog —</div>
			</div>
		</div>
	</section>

	<!-- Connect gate (manual /api/auth/session path is primary) -->
	{#if !artist && !connected}
		<section class="hero gate">
			<div class="prompt-line">
				<span class="caps prompt-num">Nº 00</span>
				<span class="prompt-dot"></span>
				<span class="caps prompt-label">Connect</span>
			</div>
			<h2 class="section-title" style="margin-top:1rem;">Connect your <em>Beatport</em> account to dig</h2>
			<p class="dossier-bio" style="margin-top:1rem;">
				Groove &amp; Grind reads the Beatport catalog from your browser, on your connection — nothing runs on a server. Hand it a token from your Beatport session:
			</p>

			<div class="manual-setup">
				<div class="why-note">
					<div class="caps mute why-title">Why paste a token?</div>
					<p>
						Beatport has no public app API, so Groove &amp; Grind works through your own Beatport session.
						It used to run on a server with a plain user login — but Beatport now blocks datacenter IPs
						(our Azure host included) and allows only residential connections, so the catalog has to be
						fetched locally, here in your browser. Your token is stored only in this browser's
						<code>localStorage</code>, which other websites can't read.
					</p>
				</div>
				<ol class="manual-steps">
					<li>Sign in to <strong>beatport.com</strong> in this browser.</li>
					<li>Open the devtools console (F12) and run this command:</li>
				</ol>
				<div class="snippet-head">
					<span class="caps mute">Console command</span>
					<button class="copy-btn caps" on:click={copyCmd}>{cmdCopied ? 'Copied ✓' : 'Copy'}</button>
				</div>
				<pre class="manual-snippet">{manualSnippet}</pre>
				<label class="refresh-toggle caps">
					<input type="checkbox" bind:checked={enableRefresh} />
					Keep me signed in (auto-refresh)
				</label>
				<p class="caps mute refresh-note">
					{#if enableRefresh}
						Beatport's web token lasts only ~10 minutes; with auto-refresh on, the app renews it for you using the refresh token. If Beatport declines the refresh, you'll be asked to run the command again.
					{:else}
						You'll paste a bare token that expires in ~10 minutes — you'll re-run the command when it lapses. Turn on auto-refresh to avoid that.
					{/if}
				</p>
				<textarea
					class="token-input"
					bind:value={manualTokenInput}
					rows={enableRefresh ? 6 : 3}
					placeholder={enableRefresh ? 'paste the logged JSON session here' : 'paste the logged token here'}
					autocomplete="off"
					spellcheck="false"
				></textarea>
				<button class="prompt-go ready" style="margin-top:0.75rem;" on:click={submitManual}><span class="caps">Connect</span><span class="go-arrow">→</span></button>
			</div>

			{#if loginError}
				<div class="stream-error caps" style="margin-top:1.25rem;" role="alert">
					<span class="stream-error-label">Connection problem</span>
					<span class="stream-error-msg">{loginError}</span>
				</div>
			{/if}

			<!-- Popup login disabled: Beatport's post-message relay is locked to its own
			     origin, so the popup can't return a code to this app. Kept for reference.
			<div class="prompt-hint" style="margin-top:1.75rem;">
				<button class="suggest" on:click={() => (showPopupFallback = !showPopupFallback)}>Prefer a popup login? (experimental)</button>
			</div>
			{#if showPopupFallback}
				<p class="caps mute" style="margin-top:0.75rem;">
					Beatport may block the popup from returning to this site. If it hangs, use the console method above.
					<button class="suggest" style="margin-left:0.5rem;" on:click={connect}>Try popup login</button>
				</p>
			{/if}
			-->

		</section>
	{/if}

	{#if !artist && connected}
		<section class="hero">
			<div class="clear-token-row">
				<button class="clear-token caps" on:click={clearToken} title="Remove the stored Beatport token from this browser">Clear token</button>
			</div>
			<div class="prompt-line">
				<span class="caps prompt-num">Nº 01</span>
				<span class="prompt-dot"></span>
				<span class="caps prompt-label">Query</span>
			</div>
			<div class="prompt-field">
				<span class="prompt-arrow">↳</span>
				<input
					class="prompt-input"
					bind:value={searchTerm}
					placeholder="whose catalog should we open"
					on:keydown={handleKeydown}
					autocomplete="off"
					spellcheck="false"
				/>
				<button class="prompt-go" class:ready={searchTerm.trim()} on:click={search} aria-label="Search">
					<span class="caps">Dig</span>
					<span class="go-arrow">→</span>
				</button>
			</div>
			<div class="prompt-hint caps mute">
				<span>Try</span>
				<button class="suggest" on:click={() => { searchTerm = 'John Summit'; search(); }}>John Summit</button>
				<span class="sep">·</span>
				<button class="suggest" on:click={() => { searchTerm = 'Fred again..'; search(); }}>Fred again..</button>
				<span class="sep">·</span>
				<button class="suggest" on:click={() => { searchTerm = 'Solomun'; search(); }}>Solomun</button>
				<span class="sep">·</span>
				<button class="suggest" on:click={() => { searchTerm = 'Keinemusik'; search(); }}>Keinemusik</button>
			</div>
		</section>
	{/if}

	<!-- Loading bar -->
	{#if loading}
		<div class="loader" role="status" aria-live="polite">
			<div class="loader-bar"></div>
			<div class="loader-text caps">Scanning index · please hold</div>
		</div>
	{/if}

	<!-- Search connection error (distinct from a zero-result search) -->
	{#if searchError && !artist && !loading}
		<section class="section">
			<div class="stream-error caps" role="alert">
				<span class="stream-error-label">Connection problem</span>
				<span class="stream-error-msg">{searchError}</span>
			</div>
		</section>
	{/if}

	<!-- Artist stream error before artist loaded (e.g. get_artist failed) -->
	{#if streamError && !artist && !loading}
		<section class="section">
			<button class="breadcrumb caps" on:click={backToSearch}>← Back to index</button>
			<div class="stream-error caps" role="alert">
				<span class="stream-error-label">Transmission interrupted</span>
				<span class="stream-error-msg">{streamError}</span>
			</div>
		</section>
	{/if}

	<!-- Artist index (search results) -->
	{#if artists && !artist && !loading && !streamError}
		<section class="section">
			<header class="section-head">
				<div class="section-head-left">
					<div class="caps mute">Section A</div>
					<h2 class="section-title">Artists <em>matching</em> "{searchTerm}"</h2>
				</div>
				<div class="section-head-right caps mute">
					{pad3(artists.length)} result{artists.length === 1 ? '' : 's'}
				</div>
			</header>

			{#if artists.length === 0}
				<div class="empty caps mute">No entries found in the index.</div>
			{:else}
				<ol class="index">
					{#each artists as a, i (a.id)}
						<li class="index-row" on:click={() => openArtist(a.slug, a.id)} style="--d: {i * 40}ms">
							<span class="index-num caps mute">{pad2(i + 1)}</span>
							<div class="index-thumb">
								{#if a.image}<img src={a.image} alt={a.name} loading="lazy" />{/if}
							</div>
							<div class="index-body">
								<div class="index-name">{a.name}</div>
								<div class="index-meta caps mute">Artist · /{a.slug}</div>
							</div>
							<div class="index-cta caps">Open ↗</div>
						</li>
					{/each}
				</ol>
			{/if}

			{#if labels && labels.length > 0}
				<header class="section-head" style="margin-top: 4rem;">
					<div class="section-head-left">
						<div class="caps mute">Section B</div>
						<h2 class="section-title">Labels <em>matching</em> "{searchTerm}"</h2>
					</div>
					<div class="section-head-right caps mute">{pad3(labels.length)} result{labels.length === 1 ? '' : 's'}</div>
				</header>
				<ol class="index">
					{#each labels as l, i (l.id)}
						<li class="index-row static" style="--d: {i * 40}ms">
							<span class="index-num caps mute">{pad2(i + 1)}</span>
							<div class="index-thumb square">
								{#if l.image}<img src={l.image} alt={l.name} loading="lazy" />{/if}
							</div>
							<div class="index-body">
								<div class="index-name">{l.name}</div>
								<div class="index-meta caps mute">Label · /{l.slug}</div>
							</div>
							<div class="index-cta caps mute">—</div>
						</li>
					{/each}
				</ol>
			{/if}
		</section>
	{/if}

	<!-- Artist dossier -->
	{#if artist}
		<section class="section">
			<button class="breadcrumb caps" on:click={backToSearch}>← Back to index</button>

			{#if streamError}
				<div class="stream-error caps">
					<span class="stream-error-label">Transmission interrupted</span>
					<span class="stream-error-msg">{streamError}</span>
				</div>
			{/if}

			<div class="dossier">
				<div class="dossier-main">
					<div class="caps mute dossier-kicker">Artist Dossier · Nº {pad3(artist.id)}</div>
					<h1 class="dossier-name">
						<em>{artist.name}</em>
					</h1>
					{#if artist.bio}
						<p class="dossier-bio">{artist.bio}</p>
					{/if}
				</div>
				<aside class="dossier-portrait">
					{#if artist.image}
						<img src={artist.image} alt={artist.name} />
					{/if}
					<div class="portrait-caption caps mute">Fig. 01 · {artist.name}</div>
				</aside>
			</div>

			<div class="dossier-stats">
				<div class="stat">
					<div class="stat-val">{pad2(Math.floor($tweenedTop10))}</div>
					<div class="caps mute">Top tracks on file</div>
				</div>
				<div class="stat" class:live={streamingCatalog}>
					<div class="stat-val">{pad3(Math.floor($tweenedTracks))}</div>
					<div class="caps mute">Tracks catalogued{streamingCatalog ? ' · live' : ''}</div>
				</div>
				<div class="stat" class:live={streamingCatalog}>
					<div class="stat-val">{pad2(Math.floor($tweenedLabels))}</div>
					<div class="caps mute">Labels of issue{streamingCatalog ? ' · live' : ''}</div>
				</div>
				<div class="stat">
					<div class="stat-val">{firstActiveYear}</div>
					<div class="caps mute">Active since</div>
				</div>
			</div>

			<nav class="tabs">
				<button class="tab caps" class:active={artistView === 'top10'} on:click={() => setView('top10')}>
					<span class="tab-num">I.</span> Top Ten
				</button>
				<button class="tab caps" class:active={artistView === 'labels'} on:click={() => setView('labels')}>
					<span class="tab-num">II.</span> Label Timeline
				</button>
				<button class="tab caps" class:active={artistView === 'all'} on:click={() => setView('all')}>
					<span class="tab-num">III.</span> Full Catalog
				</button>
			</nav>

			<!-- TOP 10 -->
			{#if artistView === 'top10' && artistTop10}
				<div class="tracks-list">
					{#each artistTop10 as t, i (t.slug + i)}
						<article class="track-row" style="--d: {i * 30}ms" class:playing={currentTrackId === t.id && isPlaying}>
							<div class="track-num caps mute">{pad2(i + 1)}</div>
							<div class="track-art">
								{#if t.image}<img src={t.image} alt={t.name} loading="lazy" />{/if}
								<button class="play-btn" on:click={() => togglePlay(t)} disabled={!t.sample} aria-label="Play {t.name}">
									{#if currentTrackId === t.id && isPlaying}
										<span class="pause-icon"></span>
									{:else}
										<span class="play-icon"></span>
									{/if}
								</button>
							</div>
							<div class="track-body">
								<h3 class="track-title"><em>{t.name}</em></h3>
								<div class="track-credit caps mute">
									{#each t.artists as ar, j}{ar.name}{#if j < t.artists.length - 1}, {/if}{/each}
									{#if t.remixers && t.remixers.length > 0}
										<span class="sep">/</span> <span class="mute">rmx</span>
										{#each t.remixers as rm, j}{rm.name}{#if j < t.remixers.length - 1}, {/if}{/each}
									{/if}
								</div>
								<div class="track-label caps mute">— {t.label.name}</div>
							</div>
							<div class="track-player">
								{#if currentTrackId === t.id}
									<div class="scrubber" on:click={(e) => seek(e, t)}>
										<div class="scrubber-fill" style="width: {progressPct}%"></div>
									</div>
									<div class="track-time caps mute">{fmt(currentTime)} / {fmt(duration)}</div>
								{:else if t.sample}
									<div class="track-time caps mute">Preview available</div>
								{:else}
									<div class="track-time caps mute">No preview</div>
								{/if}
							</div>
						</article>
					{/each}
				</div>
			{/if}

			<!-- LABEL TIMELINE -->
			{#if artistView === 'labels' && !artistLabelByDate}
				<div class="tab-placeholder">
					<div class="placeholder-bar"></div>
					<div class="caps mute">
						Compiling timeline · tracks indexed {pad3(Math.floor($tweenedTracks))}{streamingCatalog ? ' · awaiting final pagination' : ''}
					</div>
				</div>
			{/if}
			{#if artistView === 'labels' && artistLabelByDate}
				<div class="timeline">
					{#each artistLabelByDate as item, i (item.label.id + i)}
						<article class="timeline-row" style="--d: {i * 40}ms">
							<div class="timeline-year">
								<div class="year">{yearOf(item.date)}</div>
								<div class="caps mute">{formatDate(item.date)}</div>
							</div>
							<div class="timeline-rail">
								<span class="timeline-dot"></span>
							</div>
							<div class="timeline-body">
								<div class="timeline-logo">
									{#if item.label.image}<img src={item.label.image} alt={item.label.name} loading="lazy" />{/if}
								</div>
								<div>
									<div class="caps mute">Label Nº {pad2(i + 1)} · first release</div>
									<h3 class="timeline-name"><em>{item.label.name}</em></h3>
								</div>
							</div>
						</article>
					{/each}
				</div>
			{/if}

			<!-- FULL CATALOG -->
			{#if artistView === 'all' && catalogForDisplay && catalogForDisplay.length === 0 && streamingCatalog}
				<div class="tab-placeholder">
					<div class="placeholder-bar"></div>
					<div class="caps mute">Requesting catalog · first page en route</div>
				</div>
			{/if}
			{#if artistView === 'all' && catalogForDisplay && catalogForDisplay.length > 0}
				<div class="catalog">
					{#if streamingCatalog}
						<div class="stream-ticker caps">
							<span class="stream-dot"></span>
							Live · {pad3(Math.floor($tweenedTracks))} tracks catalogued · {pad2(Math.floor($tweenedLabels))} labels indexed
						</div>
					{/if}
					{#each catalogForDisplay as group, gi (group.label.id + '-' + gi)}
						<div class="cat-group">
							<header class="cat-group-head">
								<div class="cat-logo">
									{#if group.label.image}<img src={group.label.image} alt={group.label.name} loading="lazy" />{/if}
								</div>
								<div>
									<div class="caps mute">On</div>
									<h3 class="cat-label-name"><em>{group.label.name}</em></h3>
								</div>
								<div class="cat-count caps mute">{pad2(group.tracks.length)} release{group.tracks.length === 1 ? '' : 's'}</div>
							</header>
							<div class="tracks-list dense">
								{#each group.tracks as t, i (t.slug + i)}
									<article class="track-row dense" class:playing={currentTrackId === t.id && isPlaying}>
										<div class="track-num caps mute">{pad2(i + 1)}</div>
										<div class="track-art small">
											{#if t.image}<img src={t.image} alt={t.name} loading="lazy" />{/if}
											<button class="play-btn small" on:click={() => togglePlay(t)} disabled={!t.sample} aria-label="Play {t.name}">
												{#if currentTrackId === t.id && isPlaying}
													<span class="pause-icon"></span>
												{:else}
													<span class="play-icon"></span>
												{/if}
											</button>
										</div>
										<div class="track-body">
											<h4 class="track-title small"><em>{t.name}</em></h4>
											<div class="track-credit caps mute">
												{#each t.artists as ar, j}{ar.name}{#if j < t.artists.length - 1}, {/if}{/each}
												{#if t.remixers && t.remixers.length > 0}
													<span class="sep">/</span> <span class="mute">rmx</span>
													{#each t.remixers as rm, j}{rm.name}{#if j < t.remixers.length - 1}, {/if}{/each}
												{/if}
											</div>
										</div>
										<div class="track-player">
											{#if currentTrackId === t.id}
												<div class="scrubber" on:click={(e) => seek(e, t)}>
													<div class="scrubber-fill" style="width: {progressPct}%"></div>
												</div>
												<div class="track-time caps mute">{fmt(currentTime)} / {fmt(duration)}</div>
											{:else if t.sample}
												<div class="track-time caps mute">Preview</div>
											{:else}
												<div class="track-time caps mute">—</div>
											{/if}
										</div>
									</article>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	{/if}

	<!-- Footer -->
	<footer class="foot">
		<div class="foot-row">
			<div class="caps mute">Groove &amp; Grind · Edition MMXXVI</div>
			<div class="caps mute">Typeset in Fraunces &amp; JetBrains Mono</div>
			<div class="caps mute">Printed on the open web</div>
			{#if connected}
				<button class="caps mute disconnect" on:click={logout}>Disconnect Beatport</button>
			{/if}
		</div>
	</footer>

	<!-- Hidden global audio -->
	<audio
		bind:this={audioEl}
		on:play={onAudioPlay}
		on:pause={onAudioPause}
		on:ended={onAudioEnded}
		on:timeupdate={onAudioTime}
		on:loadedmetadata={onAudioTime}
		preload="metadata"
	></audio>
</div>

<style>
	.frame {
		max-width: 1240px;
		margin: 0 auto;
		padding: 0 var(--gutter) 6rem;
	}

	/* Top band */
	.band {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		padding: 14px 0;
		border-bottom: var(--rule-thin);
	}
	.band-center { text-align: center; }
	.band-right { text-align: right; }
	.band .caps { color: var(--paper-dim); }

	/* Masthead */
	.masthead {
		padding: 3rem 0 2.25rem;
		border-bottom: var(--rule-thin);
	}
	.mark { text-align: center; }
	.mark-top { color: var(--paper-dim); letter-spacing: .28em; }
	.mark-word {
		font-family: var(--serif);
		font-weight: 400;
		font-style: italic;
		font-size: clamp(3.75rem, 13vw, 10rem);
		line-height: 0.88;
		letter-spacing: -0.03em;
		margin: 0.15em 0 0.2em;
		color: var(--paper);
	}
	.mark-ampersand {
		font-style: italic;
		font-weight: 300;
		color: var(--oxide);
		padding: 0 0.05em;
	}
	.mark-sub { color: var(--paper-dim); letter-spacing: .2em; }

	/* Hero search */
	.hero {
		padding: 4.5rem 0 3rem;
		border-bottom: var(--rule-thin);
	}
	.prompt-line {
		display: flex;
		align-items: center;
		gap: 12px;
		color: var(--paper-dim);
	}
	.prompt-dot {
		width: 6px; height: 6px; border-radius: 50%;
		background: var(--oxide);
		box-shadow: 0 0 12px var(--oxide);
		animation: pulse 2s ease-in-out infinite;
	}
	@keyframes pulse { 0%, 100% { opacity: .6; } 50% { opacity: 1; } }

	.prompt-field {
		display: flex;
		align-items: flex-end;
		gap: 1.5rem;
		margin-top: 1.25rem;
		padding-bottom: 1.25rem;
		border-bottom: 1px solid var(--paper);
	}
	.prompt-arrow {
		font-family: var(--mono);
		font-size: 2rem;
		color: var(--oxide);
		line-height: 1;
	}
	.prompt-input {
		flex: 1;
		font-family: var(--serif);
		font-style: italic;
		font-weight: 300;
		font-size: clamp(1.75rem, 4.5vw, 3.25rem);
		line-height: 1.05;
		color: var(--paper);
		padding: 0;
	}
	.prompt-input::placeholder {
		color: var(--paper-mute);
		font-style: italic;
	}
	.prompt-go {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 10px 18px;
		border: 1px solid var(--oxide);
		color: var(--ink);
		background: var(--oxide);
		transition: all .25s ease;
		white-space: nowrap;
	}
	.prompt-go.ready {
		color: var(--ink);
		background: var(--oxide);
		border-color: var(--oxide);
	}
	.prompt-go:hover { transform: translateX(2px); }
	.go-arrow { font-family: var(--mono); font-weight: 500; }

	.prompt-hint {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		align-items: center;
		margin-top: 1.25rem;
	}
	.suggest {
		border: 1px solid var(--rule);
		padding: 6px 10px;
		font-family: var(--mono);
		font-size: 10px;
		letter-spacing: .16em;
		color: var(--paper-dim);
		text-transform: uppercase;
		transition: all .2s ease;
	}
	.suggest:hover {
		color: var(--oxide);
		border-color: var(--oxide);
	}
	.sep { color: var(--rule); }

	/* Loader */
	.loader {
		padding: 2.5rem 0 3rem;
		text-align: center;
	}
	.loader-bar {
		height: 1px;
		background: var(--rule);
		position: relative;
		overflow: hidden;
		margin-bottom: 14px;
	}
	.loader-bar::before {
		content: "";
		position: absolute;
		top: 0; left: 0; bottom: 0;
		width: 28%;
		background: var(--oxide);
		animation: slide 1.2s cubic-bezier(.55, .1, .45, 1) infinite;
	}
	@keyframes slide {
		0%   { transform: translateX(-100%); }
		100% { transform: translateX(460%); }
	}
	.loader-text { color: var(--paper-dim); }

	/* Sections */
	.section { padding: 3.5rem 0 2rem; }
	.section-head {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
		padding-bottom: 1.5rem;
		border-bottom: var(--rule-thin);
		margin-bottom: 1rem;
	}
	.section-title {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(1.75rem, 3.5vw, 2.6rem);
		line-height: 1.05;
		letter-spacing: -0.01em;
		margin-top: 6px;
	}
	.section-title em {
		color: var(--oxide);
		font-style: italic;
		font-weight: 300;
	}
	.empty {
		padding: 3rem 0;
		text-align: center;
		color: var(--paper-mute);
	}

	/* Index rows (artists/labels) */
	.index {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	.index-row {
		display: grid;
		grid-template-columns: 56px 84px 1fr auto;
		gap: 1.5rem;
		align-items: center;
		padding: 1.1rem 0.5rem;
		border-bottom: var(--rule-thin-soft);
		cursor: pointer;
		position: relative;
		transition: background .2s ease, padding .3s ease;
		opacity: 0;
		animation: rise .6s ease forwards;
		animation-delay: var(--d, 0ms);
	}
	.index-row.static { cursor: default; }
	.index-row:not(.static):hover {
		padding-left: 1.25rem;
		padding-right: 1.25rem;
		background: var(--ink-2);
	}
	.index-row:not(.static):hover .index-cta {
		color: var(--oxide);
	}
	.index-row::before {
		content: "";
		position: absolute;
		left: 0; top: 0; bottom: 0;
		width: 2px;
		background: var(--oxide);
		transform: scaleY(0);
		transform-origin: top;
		transition: transform .3s ease;
	}
	.index-row:not(.static):hover::before { transform: scaleY(1); }
	.index-num { font-size: 12px; }
	.index-thumb {
		width: 72px; height: 72px;
		border-radius: 50%;
		overflow: hidden;
		background: var(--ink-3);
		border: 1px solid var(--rule);
		flex-shrink: 0;
	}
	.index-thumb.square { border-radius: 2px; }
	.index-thumb img {
		width: 100%; height: 100%;
		object-fit: cover;
		filter: grayscale(.25) contrast(1.05);
		transition: filter .4s ease;
	}
	.index-row:hover .index-thumb img { filter: grayscale(0) contrast(1); }
	.index-name {
		font-family: var(--serif);
		font-style: italic;
		font-weight: 400;
		font-size: clamp(1.25rem, 2.4vw, 1.8rem);
		line-height: 1.1;
		letter-spacing: -0.01em;
	}
	.index-meta { margin-top: 4px; font-size: 10px; }
	.index-cta {
		font-size: 11px;
		color: var(--paper-dim);
		transition: color .25s ease;
	}

	@keyframes rise {
		from { opacity: 0; transform: translateY(14px); }
		to   { opacity: 1; transform: translateY(0); }
	}

	/* Artist dossier */
	.breadcrumb {
		font-size: 11px;
		color: var(--paper-dim);
		padding: 6px 0;
		margin-bottom: 1.5rem;
		transition: color .2s ease;
	}
	.breadcrumb:hover { color: var(--oxide); }

	.dossier {
		display: grid;
		grid-template-columns: 1fr 280px;
		gap: 3rem;
		padding: 1rem 0 2rem;
		border-bottom: var(--rule-thin);
	}
	.dossier-kicker { margin-bottom: 1rem; }
	.dossier-name {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(3rem, 8.5vw, 6.5rem);
		line-height: 0.92;
		letter-spacing: -0.035em;
		margin-bottom: 1.5rem;
	}
	.dossier-name em { font-style: italic; font-weight: 400; }
	.dossier-bio {
		font-family: var(--serif);
		font-weight: 300;
		font-size: 17px;
		line-height: 1.55;
		color: var(--paper);
		max-width: var(--measure);
		opacity: .9;
	}
	.dossier-portrait { padding-top: 2.5rem; }
	.dossier-portrait img {
		width: 100%;
		aspect-ratio: 1;
		object-fit: cover;
		filter: grayscale(.35) contrast(1.1);
		border: 1px solid var(--rule);
	}
	.portrait-caption {
		margin-top: 10px;
		font-size: 10px;
		text-align: right;
	}

	.dossier-stats {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 1px;
		background: var(--rule);
		border-bottom: var(--rule-thin);
		margin: 0;
	}
	.stat {
		background: var(--ink);
		padding: 1.5rem 1.25rem 1.25rem;
	}
	.stat-val {
		font-family: var(--serif);
		font-style: italic;
		font-weight: 300;
		font-size: clamp(2.5rem, 5vw, 3.75rem);
		line-height: 1;
		color: var(--paper);
		margin-bottom: 6px;
	}

	/* Tabs */
	.tabs {
		display: flex;
		gap: 0;
		border-bottom: var(--rule-thin);
		margin-top: 3rem;
	}
	.tab {
		padding: 1.25rem 2rem 1.25rem 0;
		margin-right: 2.5rem;
		font-size: 11px;
		color: var(--paper-mute);
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		transition: all .25s ease;
		display: inline-flex;
		gap: 10px;
		align-items: baseline;
	}
	.tab-num {
		font-family: var(--serif);
		font-style: italic;
		font-size: 14px;
		letter-spacing: 0;
		text-transform: none;
	}
	.tab:hover { color: var(--paper); }
	.tab.active {
		color: var(--paper);
		border-bottom-color: var(--oxide);
	}
	.tab.active .tab-num { color: var(--oxide); }

	/* Track rows */
	.tracks-list { padding: 1rem 0 0; }
	.tracks-list.dense { padding-top: 0; }

	.track-row {
		display: grid;
		grid-template-columns: 48px 112px 1fr 200px;
		gap: 1.5rem;
		align-items: center;
		padding: 1.5rem 0.5rem;
		border-bottom: var(--rule-thin-soft);
		position: relative;
		opacity: 0;
		animation: rise .6s ease forwards;
		animation-delay: var(--d, 0ms);
		transition: background .2s ease;
	}
	.track-row.dense {
		grid-template-columns: 40px 64px 1fr 140px;
		gap: 1rem;
		padding: 0.85rem 0.5rem;
	}
	.track-row:hover { background: var(--ink-2); }
	.track-row.playing { background: var(--ink-3); }
	.track-row.playing::before {
		content: "";
		position: absolute;
		left: 0; top: 0; bottom: 0;
		width: 2px;
		background: var(--oxide);
	}

	.track-num { font-size: 11px; }
	.track-art {
		position: relative;
		width: 100%;
		aspect-ratio: 1;
		background: var(--ink-3);
		border: 1px solid var(--rule);
	}
	.track-art img {
		width: 100%; height: 100%;
		object-fit: cover;
		filter: grayscale(.2) contrast(1.05);
		transition: filter .3s ease;
	}
	.track-row:hover .track-art img { filter: grayscale(0) contrast(1); }
	.track-art.small { width: 64px; height: 64px; }

	.play-btn {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0;
		background: rgba(10, 9, 6, 0.55);
		transition: opacity .25s ease;
	}
	.track-row:hover .play-btn,
	.track-row.playing .play-btn { opacity: 1; }
	.play-btn:disabled { cursor: not-allowed; opacity: 0; }
	.play-icon {
		width: 0; height: 0;
		border-left: 14px solid var(--paper);
		border-top: 9px solid transparent;
		border-bottom: 9px solid transparent;
		margin-left: 3px;
		transition: border-left-color .2s ease;
	}
	.play-btn:hover .play-icon { border-left-color: var(--oxide); }
	.play-btn.small .play-icon {
		border-left-width: 10px;
		border-top-width: 6px;
		border-bottom-width: 6px;
	}
	.pause-icon {
		display: inline-block;
		width: 12px; height: 14px;
		border-left: 4px solid var(--oxide);
		border-right: 4px solid var(--oxide);
	}
	.play-btn.small .pause-icon {
		width: 8px; height: 10px;
		border-left-width: 3px; border-right-width: 3px;
	}

	.track-title {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(1.2rem, 2vw, 1.6rem);
		line-height: 1.15;
		letter-spacing: -0.01em;
		margin-bottom: 6px;
	}
	.track-title.small { font-size: 1.15rem; margin-bottom: 4px; }
	.track-title em { font-style: italic; }
	.track-credit { font-size: 10px; letter-spacing: 0.14em; }
	.track-label { font-size: 10px; margin-top: 4px; }
	.track-credit .sep { margin: 0 6px; }

	.track-player {
		display: flex;
		flex-direction: column;
		gap: 10px;
		align-items: stretch;
	}
	.track-time {
		font-size: 10px;
		text-align: right;
	}
	.scrubber {
		height: 2px;
		background: var(--rule);
		cursor: pointer;
		position: relative;
	}
	.scrubber-fill {
		height: 100%;
		background: var(--oxide);
		transition: width .1s linear;
	}
	.scrubber:hover { height: 4px; margin-top: -1px; }

	/* Timeline */
	.timeline {
		padding: 2rem 0 0;
	}
	.timeline-row {
		display: grid;
		grid-template-columns: 150px 60px 1fr;
		gap: 1.5rem;
		align-items: stretch;
		opacity: 0;
		animation: rise .6s ease forwards;
		animation-delay: var(--d, 0ms);
	}
	.timeline-year {
		padding: 1.5rem 0;
		text-align: right;
	}
	.year {
		font-family: var(--serif);
		font-style: italic;
		font-weight: 300;
		font-size: 3rem;
		line-height: 1;
		color: var(--paper);
		margin-bottom: 4px;
	}
	.timeline-rail {
		position: relative;
		display: flex;
		justify-content: center;
	}
	.timeline-rail::before {
		content: "";
		position: absolute;
		top: 0; bottom: 0;
		width: 1px;
		background: var(--rule);
	}
	.timeline-row:first-child .timeline-rail::before { top: 1.5rem; }
	.timeline-row:last-child .timeline-rail::before { bottom: calc(100% - 1.5rem - 10px); }
	.timeline-dot {
		position: absolute;
		top: 1.75rem;
		width: 10px; height: 10px;
		border-radius: 50%;
		background: var(--ink);
		border: 1px solid var(--oxide);
		box-shadow: 0 0 0 3px var(--ink);
	}
	.timeline-row:hover .timeline-dot { background: var(--oxide); }
	.timeline-body {
		display: flex;
		gap: 1.25rem;
		align-items: center;
		padding: 1.5rem 0;
		border-bottom: var(--rule-thin-soft);
	}
	.timeline-logo {
		width: 88px; height: 88px;
		background: var(--ink-3);
		border: 1px solid var(--rule);
		overflow: hidden;
		flex-shrink: 0;
	}
	.timeline-logo img {
		width: 100%; height: 100%;
		object-fit: cover;
		filter: grayscale(.25) contrast(1.05);
	}
	.timeline-name {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(1.5rem, 2.6vw, 2rem);
		line-height: 1.1;
		letter-spacing: -0.015em;
		margin-top: 4px;
	}

	/* Catalog (full tracks grouped by label) */
	.catalog { padding: 2rem 0 0; }
	.cat-group { margin-bottom: 3rem; }
	.cat-group-head {
		display: grid;
		grid-template-columns: 72px 1fr auto;
		gap: 1.25rem;
		align-items: center;
		padding-bottom: 1rem;
		border-bottom: var(--rule-thin);
		margin-bottom: 0.5rem;
	}
	.cat-logo {
		width: 72px; height: 72px;
		background: var(--ink-3);
		border: 1px solid var(--rule);
		overflow: hidden;
	}
	.cat-logo img {
		width: 100%; height: 100%; object-fit: cover;
		filter: grayscale(.25) contrast(1.05);
	}
	.cat-label-name {
		font-family: var(--serif);
		font-weight: 400;
		font-size: clamp(1.4rem, 2.4vw, 1.85rem);
		line-height: 1.1;
		letter-spacing: -0.015em;
		margin-top: 2px;
	}
	.cat-count { font-size: 11px; }

	/* Streaming UI */
	.stat.live .stat-val {
		color: var(--oxide);
		transition: color .4s ease;
	}
	.tab-placeholder {
		padding: 3.5rem 0 2rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
	}
	.placeholder-bar {
		width: 180px;
		height: 1px;
		background: var(--rule);
		position: relative;
		overflow: hidden;
	}
	.placeholder-bar::before {
		content: "";
		position: absolute;
		inset: 0;
		width: 35%;
		background: var(--oxide);
		animation: slide 1.2s cubic-bezier(.55,.1,.45,1) infinite;
	}
	.stream-ticker {
		display: inline-flex;
		align-items: center;
		gap: 12px;
		padding: 10px 14px;
		margin: 0 0 1.25rem;
		border: 1px solid var(--rule);
		font-size: 10px;
		color: var(--paper-dim);
		background: var(--ink-2);
	}
	.stream-dot {
		width: 6px; height: 6px;
		border-radius: 50%;
		background: var(--oxide);
		box-shadow: 0 0 10px var(--oxide);
		animation: pulse 1.1s ease-in-out infinite;
	}
	.stream-error {
		display: flex;
		flex-wrap: wrap;
		gap: 14px;
		align-items: baseline;
		padding: 14px 18px;
		margin-bottom: 1.5rem;
		border: 1px solid var(--oxide);
		background: rgba(255, 61, 0, 0.06);
	}
	.stream-error-label {
		color: var(--oxide);
		font-size: 10px;
		letter-spacing: 0.2em;
	}
	.stream-error-msg {
		color: var(--paper-dim);
		font-size: 11px;
		letter-spacing: 0.1em;
		text-transform: none;
	}

	.manual-setup { margin-top: 2rem; padding-top: 1.5rem; border-top: var(--rule-thin); }
	.manual-steps { margin: 1rem 0; padding-left: 1.25rem; color: var(--paper-dim); font-size: 13px; line-height: 1.6; }
	.snippet-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 6px;
	}
	.copy-btn {
		border: 1px solid var(--rule);
		background: none;
		color: var(--paper-dim);
		padding: 4px 12px;
		font-size: 10px;
		letter-spacing: 0.16em;
		cursor: pointer;
		transition: color .2s ease, border-color .2s ease;
	}
	.copy-btn:hover { color: var(--oxide); border-color: var(--oxide); }
	.manual-snippet {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--paper);
		background: var(--ink-2);
		border: 1px solid var(--rule);
		padding: 12px;
		overflow-x: auto;
		white-space: pre-wrap;
	}
	.clear-token-row {
		display: flex;
		justify-content: flex-end;
		margin-bottom: 1rem;
	}
	.clear-token {
		background: none;
		border: 1px solid var(--rule);
		color: var(--paper-dim);
		padding: 6px 12px;
		font-size: 10px;
		letter-spacing: 0.16em;
		cursor: pointer;
		transition: color .2s ease, border-color .2s ease;
	}
	.clear-token:hover { color: var(--oxide); border-color: var(--oxide); }
	.why-note {
		margin-bottom: 1.5rem;
		padding: 14px 16px;
		border: 1px solid var(--rule);
		background: var(--ink-2);
	}
	.why-title { margin-bottom: 8px; }
	.why-note p {
		margin: 0;
		font-size: 13px;
		line-height: 1.6;
		color: var(--paper-dim);
	}
	.why-note code {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--paper);
	}
	.token-input {
		width: 100%;
		margin-top: 1rem;
		box-sizing: border-box;
		font-family: var(--mono);
		font-size: 12px;
		line-height: 1.5;
		color: var(--paper);
		background: var(--ink-2);
		border: 1px solid var(--rule);
		padding: 12px;
		resize: vertical;
		white-space: pre;
		overflow-wrap: normal;
		overflow-x: auto;
	}
	.token-input:focus { outline: none; border-color: var(--oxide); }
	.token-input::placeholder { color: var(--paper-mute); }
	.refresh-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 1rem;
		color: var(--paper-dim);
		cursor: pointer;
	}
	.refresh-toggle input { accent-color: var(--oxide); cursor: pointer; }
	.refresh-note { margin-top: 0.75rem; text-transform: none; line-height: 1.6; }
	.disconnect { background: none; border: none; cursor: pointer; }
	.disconnect:hover { color: var(--oxide); }

	/* Footer */
	.foot {
		margin-top: 5rem;
		padding: 2rem 0 1rem;
		border-top: var(--rule-thin);
	}
	.foot-row {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
	}
	.foot-row .caps { font-size: 10px; }

	/* Responsive */
	@media (max-width: 900px) {
		.band { grid-template-columns: 1fr 1fr; }
		.band-center { display: none; }
		.dossier { grid-template-columns: 1fr; }
		.dossier-portrait { max-width: 240px; }
		.dossier-stats { grid-template-columns: repeat(2, 1fr); }
		.index-row { grid-template-columns: 40px 64px 1fr; gap: 1rem; }
		.index-cta { display: none; }
		.track-row, .track-row.dense {
			grid-template-columns: 40px 64px 1fr;
			gap: 0.75rem;
		}
		.track-player { grid-column: 2 / -1; padding-top: 6px; }
		.timeline-row { grid-template-columns: 96px 40px 1fr; gap: 1rem; }
		.year { font-size: 2rem; }
		.timeline-body { flex-direction: column; align-items: flex-start; }
		.tabs { flex-wrap: wrap; }
		.tab { padding: 1rem 1rem 1rem 0; margin-right: 1rem; }
	}

	@media (max-width: 640px) {
		.frame { padding: 0 1rem 4rem; }
		.mark-word { font-size: clamp(2.5rem, 11vw, 4.5rem); }
		.prompt-field { flex-wrap: wrap; gap: 0.75rem 1rem; }
		.prompt-input { min-width: 0; font-size: clamp(0.95rem, 4vw, 1.125rem); }
		.prompt-go { flex: 0 0 100%; justify-content: space-between; }
		.dossier-stats { grid-template-columns: 1fr; }
		.dossier-portrait { max-width: 160px; }
		.dossier-name { font-size: clamp(2rem, 10vw, 3.5rem); }
		.index-thumb { width: 56px; height: 56px; }
		.index-row { grid-template-columns: 32px 56px 1fr; gap: 0.75rem; }
		.track-art { width: 64px; height: 64px; }
		.track-row, .track-row.dense { grid-template-columns: 32px 64px 1fr; gap: 0.5rem; }
		.timeline-row { grid-template-columns: 1fr; gap: 0.5rem; }
		.timeline-logo { width: 64px; height: 64px; }
	}

	@media (max-width: 340px) {
		.mark-word { font-size: clamp(2.25rem, 13vw, 3.5rem); }
	}
</style>
