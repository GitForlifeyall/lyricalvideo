// State Management
const state = {
  currentQuery: '',
  searchResults: [],
  selectedTrack: null,
  parsedLrcLines: [],
  currentTab: 'karaoke',
  karaokeTimer: null,
  karaokeIndex: 0,
  isPlayingKaraoke: false,
};

// DOM Elements
const searchForm = document.getElementById('search-form');
const songInput = document.getElementById('song-input');
const clearBtn = document.getElementById('clear-btn');
const quickTags = document.querySelectorAll('.tag-btn');

const mainLayout = document.getElementById('main-layout');
const resultsSidebar = document.getElementById('results-sidebar');
const resultsList = document.getElementById('results-list');
const resultsCount = document.getElementById('results-count');

const emptyState = document.getElementById('empty-state');
const loadingState = document.getElementById('loading-state');
const errorState = document.getElementById('error-state');
const errorMessage = document.getElementById('error-message');
const contentView = document.getElementById('content-view');

const songTitle = document.getElementById('song-title');
const songArtist = document.getElementById('song-artist');
const songAlbum = document.getElementById('song-album');
const syncedBadge = document.getElementById('synced-badge');
const durationBadge = document.getElementById('duration-badge');
const instrumentalBadge = document.getElementById('instrumental-badge');
const vinylDisk = document.getElementById('vinyl-disk');

const tabKaraoke = document.getElementById('tab-karaoke');
const tabPlain = document.getElementById('tab-plain');
const tabLrc = document.getElementById('tab-lrc');
const tabJson = document.getElementById('tab-json');

const paneKaraoke = document.getElementById('pane-karaoke');
const panePlain = document.getElementById('pane-plain');
const paneLrc = document.getElementById('pane-lrc');
const paneJson = document.getElementById('pane-json');

const karaokeLinesContainer = document.getElementById('karaoke-lines');
const plainLyricsText = document.getElementById('plain-lyrics-text');
const rawLrcText = document.getElementById('raw-lrc-text');
const jsonTimestampsText = document.getElementById('json-timestamps-text');

const karaokeControls = document.getElementById('karaoke-controls');
const playBtn = document.getElementById('karaoke-play-btn');
const playBtnText = document.getElementById('play-btn-text');
const resetBtn = document.getElementById('karaoke-reset-btn');

const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toast-message');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
});

function setupEventListeners() {
  // Search Form Submit
  searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = songInput.value.trim();
    if (query) {
      performSearch(query);
    }
  });

  // Input Clear Button
  songInput.addEventListener('input', () => {
    clearBtn.style.display = songInput.value ? 'block' : 'none';
  });

  clearBtn.addEventListener('click', () => {
    songInput.value = '';
    clearBtn.style.display = 'none';
    songInput.focus();
  });

  // Quick Tags
  quickTags.forEach((btn) => {
    btn.addEventListener('click', () => {
      const query = btn.dataset.query;
      songInput.value = query;
      clearBtn.style.display = 'block';
      performSearch(query);
    });
  });

  // Tab switching
  [tabKaraoke, tabPlain, tabLrc, tabJson].forEach((btn) => {
    if (btn) {
      btn.addEventListener('click', () => {
        switchTab(btn.dataset.tab);
      });
    }
  });

  // Copy Button
  copyBtn.addEventListener('click', handleCopy);

  // Download Button
  downloadBtn.addEventListener('click', handleDownload);

  // Karaoke Simulation
  playBtn.addEventListener('click', toggleKaraokeSimulation);
  resetBtn.addEventListener('click', resetKaraokeSimulation);
}

// Perform Search against backend API proxy
async function performSearch(query) {
  state.currentQuery = query;
  stopKaraokeSimulation();
  showLoading();

  try {
    const res = await fetch(`/api/lyrics/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch results (${res.status})`);
    }

    const data = await res.json();

    if (!Array.isArray(data) || data.length === 0) {
      showError('No tracks found for "' + query + '". Try refining song/artist name.');
      return;
    }

    state.searchResults = data;
    renderSearchResults(data);

    // Automatically select the first track with synced or plain lyrics
    const firstValid = data.find((item) => item.hasSyncedLyrics || item.plainLyrics) || data[0];
    selectTrack(firstValid);
  } catch (err) {
    console.error('Search error:', err);
    showError(err.message || 'Error communicating with LRCLIB API.');
  }
}

// Render Results List in Sidebar
function renderSearchResults(results) {
  resultsList.innerHTML = '';
  resultsSidebar.style.display = 'flex';
  mainLayout.classList.remove('single-column');
  resultsCount.textContent = `${results.length} ${results.length === 1 ? 'match' : 'matches'}`;

  results.forEach((track) => {
    const card = document.createElement('div');
    card.className = 'track-card';
    card.dataset.id = track.id;

    const hasSynced = !!(track.hasSyncedLyrics || track.syncedLyrics);
    const hasPlain = !!track.plainLyrics;

    card.innerHTML = `
      <div class="track-card-title" title="${escapeHtml(track.trackName || track.name)}">
        ${escapeHtml(track.trackName || track.name)}
      </div>
      <div class="track-card-artist" title="${escapeHtml(track.artistName || 'Unknown Artist')}">
        ${escapeHtml(track.artistName || 'Unknown Artist')}
      </div>
      <div class="track-card-meta">
        <span class="track-card-album">${escapeHtml(track.albumName || '')}</span>
        <span class="badge ${hasSynced ? 'badge-accent' : 'badge-subtle'}">
          ${hasSynced ? '⏱️ Synced' : hasPlain ? '📄 Plain' : '🚫 No Lyrics'}
        </span>
      </div>
    `;

    card.addEventListener('click', () => {
      selectTrack(track);
    });

    resultsList.appendChild(card);
  });
}

// Select and Display Track Details
async function selectTrack(track) {
  state.selectedTrack = track;
  stopKaraokeSimulation();

  // Highlight active card
  document.querySelectorAll('.track-card').forEach((card) => {
    card.classList.toggle('active', card.dataset.id === String(track.id));
  });

  // Metadata Display
  songTitle.textContent = track.trackName || track.name || 'Unknown Track';
  songArtist.textContent = track.artistName || 'Unknown Artist';
  songAlbum.textContent = track.albumName ? `Album: ${track.albumName}` : '';

  // Badges
  const hasSynced = !!(track.hasSyncedLyrics || track.syncedLyrics);
  syncedBadge.style.display = hasSynced ? 'inline-flex' : 'none';
  instrumentalBadge.style.display = track.instrumental ? 'inline-flex' : 'none';

  if (track.duration) {
    const min = Math.floor(track.duration / 60);
    const sec = Math.floor(track.duration % 60).toString().padStart(2, '0');
    durationBadge.textContent = `⏱️ ${min}:${sec}`;
    durationBadge.style.display = 'inline-flex';
  } else {
    durationBadge.style.display = 'none';
  }

  // Use pre-parsed lines if available from backend, or parse locally
  state.parsedLrcLines = track.syncedLines || parseLRC(track.syncedLyrics || '');

  // Populate Panes
  renderKaraokeLines();
  plainLyricsText.textContent = track.plainLyrics || (track.instrumental ? '[Instrumental - No Lyrics]' : 'No plain lyrics available.');
  rawLrcText.textContent = track.syncedLyrics || 'No synced LRC timestamps available for this track.';

  // Structured JSON Timestamps representation
  const jsonPayload = {
    id: track.id,
    trackName: track.trackName || track.name,
    artistName: track.artistName,
    albumName: track.albumName,
    durationSeconds: track.duration,
    hasSyncedLyrics: hasSynced,
    totalLines: state.parsedLrcLines.length,
    syncedLines: state.parsedLrcLines,
    rawLrc: track.syncedLyrics || null
  };
  jsonTimestampsText.textContent = JSON.stringify(jsonPayload, null, 2);

  // Sync with Backend active session
  try {
    fetch('/api/lyrics/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track })
    }).catch(err => console.warn('Backend sync notice:', err));
  } catch (e) {
    // Non-blocking
  }

  // Show/Hide Karaoke Simulation controls based on LRC availability
  if (state.parsedLrcLines.length > 0) {
    karaokeControls.style.display = 'flex';
    tabKaraoke.style.display = 'inline-block';
    tabLrc.style.display = 'inline-block';
    tabJson.style.display = 'inline-block';
    switchTab('karaoke');
  } else {
    karaokeControls.style.display = 'none';
    tabKaraoke.style.display = 'none';
    switchTab('plain');
  }

  showContent();
}

// Parse LRC Timestamp format [mm:ss.xx] into structured objects
function parseLRC(lrcText) {
  if (!lrcText) return [];
  const lines = lrcText.split('\n');
  const result = [];
  const timeRegex = /\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\](.*)/;

  let idx = 0;
  lines.forEach((line) => {
    const match = line.match(timeRegex);
    if (match) {
      const minutes = parseInt(match[1], 10);
      const seconds = parseInt(match[2], 10);
      const millis = match[3] ? (match[3].length === 2 ? parseInt(match[3], 10) * 10 : parseInt(match[3], 10)) : 0;
      const totalSeconds = parseFloat((minutes * 60 + seconds + millis / 1000).toFixed(3));
      const totalMs = minutes * 60000 + seconds * 1000 + millis;
      const text = match[4].trim();

      if (text.length > 0) {
        result.push({
          index: idx++,
          timestamp: `${match[1]}:${match[2]}${match[3] ? '.' + match[3] : ''}`,
          timeSeconds: totalSeconds,
          timeMs: totalMs,
          text: text,
        });
      }
    }
  });

  return result;
}

// Render Interactive Karaoke Lines
function renderKaraokeLines() {
  karaokeLinesContainer.innerHTML = '';

  if (state.parsedLrcLines.length === 0) {
    karaokeLinesContainer.innerHTML = `
      <div class="empty-state" style="padding: 2rem 0;">
        <p>Synced LRC timestamps are not available for this track. Please check the Plain Text tab.</p>
      </div>
    `;
    return;
  }

  state.parsedLrcLines.forEach((line, idx) => {
    const row = document.createElement('div');
    row.className = 'lyric-line';
    row.dataset.index = idx;
    row.innerHTML = `
      <span class="lyric-time">${escapeHtml(line.timestamp || line.timeFormatted)}</span>
      <span class="lyric-text">${escapeHtml(line.text)}</span>
    `;

    row.addEventListener('click', () => {
      highlightKaraokeLine(idx);
    });

    karaokeLinesContainer.appendChild(row);
  });
}

// Highlight a specific line and scroll smoothly into view
function highlightKaraokeLine(index) {
  state.karaokeIndex = index;
  const allLines = karaokeLinesContainer.querySelectorAll('.lyric-line');

  allLines.forEach((el, idx) => {
    el.classList.toggle('active', idx === index);
  });

  const activeLine = allLines[index];
  if (activeLine) {
    activeLine.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// Simulate Karaoke Auto-Scroller
function toggleKaraokeSimulation() {
  if (state.isPlayingKaraoke) {
    stopKaraokeSimulation();
  } else {
    startKaraokeSimulation();
  }
}

function startKaraokeSimulation() {
  if (state.parsedLrcLines.length === 0) return;

  state.isPlayingKaraoke = true;
  vinylDisk.classList.add('spinning');
  playBtnText.textContent = 'Pause';
  playBtn.classList.add('action-btn-primary');

  highlightKaraokeLine(state.karaokeIndex);

  state.karaokeTimer = setInterval(() => {
    state.karaokeIndex++;
    if (state.karaokeIndex >= state.parsedLrcLines.length) {
      stopKaraokeSimulation();
      state.karaokeIndex = 0;
      return;
    }
    highlightKaraokeLine(state.karaokeIndex);
  }, 2500);
}

function stopKaraokeSimulation() {
  state.isPlayingKaraoke = false;
  vinylDisk.classList.remove('spinning');
  playBtnText.textContent = 'Simulate Play';
  playBtn.classList.remove('action-btn-primary');

  if (state.karaokeTimer) {
    clearInterval(state.karaokeTimer);
    state.karaokeTimer = null;
  }
}

function resetKaraokeSimulation() {
  stopKaraokeSimulation();
  state.karaokeIndex = 0;
  highlightKaraokeLine(0);
}

// Switch Active View Tab
function switchTab(tabKey) {
  state.currentTab = tabKey;

  [tabKaraoke, tabPlain, tabLrc, tabJson].forEach((btn) => {
    if (btn) btn.classList.toggle('active', btn.dataset.tab === tabKey);
  });

  if (paneKaraoke) paneKaraoke.classList.toggle('active', tabKey === 'karaoke');
  if (panePlain) panePlain.classList.toggle('active', tabKey === 'plain');
  if (paneLrc) paneLrc.classList.toggle('active', tabKey === 'lrc');
  if (paneJson) paneJson.classList.toggle('active', tabKey === 'json');
}

// Copy to Clipboard
function handleCopy() {
  if (!state.selectedTrack) return;

  let textToCopy = '';
  if (state.currentTab === 'json') {
    textToCopy = jsonTimestampsText.textContent;
  } else if (state.currentTab === 'lrc' && state.selectedTrack.syncedLyrics) {
    textToCopy = state.selectedTrack.syncedLyrics;
  } else {
    textToCopy = state.selectedTrack.plainLyrics || state.selectedTrack.syncedLyrics || '';
  }

  if (!textToCopy) {
    showToast('No lyrics text to copy!');
    return;
  }

  navigator.clipboard.writeText(textToCopy)
    .then(() => showToast('Copied to clipboard! 🎉'))
    .catch(() => showToast('Failed to copy.'));
}

// Download File (.lrc, .json, or .txt)
function handleDownload() {
  if (!state.selectedTrack) return;

  const track = state.selectedTrack;
  const isJson = state.currentTab === 'json';
  const isLrc = state.currentTab === 'lrc' || (track.syncedLyrics && state.currentTab === 'karaoke');

  let content = '';
  let extension = 'txt';
  let mimeType = 'text/plain';

  if (isJson) {
    content = jsonTimestampsText.textContent;
    extension = 'json';
    mimeType = 'application/json';
  } else if (isLrc && track.syncedLyrics) {
    content = track.syncedLyrics;
    extension = 'lrc';
    mimeType = 'application/x-subrip';
  } else {
    content = track.plainLyrics || track.syncedLyrics || '';
    extension = 'txt';
  }

  if (!content) {
    showToast('No content to download!');
    return;
  }

  const safeTitle = (track.trackName || 'lyrics').replace(/[^a-z0-9]/gi, '_').toLowerCase();
  const safeArtist = (track.artistName || 'artist').replace(/[^a-z0-9]/gi, '_').toLowerCase();
  const filename = `${safeArtist}-${safeTitle}.${extension}`;

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  showToast(`Downloaded ${filename} 🚀`);
}

// Toast notification trigger
function showToast(message) {
  toastMessage.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 2600);
}

// UI State Toggles
function showLoading() {
  emptyState.style.display = 'none';
  errorState.style.display = 'none';
  contentView.style.display = 'none';
  loadingState.style.display = 'flex';
}

function showError(msg) {
  loadingState.style.display = 'none';
  contentView.style.display = 'none';
  emptyState.style.display = 'none';
  errorMessage.textContent = msg;
  errorState.style.display = 'flex';
}

function showContent() {
  emptyState.style.display = 'none';
  loadingState.style.display = 'none';
  errorState.style.display = 'none';
  contentView.style.display = 'flex';
}

// Utility: HTML Sanitizer
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
