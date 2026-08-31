// State
const state = {
  audioFile: null,
  audioUrl: null,
  audioDuration: 0,
  lyricsData: null,
  syncedLines: [],
  currentLineIndex: -1,
  syncOffset: 0.0, // seconds (+/-)
  isPlaying: false,
  audioContext: null,
  analyser: null,
  animationFrameId: null,
};

// DOM Elements
const audioFileInput = document.getElementById('audio-file-input');
const audioDropZone = document.getElementById('audio-drop-zone');
const loadedAudioInfo = document.getElementById('loaded-audio-info');
const audioFilename = document.getElementById('audio-filename');
const audioFilesize = document.getElementById('audio-file-size');
const changeAudioBtn = document.getElementById('change-audio-btn');

const quickSongSearch = document.getElementById('quick-song-search');
const quickSearchBtn = document.getElementById('quick-search-btn');
const loadSavedBtn = document.getElementById('load-saved-btn');
const loadSessionBtn = document.getElementById('load-session-btn');
const savedFilesDropdown = document.getElementById('saved-files-dropdown');
const savedFilesList = document.getElementById('saved-files-list');
const closeDropdownBtn = document.getElementById('close-dropdown-btn');

const lyricsStatusDot = document.getElementById('lyrics-status-dot');
const lyricsStatusText = document.getElementById('lyrics-status-text');

const audioPlayer = document.getElementById('audio-player');
const mainPlayBtn = document.getElementById('main-play-btn');
const playIcon = document.getElementById('play-icon');
const pauseIcon = document.getElementById('pause-icon');
const seekBar = document.getElementById('seek-bar');
const currentTimeDisplay = document.getElementById('current-time-display');
const totalTimeDisplay = document.getElementById('total-time-display');
const skipBackBtn = document.getElementById('skip-back-btn');
const skipForwardBtn = document.getElementById('skip-forward-btn');
const volumeBar = document.getElementById('volume-bar');
const fullscreenBtn = document.getElementById('fullscreen-btn');
const karaokeStageBox = document.getElementById('karaoke-stage-box');

const offsetMinus = document.getElementById('offset-minus');
const offsetPlus = document.getElementById('offset-plus');
const offsetReset = document.getElementById('offset-reset');
const offsetDisplay = document.getElementById('offset-display');

const nowPlayingTitle = document.getElementById('now-playing-title');
const nowPlayingArtist = document.getElementById('now-playing-artist');
const playerSyncBadge = document.getElementById('player-sync-badge');
const playerLinesCount = document.getElementById('player-lines-count');
const playerVinyl = document.getElementById('player-vinyl');
const liveKaraokeStream = document.getElementById('live-karaoke-stream');
const waveformCanvas = document.getElementById('waveform-canvas');

const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toast-message');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  checkUrlParamsAndSession();
  initWaveformVisualizer();
});

function setupEventListeners() {
  // Audio File Selection & Drag-and-Drop
  audioDropZone.addEventListener('click', () => {
    if (!state.audioFile) audioFileInput.click();
  });

  changeAudioBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    audioFileInput.click();
  });

  audioFileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleAudioFileLoaded(e.target.files[0]);
    }
  });

  // Drag-and-drop support
  ['dragenter', 'dragover'].forEach((eventName) => {
    audioDropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      audioDropZone.classList.add('drag-active');
    });
  });

  ['dragleave', 'drop'].forEach((eventName) => {
    audioDropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      audioDropZone.classList.remove('drag-active');
    });
  });

  audioDropZone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleAudioFileLoaded(e.dataTransfer.files[0]);
    }
  });

  // Quick Lyrics Search
  quickSearchBtn.addEventListener('click', () => {
    const q = quickSongSearch.value.trim();
    if (q) fetchLyricsFromSearch(q);
  });

  quickSongSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = quickSongSearch.value.trim();
      if (q) fetchLyricsFromSearch(q);
    }
  });

  // Load from session or saved files
  loadSessionBtn.addEventListener('click', loadCurrentSessionLyrics);
  loadSavedBtn.addEventListener('click', openSavedFilesModal);
  closeDropdownBtn.addEventListener('click', () => {
    savedFilesDropdown.style.display = 'none';
  });

  // Audio Player Event Listeners
  mainPlayBtn.addEventListener('click', togglePlayPause);

  audioPlayer.addEventListener('play', () => {
    state.isPlaying = true;
    playIcon.style.display = 'none';
    pauseIcon.style.display = 'block';
    playerVinyl.classList.add('spinning');
    startVisualizerLoop();
  });

  audioPlayer.addEventListener('pause', () => {
    state.isPlaying = false;
    playIcon.style.display = 'block';
    pauseIcon.style.display = 'none';
    playerVinyl.classList.remove('spinning');
  });

  audioPlayer.addEventListener('timeupdate', handleTimeUpdate);

  audioPlayer.addEventListener('loadedmetadata', () => {
    state.audioDuration = audioPlayer.duration;
    totalTimeDisplay.textContent = formatTime(audioPlayer.duration);
    seekBar.max = audioPlayer.duration;
  });

  audioPlayer.addEventListener('ended', () => {
    state.isPlaying = false;
    playIcon.style.display = 'block';
    pauseIcon.style.display = 'none';
    playerVinyl.classList.remove('spinning');
  });

  // Seek Bar
  seekBar.addEventListener('input', () => {
    audioPlayer.currentTime = parseFloat(seekBar.value);
    currentTimeDisplay.textContent = formatTime(audioPlayer.currentTime);
    syncKaraokeLine(audioPlayer.currentTime);
  });

  // Skip 5s
  skipBackBtn.addEventListener('click', () => {
    audioPlayer.currentTime = Math.max(0, audioPlayer.currentTime - 5);
  });

  skipForwardBtn.addEventListener('click', () => {
    audioPlayer.currentTime = Math.min(audioPlayer.duration || 0, audioPlayer.currentTime + 5);
  });

  // Volume Bar
  volumeBar.addEventListener('input', () => {
    audioPlayer.volume = parseFloat(volumeBar.value);
  });

  // Offset adjustment
  offsetMinus.addEventListener('click', () => adjustOffset(-0.2));
  offsetPlus.addEventListener('click', () => adjustOffset(0.2));
  offsetReset.addEventListener('click', () => resetOffset());

  // Fullscreen
  fullscreenBtn.addEventListener('click', toggleFullscreen);
}

// 1. Handle Audio File Upload
function handleAudioFileLoaded(file) {
  if (!file.type.startsWith('audio/') && !file.name.match(/\.(mp3|wav|m4a|aac|flac|ogg)$/i)) {
    showToast('Please select a valid audio file (.mp3, .wav, .m4a, etc.)');
    return;
  }

  state.audioFile = file;
  if (state.audioUrl) {
    URL.revokeObjectURL(state.audioUrl);
  }

  state.audioUrl = URL.createObjectURL(file);
  audioPlayer.src = state.audioUrl;
  audioPlayer.load();

  // Display loaded audio file details
  audioDropZone.querySelector('.drop-zone-content').style.display = 'none';
  loadedAudioInfo.style.display = 'flex';
  audioFilename.textContent = file.name;
  audioFilesize.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;

  playerSyncBadge.textContent = 'Audio Loaded';
  playerSyncBadge.className = 'badge badge-accent';

  // Automatically guess track name from filename if lyrics not yet searched
  if (!state.lyricsData) {
    const cleanName = file.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
    quickSongSearch.value = cleanName;
    nowPlayingTitle.textContent = cleanName;
    nowPlayingArtist.textContent = 'Ready to play (lyrics search suggested)';
    showToast(`Loaded "${file.name}"! Click search to find lyrics.`);
  } else {
    showToast(`Audio loaded! Ready for synced playback.`);
  }

  connectWebAudio();
}

// 2. Fetch Synced Lyrics from LRCLIB
async function fetchLyricsFromSearch(query) {
  lyricsStatusDot.className = 'status-indicator-dot yellow';
  lyricsStatusText.textContent = `Searching LRCLIB for "${query}"...`;

  try {
    const res = await fetch(`/api/lyrics/synced?q=${encodeURIComponent(query)}`);
    if (!res.ok) {
      throw new Error(`No lyrics found (${res.status})`);
    }

    const data = await res.json();
    setLoadedLyrics(data);
    showToast(`Synced lyrics loaded for "${data.trackName}"! 🎤`);
  } catch (err) {
    console.error('Lyrics search error:', err);
    lyricsStatusDot.className = 'status-indicator-dot red';
    lyricsStatusText.textContent = `Failed to find lyrics for "${query}".`;
    showToast(`Error: ${err.message}`);
  }
}

// 3. Load Active Backend Session
async function loadCurrentSessionLyrics() {
  lyricsStatusDot.className = 'status-indicator-dot yellow';
  lyricsStatusText.textContent = 'Checking active session...';

  try {
    const res = await fetch('/api/lyrics/current');
    if (!res.ok) {
      throw new Error('No song currently active. Search on Lyrics Finder page first.');
    }

    const data = await res.json();
    setLoadedLyrics(data);
    showToast(`Loaded active session: "${data.trackName}"! ⚡`);
  } catch (err) {
    lyricsStatusDot.className = 'status-indicator-dot red';
    lyricsStatusText.textContent = 'No active session found.';
    showToast(err.message);
  }
}

// 4. Open Saved Files Modal
async function openSavedFilesModal() {
  savedFilesDropdown.style.display = 'block';
  savedFilesList.innerHTML = '<div style="padding: 1rem; color: var(--text-muted);">Loading saved files...</div>';

  try {
    const res = await fetch('/api/lyrics/saved');
    const data = await res.json();

    if (!data.files || data.files.length === 0) {
      savedFilesList.innerHTML = '<div style="padding: 1rem; color: var(--text-muted);">No saved JSON files found in /lyrics folder yet.</div>';
      return;
    }

    savedFilesList.innerHTML = '';
    data.files.forEach((file) => {
      const item = document.createElement('div');
      item.className = 'saved-item-row';
      item.innerHTML = `
        <div class="saved-item-info">
          <strong class="saved-item-name">${escapeHtml(file.trackName || file.filename)}</strong>
          <span class="saved-item-artist">${escapeHtml(file.artistName || 'Unknown Artist')} &bull; ${file.totalLines} lines</span>
        </div>
        <button class="mini-btn load-file-btn">Load</button>
      `;

      item.querySelector('.load-file-btn').addEventListener('click', async () => {
        try {
          const fileRes = await fetch(`/lyrics/${file.filename}`);
          const fileData = await fileRes.json();
          setLoadedLyrics(fileData);
          savedFilesDropdown.style.display = 'none';
          showToast(`Loaded "${file.trackName || file.filename}" from storage!`);
        } catch (e) {
          showToast('Failed to load saved file.');
        }
      });

      savedFilesList.appendChild(item);
    });
  } catch (err) {
    savedFilesList.innerHTML = '<div style="padding: 1rem; color: var(--error);">Error loading saved files.</div>';
  }
}

// 5. Apply Loaded Lyrics to Player State & DOM
function setLoadedLyrics(data) {
  state.lyricsData = data;
  state.syncedLines = data.syncedLines || [];

  lyricsStatusDot.className = 'status-indicator-dot green';
  lyricsStatusText.textContent = `Synced: ${data.trackName} (${state.syncedLines.length} lines)`;

  nowPlayingTitle.textContent = data.trackName || 'Loaded Track';
  nowPlayingArtist.textContent = data.artistName ? `${data.artistName} — ${data.albumName || 'Single'}` : '';

  playerLinesCount.textContent = `${state.syncedLines.length} Lines`;
  playerSyncBadge.textContent = data.hasSyncedLyrics ? '⏱️ Real-Time Synced' : '📄 Plain Only';
  playerSyncBadge.className = data.hasSyncedLyrics ? 'badge badge-accent' : 'badge badge-subtle';

  renderLiveKaraokeStream();
}

// 6. Render Karaoke Stage Stream
function renderLiveKaraokeStream() {
  liveKaraokeStream.innerHTML = '';

  if (!state.syncedLines || state.syncedLines.length === 0) {
    liveKaraokeStream.innerHTML = `
      <div class="empty-karaoke-prompt">
        <div class="prompt-icon">📄</div>
        <h3>No Synchronized Timestamps</h3>
        <p>${escapeHtml(state.lyricsData?.plainLyrics || 'Only plain lyrics are available for this song.')}</p>
      </div>
    `;
    return;
  }

  state.syncedLines.forEach((line, index) => {
    const lineEl = document.createElement('div');
    lineEl.className = 'live-lyric-row';
    lineEl.dataset.index = index;
    lineEl.dataset.time = line.timeSeconds;

    lineEl.innerHTML = `
      <span class="live-lyric-time">${escapeHtml(line.timestamp || formatTime(line.timeSeconds))}</span>
      <span class="live-lyric-text">${escapeHtml(line.text)}</span>
    `;

    // Click to seek
    lineEl.addEventListener('click', () => {
      const targetTime = Math.max(0, line.timeSeconds - state.syncOffset);
      audioPlayer.currentTime = targetTime;
      if (!state.isPlaying) audioPlayer.play();
    });

    liveKaraokeStream.appendChild(lineEl);
  });
}

// 7. Time Update & Synchronized Auto-Scroller
function handleTimeUpdate() {
  const currentSec = audioPlayer.currentTime;
  currentTimeDisplay.textContent = formatTime(currentSec);
  seekBar.value = currentSec;

  syncKaraokeLine(currentSec);
}

function syncKaraokeLine(currentSec) {
  if (!state.syncedLines || state.syncedLines.length === 0) return;

  const adjustedTime = currentSec + state.syncOffset;

  // Find active line: closest line with time <= adjustedTime
  let activeIndex = -1;
  for (let i = 0; i < state.syncedLines.length; i++) {
    if (state.syncedLines[i].timeSeconds <= adjustedTime) {
      activeIndex = i;
    } else {
      break;
    }
  }

  if (activeIndex !== state.currentLineIndex) {
    state.currentLineIndex = activeIndex;

    const allRows = liveKaraokeStream.querySelectorAll('.live-lyric-row');
    allRows.forEach((row, idx) => {
      const isActive = idx === activeIndex;
      const isPast = idx < activeIndex;

      row.classList.toggle('active', isActive);
      row.classList.toggle('past', isPast);
    });

    if (activeIndex >= 0 && allRows[activeIndex]) {
      allRows[activeIndex].scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }
}

// 8. Offset Adjustments
function adjustOffset(delta) {
  state.syncOffset = parseFloat((state.syncOffset + delta).toFixed(2));
  offsetDisplay.textContent = `${state.syncOffset > 0 ? '+' : ''}${state.syncOffset.toFixed(1)}s`;
  syncKaraokeLine(audioPlayer.currentTime);
  showToast(`Offset: ${offsetDisplay.textContent}`);
}

function resetOffset() {
  state.syncOffset = 0.0;
  offsetDisplay.textContent = '0.0s';
  syncKaraokeLine(audioPlayer.currentTime);
  showToast('Offset reset to 0.0s');
}

// 9. Playback Controls
function togglePlayPause() {
  if (!state.audioUrl) {
    showToast('Please upload an audio file first!');
    return;
  }

  if (audioPlayer.paused) {
    audioPlayer.play();
  } else {
    audioPlayer.pause();
  }
}

// 10. Web Audio API Waveform Visualizer
function connectWebAudio() {
  try {
    if (!state.audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      state.audioContext = new AudioCtx();
      state.analyser = state.audioContext.createAnalyser();
      state.analyser.fftSize = 64;

      const source = state.audioContext.createMediaElementSource(audioPlayer);
      source.connect(state.analyser);
      state.analyser.connect(state.audioContext.destination);
    }
    if (state.audioContext.state === 'suspended') {
      state.audioContext.resume();
    }
  } catch (e) {
    console.warn('Web Audio visualizer note:', e);
  }
}

function initWaveformVisualizer() {
  const ctx = waveformCanvas.getContext('2d');
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, waveformCanvas.width, waveformCanvas.height);
}

function startVisualizerLoop() {
  if (state.animationFrameId) cancelAnimationFrame(state.animationFrameId);
  const ctx = waveformCanvas.getContext('2d');
  const bufferLength = state.analyser ? state.analyser.frequencyBinCount : 32;
  const dataArray = new Uint8Array(bufferLength);

  function draw() {
    if (!state.isPlaying) {
      return;
    }

    state.animationFrameId = requestAnimationFrame(draw);

    if (state.analyser) {
      state.analyser.getByteFrequencyData(dataArray);
    }

    ctx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);

    const barWidth = (waveformCanvas.width / bufferLength) * 1.5;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      const barHeight = (dataArray[i] / 255) * waveformCanvas.height * 0.9;

      const gradient = ctx.createLinearGradient(0, waveformCanvas.height, 0, 0);
      gradient.addColorStop(0, '#6366f1');
      gradient.addColorStop(0.5, '#8b5cf6');
      gradient.addColorStop(1, '#06b6d4');

      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.roundRect(x, waveformCanvas.height - barHeight, barWidth - 2, barHeight, 3);
      ctx.fill();

      x += barWidth + 1;
    }
  }

  draw();
}

// 11. Fullscreen Toggle
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    karaokeStageBox.requestFullscreen().catch(err => {
      showToast('Fullscreen not supported on this view');
    });
  } else {
    document.exitFullscreen();
  }
}

// 12. URL Parameter checks on load
function checkUrlParamsAndSession() {
  const params = new URLSearchParams(window.location.search);
  const trackQuery = params.get('q') || params.get('track');

  if (trackQuery) {
    quickSongSearch.value = trackQuery;
    fetchLyricsFromSearch(trackQuery);
  } else {
    // Attempt auto-loading active session
    loadCurrentSessionLyrics();
  }
}

// Helpers
function formatTime(seconds) {
  if (isNaN(seconds) || seconds < 0) return '0:00';
  const min = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${min}:${sec}`;
}

function showToast(msg) {
  toastMessage.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
