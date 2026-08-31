// State Management
const state = {
  currentEventSource: null,
  isGenerating: false,
  activeVideoUrl: null,
  activeMetadata: null,
  syncedLines: [],
  currentLineIndex: -1,
  currentBackdrop: 'checkerboard',
  generationOffset: 0.0,
};

// DOM Elements
const generatorForm = document.getElementById('generator-form');
const songQueryInput = document.getElementById('song-query-input');
const generateBtn = document.getElementById('generate-btn');
const btnText = document.getElementById('btn-text');
const presetChips = document.querySelectorAll('.preset-chip');
const offsetChips = document.querySelectorAll('.offset-chip');

// Pipeline elements
const pipelineSection = document.getElementById('pipeline-section');
const pipelineStatusText = document.getElementById('pipeline-status-text');
const pipelinePercentBadge = document.getElementById('pipeline-percent-badge');
const progressBarFill = document.getElementById('progress-bar-fill');

const stepAudio = document.getElementById('step-audio');
const stepAudioDetail = document.getElementById('step-audio-detail');
const stepAudioStatus = document.getElementById('step-audio-status');

const stepLyrics = document.getElementById('step-lyrics');
const stepLyricsDetail = document.getElementById('step-lyrics-detail');
const stepLyricsStatus = document.getElementById('step-lyrics-status');

const stepAss = document.getElementById('step-ass');
const stepAssDetail = document.getElementById('step-ass-detail');
const stepAssStatus = document.getElementById('step-ass-status');

const stepFfmpeg = document.getElementById('step-ffmpeg');
const stepFfmpegDetail = document.getElementById('step-ffmpeg-detail');
const stepFfmpegStatus = document.getElementById('step-ffmpeg-status');

const consoleStream = document.getElementById('console-stream');
const consoleLineCount = document.getElementById('console-line-count');

// Studio Stage
const studioStage = document.getElementById('studio-stage');
const stageSongTitle = document.getElementById('stage-song-title');
const stageSongMeta = document.getElementById('stage-song-meta');
const videoBackdrop = document.getElementById('video-backdrop');
const outputVideoPlayer = document.getElementById('output-video-player');
const videoSource = document.getElementById('video-source');
const backdropBtns = document.querySelectorAll('.backdrop-btn');

const dlVideoBtn = document.getElementById('dl-video-btn');
const dlAssBtn = document.getElementById('dl-ass-btn');
const dlLrcBtn = document.getElementById('dl-lrc-btn');

const teleprompterStream = document.getElementById('teleprompter-stream');
const teleprompterCount = document.getElementById('teleprompter-count');

// Gallery
const videosGalleryGrid = document.getElementById('videos-gallery-grid');
const refreshGalleryBtn = document.getElementById('refresh-gallery-btn');

const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toast-message');

let logCount = 0;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadVideosGallery();
});

function setupEventListeners() {
  // Form submission
  generatorForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = songQueryInput.value.trim();
    if (query) {
      startGenerationPipeline(query);
    }
  });

  // Preset chips
  presetChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      songQueryInput.value = chip.dataset.query;
      startGenerationPipeline(chip.dataset.query);
    });
  });

  // Offset chips
  offsetChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      offsetChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.generationOffset = parseFloat(chip.dataset.offset) || 0.0;
      showToast(`Timing offset set to ${chip.dataset.offset}s`);
    });
  });

  // Backdrop Switcher
  backdropBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      setBackdrop(btn.dataset.bg);
    });
  });

  // Refresh Gallery
  refreshGalleryBtn.addEventListener('click', loadVideosGallery);

  // Video Time Update for Synchronized Teleprompter
  outputVideoPlayer.addEventListener('timeupdate', () => {
    syncTeleprompter(outputVideoPlayer.currentTime);
  });
}

// 1. Start Server-Sent Events (SSE) Video Generation
function startGenerationPipeline(query) {
  if (state.isGenerating && state.currentEventSource) {
    state.currentEventSource.close();
  }

  state.isGenerating = true;
  generateBtn.disabled = true;
  btnText.textContent = 'Generating 1080p Overlay...';
  generateBtn.classList.add('loading');

  // Reset & show pipeline UI
  resetPipelineUI(query);
  pipelineSection.style.display = 'block';
  pipelineSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Connect to SSE Endpoint with timing offset parameter
  const sseUrl = `/api/generate-video-stream?q=${encodeURIComponent(query)}&offset=${state.generationOffset}`;
  const eventSource = new EventSource(sseUrl);
  state.currentEventSource = eventSource;

  eventSource.addEventListener('start', (e) => {
    const data = JSON.parse(e.data);
    appendConsoleLog(`[START] ${data.message}`);
  });

  eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    handleProgressUpdate(data);
  });

  eventSource.addEventListener('log', (e) => {
    const data = JSON.parse(e.data);
    appendConsoleLog(data.message);
  });

  eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    handleGenerationComplete(data);
    eventSource.close();
    state.isGenerating = false;
    generateBtn.disabled = false;
    btnText.textContent = 'Generate Video Overlay';
    generateBtn.classList.remove('loading');
  });

  eventSource.addEventListener('error', (e) => {
    console.error('SSE Error:', e);
    appendConsoleLog('[ERROR] Video generation pipeline failed or connection closed.');
    pipelineStatusText.textContent = 'Generation Failed (Check console output)';
    eventSource.close();
    state.isGenerating = false;
    generateBtn.disabled = false;
    btnText.textContent = 'Generate Video Overlay';
    generateBtn.classList.remove('loading');
    showToast('Generation failed. Please try a different track title.');
  });
}

// 2. Handle Progress Updates from Python Generator
function handleProgressUpdate(data) {
  const { step, percent, message, details } = data;

  // Update progress bar
  progressBarFill.style.width = `${percent}%`;
  pipelinePercentBadge.textContent = `${percent}%`;
  pipelineStatusText.textContent = message;

  appendConsoleLog(`[${percent}%] ${message}`);

  // Step-specific updates
  if (step === 'ytdlp_start' || step === 'ytdlp_downloading') {
    markStepActive(stepAudio, stepAudioStatus, stepAudioDetail, 'Downloading MP3 audio...');
    markStepActive(stepLyrics, stepLyricsStatus, stepLyricsDetail, 'Fetching YouTube subtitles & captions...');
  } else if (step === 'ytdlp_done') {
    markStepDone(stepAudio, stepAudioStatus, stepAudioDetail, `Extracted audio (${details.duration || 0}s)`);
    markStepDone(stepLyrics, stepLyricsStatus, stepLyricsDetail, `Extracted ${details.subtitles_count || 1} caption stream(s)`);
  } else if (step === 'ass_start') {
    markStepActive(stepAss, stepAssStatus, stepAssDetail, 'Formatting 1080p canvas...');
  } else if (step === 'ass_done') {
    markStepDone(stepAss, stepAssStatus, stepAssDetail, 'Generated styled 1080p ASS');
  } else if (step === 'ffmpeg_start' || step === 'ffmpeg_rendering') {
    markStepActive(stepFfmpeg, stepFfmpegStatus, stepFfmpegDetail, 'Rendering VP9 yuva420p video...');
  } else if (step === 'ffmpeg_done' || step === 'completed') {
    markStepDone(stepFfmpeg, stepFfmpegStatus, stepFfmpegDetail, '1080p Transparent Overlay Ready!');
  }
}

// 3. Handle Generation Complete
function handleGenerationComplete(data) {
  progressBarFill.style.width = '100%';
  pipelinePercentBadge.textContent = '100%';
  pipelineStatusText.textContent = '🎉 Video Overlay Successfully Generated!';

  state.activeVideoUrl = data.videoUrl;
  state.activeMetadata = data.metadata;
  state.syncedLines = data.metadata?.syncedLines || [];

  showToast('1080p Transparent Lyric Video Overlay Generated! 🚀');

  // Populate Studio Stage
  stageSongTitle.textContent = data.metadata?.track_name || data.query;
  stageSongMeta.textContent = `${data.metadata?.artist_name || 'Transparent Overlay'} &bull; ${data.metadata?.duration || 0}s duration &bull; 1080p 30fps`;

  // Set Video Player source
  outputVideoPlayer.pause();
  videoSource.src = data.videoUrl;
  outputVideoPlayer.load();
  outputVideoPlayer.play().catch(() => {});

  // Setup Download Links
  dlVideoBtn.href = data.videoUrl;
  dlVideoBtn.download = data.videoFileName || 'lyric_video_overlay.webm';

  if (data.metadata?.syncedLines) {
    setupAssetDownloadBlobs(data.metadata);
  }

  // Populate Teleprompter
  renderTeleprompter(state.syncedLines);

  studioStage.style.display = 'block';
  studioStage.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Reload Gallery
  setTimeout(loadVideosGallery, 1000);
}

// 4. Setup Asset Blobs for .ass and .lrc download buttons
function setupAssetDownloadBlobs(meta) {
  if (meta.rawLrc) {
    const lrcBlob = new Blob([meta.rawLrc], { type: 'application/x-subrip' });
    dlLrcBtn.href = URL.createObjectURL(lrcBlob);
    dlLrcBtn.download = `${(meta.track_name || 'lyrics').replace(/\s+/g, '_')}.lrc`;
    dlLrcBtn.style.display = 'inline-flex';
  } else {
    dlLrcBtn.style.display = 'none';
  }

  // ASS download
  if (meta.syncedLines) {
    const assContent = generateAssBlobContent(meta);
    const assBlob = new Blob([assContent], { type: 'text/plain' });
    dlAssBtn.href = URL.createObjectURL(assBlob);
    dlAssBtn.download = `${(meta.track_name || 'subtitles').replace(/\s+/g, '_')}.ass`;
    dlAssBtn.style.display = 'inline-flex';
  }
}

function generateAssBlobContent(meta) {
  const header = `[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,60,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n`;
  const lines = (meta.syncedLines || []).map(l => `Dialogue: 0,0:${l.timestamp || '00:00'},0:${l.timestamp || '00:04'},Default,,0,0,0,,${l.text}`).join('\n');
  return header + lines;
}

// 5. Synchronized Teleprompter
function renderTeleprompter(lines) {
  teleprompterStream.innerHTML = '';
  teleprompterCount.textContent = `${lines.length} lines`;

  if (!lines || lines.length === 0) {
    teleprompterStream.innerHTML = '<div style="padding:1rem; color:var(--text-muted);">No synchronized lines available.</div>';
    return;
  }

  lines.forEach((line, idx) => {
    const row = document.createElement('div');
    row.className = 'teleprompter-row';
    row.dataset.index = idx;
    row.dataset.time = line.timeSeconds;

    row.innerHTML = `
      <span class="teleprompter-time">${escapeHtml(line.timestamp || '')}</span>
      <span class="teleprompter-text">${escapeHtml(line.text)}</span>
    `;

    // Click to seek video
    row.addEventListener('click', () => {
      outputVideoPlayer.currentTime = line.timeSeconds;
      if (outputVideoPlayer.paused) outputVideoPlayer.play();
    });

    teleprompterStream.appendChild(row);
  });
}

function syncTeleprompter(currentTime) {
  if (!state.syncedLines || state.syncedLines.length === 0) return;

  let activeIndex = -1;
  for (let i = 0; i < state.syncedLines.length; i++) {
    if (state.syncedLines[i].timeSeconds <= currentTime) {
      activeIndex = i;
    } else {
      break;
    }
  }

  if (activeIndex !== state.currentLineIndex) {
    state.currentLineIndex = activeIndex;
    const allRows = teleprompterStream.querySelectorAll('.teleprompter-row');
    allRows.forEach((row, idx) => {
      const isActive = idx === activeIndex;
      const isPast = idx < activeIndex;
      row.classList.toggle('active', isActive);
      row.classList.toggle('past', isPast);
    });

    if (activeIndex >= 0 && allRows[activeIndex]) {
      allRows[activeIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}

// 6. Backdrop Switcher (Demonstrating Alpha Channel Transparency)
function setBackdrop(bgType) {
  state.currentBackdrop = bgType;
  backdropBtns.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.bg === bgType);
  });

  videoBackdrop.className = `video-backdrop backdrop-${bgType}`;
}

// 7. Load & Render Previously Generated Videos Gallery
async function loadVideosGallery() {
  try {
    const res = await fetch('/api/videos');
    const data = await res.json();

    if (!data.videos || data.videos.length === 0) {
      videosGalleryGrid.innerHTML = `
        <div class="gallery-empty">
          <p>No generated video files found yet. Type a song name above to generate your first transparent overlay!</p>
        </div>
      `;
      return;
    }

    videosGalleryGrid.innerHTML = '';
    data.videos.forEach((vid) => {
      const card = document.createElement('div');
      card.className = 'gallery-card';

      const cleanTitle = vid.filename
        .replace(/\.webm$/, '')
        .replace(/_[0-9]+$/, '')
        .replace(/[_-]/g, ' ');

      card.innerHTML = `
        <div class="gallery-video-thumb backdrop-checkerboard">
          <video src="${vid.url}" preload="metadata" muted playsinline></video>
          <div class="play-overlay-icon">▶</div>
        </div>
        <div class="gallery-card-body">
          <strong class="gallery-card-title" title="${escapeHtml(cleanTitle)}">${escapeHtml(cleanTitle)}</strong>
          <span class="gallery-card-meta">${vid.sizeMb} MB &bull; 1080p VP9 Transparent</span>
          <div class="gallery-card-actions">
            <button class="mini-btn play-gallery-btn">Preview</button>
            <a href="${vid.url}" download="${vid.filename}" class="mini-btn" target="_blank">Download</a>
          </div>
        </div>
      `;

      card.querySelector('.play-gallery-btn').addEventListener('click', () => {
        outputVideoPlayer.pause();
        videoSource.src = vid.url;
        outputVideoPlayer.load();
        outputVideoPlayer.play().catch(() => {});
        stageSongTitle.textContent = cleanTitle;
        stageSongMeta.textContent = `${vid.sizeMb} MB &bull; 1080p 30fps Transparent Overlay`;
        studioStage.style.display = 'block';
        studioStage.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });

      videosGalleryGrid.appendChild(card);
    });
  } catch (e) {
    console.warn('Could not load videos gallery:', e);
  }
}

// UI Helpers
function resetPipelineUI(query) {
  progressBarFill.style.width = '5%';
  pipelinePercentBadge.textContent = '0%';
  pipelineStatusText.textContent = `Starting pipeline for "${query}"...`;
  consoleStream.innerHTML = '';
  logCount = 0;
  consoleLineCount.textContent = '0 lines';

  resetStep(stepAudio, stepAudioStatus, stepAudioDetail, 'Waiting to start...');
  resetStep(stepLyrics, stepLyricsStatus, stepLyricsDetail, 'Waiting to start...');
  resetStep(stepAss, stepAssStatus, stepAssDetail, 'Waiting...');
  resetStep(stepFfmpeg, stepFfmpegStatus, stepFfmpegDetail, 'Waiting...');
}

function resetStep(card, status, detail, text) {
  card.className = 'step-card';
  status.textContent = '⏳';
  detail.textContent = text;
}

function markStepActive(card, status, detail, text) {
  card.className = 'step-card active';
  status.innerHTML = '<span class="spinner" style="width:14px; height:14px; margin:0; border-width:2px; display:inline-block;"></span>';
  detail.textContent = text;
}

function markStepDone(card, status, detail, text) {
  card.className = 'step-card done';
  status.textContent = '✅';
  detail.textContent = text;
}

function appendConsoleLog(msg) {
  logCount++;
  consoleLineCount.textContent = `${logCount} lines`;
  const line = document.createElement('div');
  line.className = 'console-line';
  line.textContent = `> ${msg}`;
  consoleStream.appendChild(line);
  consoleStream.scrollTop = consoleStream.scrollHeight;
}

function showToast(msg) {
  toastMessage.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
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
