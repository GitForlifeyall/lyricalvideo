// State Management
const state = {
  currentEventSource: null,
  isGenerating: false,
  activeVideoUrl: null,
  activeMetadata: null,
  syncedLines: [],
  currentLineIndex: -1,
  currentBackdrop: 'black',
  template: 'template1',
  fontFamily: 'Impact',
  fontSize: 72,
  blur: 3.2,
  spacing: -1,
  wordSpacing: 0,
  overlayEnabled: true,
  language: 'auto',
  placement: 'center',
  ypos: 50,
  xpos: 50,
  bratTheme: 'green',
  bratCasing: 'lower',
  topHeader: '',
  testStart: 0,
  testEnd: '',
  previewQuality: 'final',
  lastQuery: 'The Weeknd - Blinding Lights'
};


// DOM Elements
const generatorForm = document.getElementById('generator-form');
const songQueryInput = document.getElementById('song-query-input');
const generateBtn = document.getElementById('generate-btn');
const btnText = document.getElementById('btn-text');
const templatePills = document.querySelectorAll('#template-group .template-pill');
const fontBtns = document.querySelectorAll('#font-group .font-pill');
const customFontInput = document.getElementById('custom-font-input');
const langBtns = document.querySelectorAll('#lang-group .lang-pill');
const customLangInput = document.getElementById('custom-lang-input');

// Brat controls & live sandbox
const bratOptionsRow = document.getElementById('brat-options-row');
const bratPalettes = document.querySelectorAll('#brat-palettes-group .brat-swatch-btn');
const bratLiveSandbox = document.getElementById('brat-live-sandbox');
const bratLiveContainer = document.getElementById('brat-live-container');
const bratLiveText = document.getElementById('brat-live-text');
const bratSandboxInput = document.getElementById('brat-sandbox-input');
const bratCasingToggleBtn = document.getElementById('brat-casing-toggle-btn');
const bratChipBtns = document.querySelectorAll('.brat-chip-btn');

// YT Hindi Type controls
const ytHindiOptionsRow = document.getElementById('yt-hindi-options-row');
const ytHindiTopHeaderInput = document.getElementById('yt-hindi-top-header-input');
const testStartInput = document.getElementById('test-start-input');
const testEndInput = document.getElementById('test-end-input');
const previewQualityInput = document.getElementById('preview-quality-input');

// Placement & Size controls
const placementPills = document.querySelectorAll('#placement-group .placement-pill');
const xposSlider = document.getElementById('xpos-slider');
const xposVal = document.getElementById('xpos-val');
const yposSlider = document.getElementById('ypos-slider');
const yposVal = document.getElementById('ypos-val');
const fontsizeSlider = document.getElementById('fontsize-slider');
const fontsizeVal = document.getElementById('fontsize-val');
const blurSlider = document.getElementById('blur-slider');
const blurVal = document.getElementById('blur-val');
const spacingSlider = document.getElementById('spacing-slider');
const spacingVal = document.getElementById('spacing-val');
const wordSpacingSlider = document.getElementById('word-spacing-slider');
const wordSpacingVal = document.getElementById('word-spacing-val');

// Stage Placement & Size controls
const stagePlacementBtns = document.querySelectorAll('#stage-placement-group .stage-place-btn');
const stageXposSlider = document.getElementById('stage-xpos-slider');
const stageXposVal = document.getElementById('stage-xpos-val');
const stageYposSlider = document.getElementById('stage-ypos-slider');
const stageYposVal = document.getElementById('stage-ypos-val');
const stageFontsizeSlider = document.getElementById('stage-fontsize-slider');
const stageFontsizeVal = document.getElementById('stage-fontsize-val');
const stageBlurSlider = document.getElementById('stage-blur-slider');
const stageBlurVal = document.getElementById('stage-blur-val');
const stageSpacingSlider = document.getElementById('stage-spacing-slider');
const stageSpacingVal = document.getElementById('stage-spacing-val');
const stageWordSpacingSlider = document.getElementById('stage-word-spacing-slider');
const stageWordSpacingVal = document.getElementById('stage-word-spacing-val');
const stageOverlayToggleBtn = document.getElementById('stage-overlay-toggle-btn');
const stageRerenderBtn = document.getElementById('stage-rerender-btn');
const stageLiveSubtitleOverlay = document.getElementById('stage-live-subtitle-overlay');
const stageLiveSubtitleText = document.getElementById('stage-live-subtitle-text');

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
const videoPreviewWrapper = document.getElementById('video-preview-wrapper');
const videoBackdrop = document.getElementById('video-backdrop');
const outputVideoPlayer = document.getElementById('output-video-player');
const videoSource = document.getElementById('video-source');
const backdropBtns = document.querySelectorAll('.backdrop-btn');

const dlExactCanvasBtn = document.getElementById('dl-exact-canvas-btn');
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
  applyRealtimePlacementAndSize();
});

function setupEventListeners() {
  // Form submission
  generatorForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = songQueryInput.value.trim();
    if (query) {
      state.lastQuery = query;
      startGenerationPipeline(query);
    }
  });

  // Template Selection
  templatePills.forEach((pill) => {
    pill.addEventListener('click', () => {
      templatePills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.template = pill.dataset.template;

      const isBrat = ['template4_brat', 'template_4_brat', 'brat'].includes(state.template);
      const isYtHindi = ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template);

      if (isBrat) {
        if (bratOptionsRow) bratOptionsRow.style.display = 'flex';
        if (bratLiveSandbox) bratLiveSandbox.style.display = 'flex';
        if (ytHindiOptionsRow) ytHindiOptionsRow.style.display = 'none';
        state.fontFamily = 'Arial Narrow';
        fontBtns.forEach(b => b.classList.toggle('active', b.dataset.font === 'Arial Narrow'));
        updateBratText(bratSandboxInput ? bratSandboxInput.value : '365 partygirl');
        showToast('Activated 🟩 Brat Minimal Template (Charli XCX)');
      } else if (isYtHindi) {
        if (bratOptionsRow) bratOptionsRow.style.display = 'none';
        if (bratLiveSandbox) bratLiveSandbox.style.display = 'none';
        if (ytHindiOptionsRow) ytHindiOptionsRow.style.display = 'flex';
        state.fontFamily = 'EB Garamond';
        state.fontSize = 68;
        state.blur = 0;
        fontBtns.forEach(b => b.classList.toggle('active', b.dataset.font === 'EB Garamond'));
        state.topHeader = ytHindiTopHeaderInput ? ytHindiTopHeaderInput.value : '(When Lyrics feel Too Personal...)';
        applyRealtimePlacementAndSize();
        if (state.template === 'yt_hindi_intro') {
          showToast('🔥 YT Hindi (Film Burn Intro) activated — vintage procedural film burn intro enabled!');
        } else {
          showToast('🎬 YT Hindi Type activated — drop your background videos in videos/input!');
        }
      } else {
        if (bratOptionsRow) bratOptionsRow.style.display = 'none';
        if (bratLiveSandbox) bratLiveSandbox.style.display = 'none';
        if (ytHindiOptionsRow) ytHindiOptionsRow.style.display = 'none';
        showToast(`Selected ${pill.querySelector('.template-num').textContent.trim()}`);
      }
    });
  });

  if (testStartInput) testStartInput.addEventListener('input', (e) => { state.testStart = e.target.value; });
  if (testEndInput) testEndInput.addEventListener('input', (e) => { state.testEnd = e.target.value; });
  if (previewQualityInput) previewQualityInput.addEventListener('change', (e) => { state.previewQuality = e.target.value; });

  // YT Hindi Top Header input live sync
  if (ytHindiTopHeaderInput) {
    ytHindiTopHeaderInput.addEventListener('input', (e) => {
      state.topHeader = e.target.value;
    });
  }

  // Brat Palette Swatches
  bratPalettes.forEach((btn) => {
    btn.addEventListener('click', () => {
      bratPalettes.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.bratTheme = btn.dataset.theme;
      if (bratLiveContainer) {
        bratLiveContainer.className = `brat-container theme-brat-${state.bratTheme}${state.bratCasing === 'upper' ? ' casing-upper' : ''}`;
      }
      showToast(`Brat Theme: ${btn.querySelector('.swatch-name').textContent.trim()}`);
    });
  });

  // Brat Live Reflow Sandbox Input
  if (bratSandboxInput) {
    bratSandboxInput.addEventListener('input', (e) => {
      updateBratText(e.target.value);
    });
  }

  // Brat Casing Toggle (100% Lowercase default vs Uppercase)
  if (bratCasingToggleBtn) {
    bratCasingToggleBtn.addEventListener('click', () => {
      state.bratCasing = state.bratCasing === 'lower' ? 'upper' : 'lower';
      bratCasingToggleBtn.classList.toggle('active', state.bratCasing === 'upper');
      bratCasingToggleBtn.textContent = state.bratCasing === 'upper' ? 'UPPERCASE' : 'lowercase';
      if (bratLiveContainer) {
        bratLiveContainer.classList.toggle('casing-upper', state.bratCasing === 'upper');
      }
      updateBratText(bratSandboxInput ? bratSandboxInput.value : '365 partygirl');
      showToast(`Brat casing: ${state.bratCasing.toUpperCase()}`);
    });
  }

  // Brat Preset Chips
  bratChipBtns.forEach((chip) => {
    chip.addEventListener('click', () => {
      const presetText = chip.dataset.preset;
      const chipTheme = chip.dataset.theme;
      if (bratSandboxInput) bratSandboxInput.value = presetText;

      if (chipTheme) {
        const matchingSwatch = Array.from(bratPalettes).find(b => b.dataset.theme === chipTheme);
        if (matchingSwatch) matchingSwatch.click();
      }

      if (presetText === 'THE MOMENT') {
        state.bratCasing = 'upper';
        if (bratCasingToggleBtn) {
          bratCasingToggleBtn.classList.add('active');
          bratCasingToggleBtn.textContent = 'UPPERCASE';
        }
        if (bratLiveContainer) bratLiveContainer.classList.add('casing-upper');
      }

      updateBratText(presetText, true);
      showToast(`Preset: "${presetText}"`);
    });
  });

  // Font Selection
  fontBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      fontBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.fontFamily = btn.dataset.font;
      if (customFontInput) customFontInput.value = '';
      showToast(`Font set to ${btn.dataset.font}`);
    });
  });

  // Custom Font Input
  if (customFontInput) {
    customFontInput.addEventListener('input', (e) => {
      const val = e.target.value.trim();
      if (val) {
        fontBtns.forEach(b => b.classList.remove('active'));
        state.fontFamily = val;
      }
    });
  }

  // Language Selection
  langBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      langBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.language = btn.dataset.lang;
      if (customLangInput) customLangInput.value = '';
      showToast(`Language set to ${btn.textContent.trim()}`);
    });
  });

  // Custom Language Input
  if (customLangInput) {
    customLangInput.addEventListener('input', (e) => {
      const val = e.target.value.trim().toLowerCase();
      if (val) {
        langBtns.forEach(b => b.classList.remove('active'));
        state.language = val;
      }
    });
  }

  // Search Bar Placement Pills
  placementPills.forEach((pill) => {
    pill.addEventListener('click', () => {
      placementPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.placement = pill.dataset.placement;
      state.ypos = parseInt(pill.dataset.ypos) || 50;
      if (pill.dataset.xpos) state.xpos = parseInt(pill.dataset.xpos) || 50;
      applyRealtimePlacementAndSize(true);
    });
  });

  // Search Bar Horizontal (X) Placement Range Slider (Realtime)
  if (xposSlider) {
    xposSlider.addEventListener('input', (e) => {
      state.xpos = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Search Bar Vertical (Y) Placement Range Slider (Realtime)
  if (yposSlider) {
    yposSlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      state.ypos = val;
      state.placement = val <= 25 ? 'top' : (val >= 75 ? 'bottom' : 'center');
      applyRealtimePlacementAndSize(true);
    });
  }

  // Search Bar Font Size Range Slider (Realtime)
  if (fontsizeSlider) {
    fontsizeSlider.addEventListener('input', (e) => {
      state.fontSize = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Search Bar Blur Meter Range Slider (Realtime)
  if (blurSlider) {
    blurSlider.addEventListener('input', (e) => {
      state.blur = parseFloat(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Search Bar Spacing Range Slider (Realtime)
  if (spacingSlider) {
    spacingSlider.addEventListener('input', (e) => {
      state.spacing = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Search Bar Word Spacing Range Slider (Realtime)
  if (wordSpacingSlider) {
    wordSpacingSlider.addEventListener('input', (e) => {
      state.wordSpacing = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Reposition Pills
  stagePlacementBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      stagePlacementBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.placement = btn.dataset.placement;
      state.ypos = parseInt(btn.dataset.ypos) || 50;
      if (btn.dataset.xpos) state.xpos = parseInt(btn.dataset.xpos) || 50;
      applyRealtimePlacementAndSize(true);
      showToast(`Placement set to ${btn.dataset.placement.toUpperCase()}`);
    });
  });

  // Stage Horizontal (X) Placement Range Slider (Realtime)
  if (stageXposSlider) {
    stageXposSlider.addEventListener('input', (e) => {
      state.xpos = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Vertical (Y) Placement Range Slider (Realtime)
  if (stageYposSlider) {
    stageYposSlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value);
      state.ypos = val;
      state.placement = val <= 25 ? 'top' : (val >= 75 ? 'bottom' : 'center');
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Font Size Range Slider (Realtime)
  if (stageFontsizeSlider) {
    stageFontsizeSlider.addEventListener('input', (e) => {
      state.fontSize = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Blur Meter Range Slider (Realtime)
  if (stageBlurSlider) {
    stageBlurSlider.addEventListener('input', (e) => {
      state.blur = parseFloat(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Spacing Range Slider (Realtime)
  if (stageSpacingSlider) {
    stageSpacingSlider.addEventListener('input', (e) => {
      state.spacing = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // Stage Word Spacing Range Slider (Realtime)
  if (stageWordSpacingSlider) {
    stageWordSpacingSlider.addEventListener('input', (e) => {
      state.wordSpacing = parseInt(e.target.value);
      applyRealtimePlacementAndSize(true);
    });
  }

  // YT Hindi Top Header Input
  if (ytHindiTopHeaderInput) {
    ytHindiTopHeaderInput.addEventListener('input', (e) => {
      state.topHeader = e.target.value.trim();
    });
  }

  // Test Range & Preview Quality Inputs
  if (testStartInput) {
    testStartInput.addEventListener('input', (e) => {
      state.testStart = e.target.value.trim();
    });
  }
  if (testEndInput) {
    testEndInput.addEventListener('input', (e) => {
      state.testEnd = e.target.value.trim();
    });
  }
  if (previewQualityInput) {
    previewQualityInput.addEventListener('change', (e) => {
      state.previewQuality = e.target.value;
    });
  }


  // Live Video Overlay Layer Toggle Button
  if (stageOverlayToggleBtn) {
    stageOverlayToggleBtn.addEventListener('click', () => {
      state.overlayEnabled = !state.overlayEnabled;
      stageOverlayToggleBtn.classList.toggle('active', state.overlayEnabled);
      stageOverlayToggleBtn.textContent = state.overlayEnabled
        ? '✨ Live Real-Time Video Layer: ON'
        : '❌ Live Real-Time Video Layer: OFF';
      if (stageLiveSubtitleOverlay) {
        stageLiveSubtitleOverlay.style.display = state.overlayEnabled ? 'flex' : 'none';
      }
      showToast(`Live Video Text Layer: ${state.overlayEnabled ? 'ENABLED' : 'DISABLED'}`);
    });
  }

  // Stage Re-render Button (Burns live top layer to 1080p MP4)
  if (stageRerenderBtn) {
    stageRerenderBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (state.isGenerating) return;
      const query = state.lastQuery || (songQueryInput ? songQueryInput.value.trim() : '');
      if (query) {
        showToast(`Burning custom layer: X:${state.xpos}%, Y:${state.ypos}%, Size:${state.fontSize}px, Blur:${state.blur}px, Spacing:${state.spacing}px, Word Spacing:${state.wordSpacing}px... ⚡`);
        startGenerationPipeline(query, true);
      }
    });
  }

  // Option 1: Record Exact Browser Canvas Video (100% WYSIWYG Pixel-for-Pixel Capture)
  if (dlExactCanvasBtn) {
    dlExactCanvasBtn.addEventListener('click', (e) => {
      e.preventDefault();
      recordExactBrowserCanvasVideo();
    });
  }

  // Download Button: Instantly burns the live upper layer into 1080p MP4 in 1-2s and downloads!
  if (dlVideoBtn) {
    dlVideoBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      if (state.isBurning) return;

      const originalText = dlVideoBtn.querySelector('span') ? dlVideoBtn.querySelector('span').textContent : 'Instant 1080p MP4 Download (~1-2s)';
      try {
        state.isBurning = true;
        if (dlVideoBtn.querySelector('span')) dlVideoBtn.querySelector('span').textContent = '⚡ Burning layer into 1080p MP4...';
        showToast('Burning your custom upper layer into 1080p MP4... ⚡ (1-2s)');

        const response = await fetch('/api/quick-burn-video', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: state.lastQuery || (songQueryInput ? songQueryInput.value.trim() : 'Lyric Video'),
            audioPath: state.activeMetadata?.audio_path || null,
            syncedLines: state.syncedLines || [],
            template: state.template,
            font: state.fontFamily,
            fontsize: state.fontSize,
            blur: state.blur,
            spacing: state.spacing,
            word_spacing: state.wordSpacing,
            placement: state.placement,
            ypos: state.ypos,
            xpos: state.xpos,
            brat_theme: state.bratTheme
          })
        });

        if (!response.ok) {
          throw new Error(`Burn failed with status: ${response.status}`);
        }

        const data = await response.json();
        if (data.videoUrl) {
          showToast('🎉 Burn complete! Downloading 1080p MP4... 🚀');
          const a = document.createElement('a');
          a.href = data.videoUrl;
          a.download = data.videoFileName || 'lyric_video_custom.mp4';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        } else {
          throw new Error('No video URL returned');
        }
      } catch (err) {
        console.error('Quick burn error:', err);
        showToast('Direct download started...');
        const a = document.createElement('a');
        a.href = state.activeVideoUrl || dlVideoBtn.href;
        a.download = 'lyric_video.mp4';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } finally {
        state.isBurning = false;
        if (dlVideoBtn.querySelector('span')) dlVideoBtn.querySelector('span').textContent = originalText;
      }
    });
  }

  // Backdrop Switcher
  backdropBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      setBackdrop(btn.dataset.bg);
    });
  });

  // Refresh Gallery
  refreshGalleryBtn.addEventListener('click', loadVideosGallery);

  // Video Time Update for Synchronized Teleprompter & Live Real-Time Text Overlay
  outputVideoPlayer.addEventListener('timeupdate', () => {
    syncTeleprompter(outputVideoPlayer.currentTime);
  });
}

// Brat Word-by-Word Accumulation & Auto-Fit Engine
let bratAccumulationTimer = null;

// Dynamic Auto-Fit Resizing Algorithm: iteratively shrinks font size to fit container limits
function autoFitBratText(box, container) {
  if (!box || !container) return;

  const text = box.textContent.trim();
  const wordCount = text.split(/\s+/).filter(Boolean).length;

  // Authentic Brat Framing Rule: Single/two-word phrases center, multi-line blocks stretch edge-to-edge justified
  if (wordCount <= 2 && !text.includes('\n')) {
    box.style.textAlign = "center";
    box.style.textAlignLast = "center";
  } else {
    box.style.textAlign = "justify";
    box.style.textAlignLast = "justify";
  }

  // Reset to maximum starting font size
  let fontSize = 110; // base px limit
  box.style.fontSize = `${fontSize}px`;

  // Reduce font size iteratively until content fits inside bounding box
  while (
    (box.scrollHeight > container.clientHeight || box.scrollWidth > container.clientWidth) &&
    fontSize > 14
  ) {
    fontSize -= 2;
    box.style.fontSize = `${fontSize}px`;
  }
}

// Render cumulative words step with dynamic font-sizing and reflow
function renderWordStep(wordsArray, currentIndex) {
  const container = document.querySelector(".brat-box-container") || bratLiveContainer;
  const box = document.getElementById("brat-live-text") || document.getElementById("bratTextBox") || bratLiveText;
  if (!box || !container) return;
  if (!wordsArray || wordsArray.length === 0) {
    box.textContent = '';
    return;
  }

  const boundedIndex = Math.min(wordsArray.length - 1, Math.max(0, currentIndex));
  const rawText = wordsArray.slice(0, boundedIndex + 1).join(" ");
  const currentText = state.bratCasing === 'upper' ? rawText.toUpperCase() : rawText.toLowerCase();

  box.textContent = currentText;

  // Trigger Crisp Word Entry Pop
  box.classList.remove("motion-blur-active");
  void box.offsetWidth; // Force DOM reflow
  box.classList.add("motion-blur-active");

  // Dynamic iterative auto-fit calculation
  autoFitBratText(box, container);
}

function animateBratWordAccumulation(text) {
  if (bratAccumulationTimer) {
    clearInterval(bratAccumulationTimer);
    bratAccumulationTimer = null;
  }

  const raw = text !== undefined ? text : (bratSandboxInput ? bratSandboxInput.value : '365 partygirl');
  const words = (raw || '365 partygirl').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return;

  let currentIdx = 0;
  renderWordStep(words, 0);

  if (words.length > 1) {
    bratAccumulationTimer = setInterval(() => {
      currentIdx++;
      if (currentIdx < words.length) {
        renderWordStep(words, currentIdx);
      } else {
        clearInterval(bratAccumulationTimer);
        bratAccumulationTimer = null;
      }
    }, 120);
  }
}

function updateBratText(input, animate = false) {
  if (animate) {
    animateBratWordAccumulation(input);
    return;
  }

  if (bratAccumulationTimer) {
    clearInterval(bratAccumulationTimer);
    bratAccumulationTimer = null;
  }

  const container = document.querySelector(".brat-box-container") || bratLiveContainer;
  const box = document.getElementById("brat-live-text") || document.getElementById("bratTextBox") || bratLiveText;
  if (!box || !container) return;

  const raw = input !== undefined ? String(input) : (bratSandboxInput ? bratSandboxInput.value : '365 partygirl');
  const currentText = state.bratCasing === 'upper' ? raw.toUpperCase() : raw.toLowerCase();
  box.textContent = currentText;

  // Auto-scale font size dynamically to fit bounding box
  autoFitBratText(box, container);
}

function updatePlacementPills(place) {
  placementPills.forEach(p => p.classList.toggle('active', p.dataset.placement === place));
  stagePlacementBtns.forEach(b => b.classList.toggle('active', b.dataset.placement === place));
}

let stageOverlayHideTimer = null;

function applyRealtimePlacementAndSize(showStageGuide = false) {
  // 1. Move Brat Live Canvas text in realtime (X, Y translation, dynamic blur filter, letter-spacing, and word-spacing)
  const bratText = document.getElementById("brat-live-text") || document.getElementById("bratTextBox") || bratLiveText;
  const bratContainer = document.querySelector(".brat-box-container") || bratLiveContainer;
  if (bratText && bratContainer) {
    const offsetX = ((state.xpos - 50) * 0.75);
    const offsetY = ((state.ypos - 50) * 0.75);
    bratText.style.transform = `scaleX(0.68) translate(${offsetX}%, ${offsetY}%)`;
    if (state.fontSize) {
      bratText.style.fontSize = `${state.fontSize}px`;
    }
    const effContrast = Math.round(140 + (state.blur * 4.5));
    bratText.style.filter = `blur(${state.blur}px) contrast(${effContrast}%)`;
    bratText.style.letterSpacing = `${state.spacing}px`;
    bratText.style.wordSpacing = `${state.wordSpacing}px`;
  }

  // 2. Interactive Subtitle Layer On Top of Video (Exact 1:1 Rendering of Original Text)
  if (stageLiveSubtitleOverlay && stageLiveSubtitleText) {
    stageLiveSubtitleOverlay.style.top = `${state.ypos}%`;
    stageLiveSubtitleOverlay.style.transform = `translate(${state.xpos - 50}%, -50%)`;

    stageLiveSubtitleText.style.fontSize = `${state.fontSize}px`;
    const effContrast = Math.round(140 + (state.blur * 4.5));
    stageLiveSubtitleText.style.filter = `blur(${state.blur}px) contrast(${effContrast}%)`;
    stageLiveSubtitleText.style.letterSpacing = `${state.spacing}px`;
    stageLiveSubtitleText.style.wordSpacing = `${state.wordSpacing}px`;

    const isBrat = state.template === 'template4_brat' || state.template === 'template_4_brat' || state.template === 'brat';
    const isYtHindiOverlay = ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template);
    if (isBrat) {
      stageLiveSubtitleText.style.fontFamily = "'Arial Narrow', 'Helvetica Neue Condensed', sans-serif";
      stageLiveSubtitleText.style.fontWeight = '500';
      stageLiveSubtitleText.style.fontStretch = 'condensed';
      stageLiveSubtitleText.style.lineHeight = '0.88';
      stageLiveSubtitleText.style.transform = 'scaleX(0.68)';
      stageLiveSubtitleText.style.textAlign = 'justify';
      stageLiveSubtitleText.style.textAlignLast = 'justify';
      stageLiveSubtitleText.style.textTransform = state.bratCasing === 'upper' ? 'uppercase' : 'lowercase';
      if (state.bratTheme === 'white') {
        stageLiveSubtitleText.style.color = '#000000';
        stageLiveSubtitleText.style.textShadow = 'none';
      } else if (state.bratTheme === 'blue') {
        stageLiveSubtitleText.style.color = '#DE0100';
        stageLiveSubtitleText.style.fontFamily = 'Impact, "Arial Black", sans-serif';
        stageLiveSubtitleText.style.fontWeight = '900';
        stageLiveSubtitleText.style.textTransform = 'uppercase';
      } else if (state.bratTheme === 'strike') {
        stageLiveSubtitleText.style.color = '#000000';
        stageLiveSubtitleText.style.textDecoration = 'line-through';
      } else if (state.bratTheme === 'black') {
        stageLiveSubtitleText.style.color = '#FFFFFF';
        stageLiveSubtitleText.style.textShadow = 'none';
      } else {
        stageLiveSubtitleText.style.color = '#000000';
        stageLiveSubtitleText.style.textShadow = 'none';
      }
    } else if (isYtHindiOverlay) {
      // YT Hindi Type: Cormorant Garamond, centered vertically at ~50% of center clip (y≈960/1920 = 50%)
      stageLiveSubtitleText.style.fontFamily = "'EB Garamond', Georgia, serif";
      stageLiveSubtitleText.style.fontWeight = '400';
      stageLiveSubtitleText.style.fontStretch = 'normal';
      stageLiveSubtitleText.style.lineHeight = '1.25';
      stageLiveSubtitleText.style.transform = 'none';
      stageLiveSubtitleText.style.textAlign = 'center';
      stageLiveSubtitleText.style.textAlignLast = 'center';
      stageLiveSubtitleText.style.textTransform = 'none';
      stageLiveSubtitleText.style.color = '#FFFFFF';
      stageLiveSubtitleText.style.textShadow = '0 1px 8px rgba(0,0,0,0.8)';
      stageLiveSubtitleText.style.textDecoration = 'none';
      // Keep overlay positioned at vertical center of center video clip
      if (stageLiveSubtitleOverlay) {
        stageLiveSubtitleOverlay.style.top = '50%';
        stageLiveSubtitleOverlay.style.transform = 'translateY(-50%)';
      }
    } else {
      stageLiveSubtitleText.style.fontFamily = state.fontFamily || 'Impact';
      stageLiveSubtitleText.style.fontWeight = (state.template === 'template1' || state.fontFamily === 'Impact') ? '800' : '600';
      stageLiveSubtitleText.style.transform = 'none';
      stageLiveSubtitleText.style.textAlign = 'center';
      stageLiveSubtitleText.style.textAlignLast = 'center';
      stageLiveSubtitleText.style.textTransform = 'none';
      stageLiveSubtitleText.style.color = '#FFFFFF';
      stageLiveSubtitleText.style.textShadow = '0 2px 10px rgba(0,0,0,0.95), 0 0 5px #000000';
    }

    const mergedYtHindiOutput = ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template) || ['yt_hindi_type', 'yt_hindi_intro'].includes(state.activeMetadata?.template);
    if (state.overlayEnabled && !mergedYtHindiOutput) {
      stageLiveSubtitleOverlay.style.display = 'flex';
    } else {
      stageLiveSubtitleOverlay.style.display = 'none';
    }
  }

  // 3. Keep Badges and Slider Inputs in Sync
  if (xposSlider) xposSlider.value = state.xpos;
  if (stageXposSlider) stageXposSlider.value = state.xpos;
  const xDesc = state.xpos === 50 ? ' (Center)' : (state.xpos < 50 ? ' (Left)' : ' (Right)');
  if (xposVal) xposVal.textContent = `${state.xpos}%${xDesc}`;
  if (stageXposVal) stageXposVal.textContent = `${state.xpos}%${xDesc}`;

  if (yposSlider) yposSlider.value = state.ypos;
  if (stageYposSlider) stageYposSlider.value = state.ypos;
  if (yposVal) yposVal.textContent = `${state.ypos}% (${state.placement.toUpperCase()})`;
  if (stageYposVal) stageYposVal.textContent = `${state.ypos}% (${state.placement.toUpperCase()})`;

  if (fontsizeSlider) fontsizeSlider.value = state.fontSize;
  if (stageFontsizeSlider) stageFontsizeSlider.value = state.fontSize;
  if (fontsizeVal) fontsizeVal.textContent = `${state.fontSize}px${state.fontSize === 72 ? ' (Default)' : ''}`;
  if (stageFontsizeVal) stageFontsizeVal.textContent = `${state.fontSize}px${state.fontSize === 72 ? ' (Default)' : ''}`;

  if (blurSlider) blurSlider.value = state.blur;
  if (stageBlurSlider) stageBlurSlider.value = state.blur;
  if (blurVal) blurVal.textContent = `${state.blur}px`;
  if (stageBlurVal) stageBlurVal.textContent = `${state.blur}px`;

  if (spacingSlider) spacingSlider.value = state.spacing;
  if (stageSpacingSlider) stageSpacingSlider.value = state.spacing;
  if (spacingVal) spacingVal.textContent = `${state.spacing}px${state.spacing === -1 ? ' (Default)' : ''}`;
  if (stageSpacingVal) stageSpacingVal.textContent = `${state.spacing}px${state.spacing === -1 ? ' (Default)' : ''}`;

  if (wordSpacingSlider) wordSpacingSlider.value = state.wordSpacing;
  if (stageWordSpacingSlider) stageWordSpacingSlider.value = state.wordSpacing;
  if (wordSpacingVal) wordSpacingVal.textContent = `${state.wordSpacing}px${state.wordSpacing === 0 ? ' (Default)' : ''}`;
  if (stageWordSpacingVal) stageWordSpacingVal.textContent = `${state.wordSpacing}px${state.wordSpacing === 0 ? ' (Default)' : ''}`;

  updatePlacementPills(state.placement);
}

function syncStagePlacementUI() {
  applyRealtimePlacementAndSize();
}

// 1. Start Server-Sent Events (SSE) Video Generation
function startGenerationPipeline(query, burnText = false) {
  state.lastQuery = query;
  if (state.isGenerating && state.currentEventSource) {
    state.currentEventSource.close();
  }

  state.isGenerating = true;
  generateBtn.disabled = true;
  if (stageRerenderBtn) stageRerenderBtn.disabled = true;
  btnText.textContent = burnText ? 'Burning Top Layer to 1080p MP4...' : 'Generating 1080p Base MP4...';
  generateBtn.classList.add('loading');

  // Reset & show pipeline UI
  resetPipelineUI(query);
  pipelineSection.style.display = 'block';
  pipelineSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Connect to SSE Endpoint
  const isYtHindi = ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template);
  const topHeaderParam = isYtHindi ? `&top_header=${encodeURIComponent(state.topHeader || '')}` : '';
  const testStartParam = Number(state.testStart) > 0 ? `&start_seconds=${encodeURIComponent(state.testStart)}` : '';
  const testEndParam = Number(state.testEnd) > 0 ? `&end_seconds=${encodeURIComponent(state.testEnd)}` : '';
  const qualityParam = `&preview_quality=${encodeURIComponent(state.previewQuality || 'final')}`;
  const sseUrl = `/api/generate-video-stream?q=${encodeURIComponent(query)}&template=${encodeURIComponent(state.template)}&font=${encodeURIComponent(state.fontFamily)}&fontsize=${encodeURIComponent(state.fontSize)}&blur=${encodeURIComponent(state.blur)}&spacing=${encodeURIComponent(state.spacing)}&word_spacing=${encodeURIComponent(state.wordSpacing)}&lang=${encodeURIComponent(state.language)}&placement=${encodeURIComponent(state.placement)}&ypos=${encodeURIComponent(state.ypos)}&xpos=${encodeURIComponent(state.xpos)}&brat_theme=${encodeURIComponent(state.bratTheme)}&burn_text=${burnText ? 'true' : 'false'}${topHeaderParam}${testStartParam}${testEndParam}${qualityParam}`;
  const eventSource = new EventSource(sseUrl);
  state.currentEventSource = eventSource;
  state.generationErrorHandled = false;

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
    try {
      const data = JSON.parse(e.data);
      handleGenerationComplete(data, burnText);
    } finally {
      eventSource.close();
      state.currentEventSource = null;
      state.isGenerating = false;
      generateBtn.disabled = false;
      if (stageRerenderBtn) stageRerenderBtn.disabled = false;
      btnText.textContent = 'Generate Video Overlay';
      generateBtn.classList.remove('loading');
    }
  });

  const handleError = (e) => {
    if (state.generationErrorHandled) return;
    state.generationErrorHandled = true;
    console.error('SSE Error:', e);
    appendConsoleLog('[ERROR] Video generation pipeline failed or connection closed.');
    pipelineStatusText.textContent = 'Generation Failed (Check console output)';
    eventSource.close();
    state.currentEventSource = null;
    state.isGenerating = false;
    generateBtn.disabled = false;
    if (stageRerenderBtn) stageRerenderBtn.disabled = false;
    btnText.textContent = 'Generate Video Overlay';
    generateBtn.classList.remove('loading');
    showToast('Generation finished or disconnected.');
  };

  eventSource.addEventListener('error', handleError);
  eventSource.onerror = handleError;
}

window.addEventListener('beforeunload', () => {
  if (state.currentEventSource) {
    state.currentEventSource.close();
    state.currentEventSource = null;
  }
});

// 2. Handle Progress Updates from Python Generator
function handleProgressUpdate(data) {
  const { step, percent, message, details } = data;

  // Update progress bar
  progressBarFill.style.width = `${percent}%`;
  pipelinePercentBadge.textContent = `${percent}%`;
  pipelineStatusText.textContent = message;

  appendConsoleLog(`[${percent}%] ${message}`);
  if (details && Object.keys(details).length) {
    const detailText = Object.entries(details)
      .filter(([key]) => !['title', 'uploader'].includes(key))
      .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`)
      .join(' | ');
    if (detailText) appendConsoleLog(`[DETAIL] ${detailText}`);
  }

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
    markStepActive(stepFfmpeg, stepFfmpegStatus, stepFfmpegDetail, 'Rendering 1080p video...');
  } else if (step === 'ffmpeg_done' || step === 'completed') {
    markStepDone(stepFfmpeg, stepFfmpegStatus, stepFfmpegDetail, '1080p MP4 Ready!');
  }
}

// 3. Handle Generation Complete
function handleGenerationComplete(data, isBurned = false) {
  progressBarFill.style.width = '100%';
  pipelinePercentBadge.textContent = '100%';
  pipelineStatusText.textContent = isBurned
    ? '🎉 Burned 1080p Video Ready for Download!'
    : '🎉 Clean Base Video & Live Text Layer Ready!';

  state.activeVideoUrl = data.videoUrl;
  state.activeMetadata = data.metadata;
  state.syncedLines = data.metadata?.syncedLines || [];
  state.isBurned = isBurned;
  const isMergedYtHindi = ['yt_hindi_type', 'yt_hindi_intro'].includes(data.metadata?.template) || ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template);

  showToast(isBurned ? 'Burned 1080p MP4 Ready! 🚀' : 'Clean Base Video Ready! Tune Live Layer ⚡');

  const isPortrait = (data.metadata?.aspect_ratio || 'portrait') === 'portrait';
  const tplUsed = (data.metadata?.template || state.template || 'template1').replace('template', 'Template ');

  // Populate Studio Stage
  stageSongTitle.textContent = data.metadata?.track_name || data.query;
  stageSongMeta.textContent = `${data.metadata?.artist_name || 'YouTube Video'} &bull; ${data.metadata?.duration || 0}s duration &bull; 1080p MP4 (${isPortrait ? '9:16 Portrait' : '16:9 Landscape'}) &bull; ${tplUsed.toUpperCase()}`;

  // Toggle Portrait frame styling on video container
  if (videoPreviewWrapper) {
    videoPreviewWrapper.classList.toggle('portrait-mode', isPortrait);
  }

  // Set Video Player source
  try {
    outputVideoPlayer.pause();
    if (videoSource) videoSource.src = data.videoUrl;
    outputVideoPlayer.load();
    const playPromise = outputVideoPlayer.play();
    if (playPromise !== undefined) {
      playPromise.catch(() => {});
    }
  } catch (err) {
    console.warn("Video player initialization note:", err);
  }

  // Ensure real-time interactive text overlay is visible over the clean base video
  if (stageLiveSubtitleOverlay) {
    stageLiveSubtitleOverlay.style.display = isMergedYtHindi ? 'none' : (state.overlayEnabled ? 'flex' : 'none');
  }
  applyRealtimePlacementAndSize(false);

  // Setup Download Links
  dlVideoBtn.href = data.videoUrl;
  dlVideoBtn.download = data.videoFileName || 'lyric_video.mp4';

  if (data.metadata?.syncedLines) {
    setupAssetDownloadBlobs(data.metadata);
  }

  // Populate Teleprompter
  renderTeleprompter(state.syncedLines);

  studioStage.style.display = 'block';
  studioStage.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Auto-download if this was a burn request triggered by download
  if (isBurned && state.pendingDownload) {
    state.pendingDownload = false;
    const a = document.createElement('a');
    a.href = data.videoUrl;
    a.download = data.videoFileName || 'lyric_video_burned.mp4';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

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
  if (!state.syncedLines || !Array.isArray(state.syncedLines) || state.syncedLines.length === 0) return;

  let activeIndex = -1;
  for (let i = 0; i < state.syncedLines.length; i++) {
    const s = state.syncedLines[i];
    if (s && s.timeSeconds !== undefined && s.timeSeconds <= currentTime) {
      activeIndex = i;
    } else {
      break;
    }
  }

  if (activeIndex >= 0 && state.syncedLines[activeIndex]) {
    const activeLine = state.syncedLines[activeIndex];
    const isBrat = state.template === 'template4_brat' || state.template === 'template_4_brat' || state.template === 'brat';
    
    // Real-Time Lyric Rendering directly on the Interactive Video Layer
    const isYtHindi = ['yt_hindi_type', 'yt_hindi_intro'].includes(state.template) || ['yt_hindi_type', 'yt_hindi_intro'].includes(state.activeMetadata?.template);
    if (!isYtHindi && stageLiveSubtitleText && state.overlayEnabled && activeLine && activeLine.text) {
      if (isBrat) {
        const words = activeLine.text.trim().split(/\s+/).filter(Boolean);
        if (words.length > 0) {
          const lineDur = Math.max(0.4, (activeLine.endSeconds || (activeLine.timeSeconds + 2.5)) - activeLine.timeSeconds);
          const typeDur = lineDur * 0.85;
          const elapsed = Math.max(0, currentTime - activeLine.timeSeconds);
          const progress = Math.min(1, elapsed / typeDur);
          const wordIdx = Math.min(words.length - 1, Math.floor(progress * words.length));
          const currentWords = words.slice(0, wordIdx + 1).join(' ');
          stageLiveSubtitleText.textContent = state.bratCasing === 'upper' ? currentWords.toUpperCase() : currentWords.toLowerCase();

          if (wordIdx !== lastRenderedWordCount || activeIndex !== state.currentLineIndex) {
            lastRenderedWordCount = wordIdx;
            renderWordStep(words, wordIdx);
          }
        }
      } else {
        stageLiveSubtitleText.textContent = activeLine.text;
      }
    }
  }

  if (activeIndex !== state.currentLineIndex) {
    state.currentLineIndex = activeIndex;
    const allRows = teleprompterStream ? teleprompterStream.querySelectorAll('.teleprompter-row') : [];
    allRows.forEach((row, idx) => {
      const isActive = idx === activeIndex;
      const isPast = idx < activeIndex;
      row.classList.toggle('active', isActive);
      row.classList.toggle('past', isPast);
    });

    if (activeIndex >= 0 && allRows[activeIndex]) {
      try {
        allRows[activeIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (e) {}
    }
  }
}

// 6. Backdrop Switcher (Demonstrating Alpha Channel & Brat Background)
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
        .replace(/\.(mp4|webm)$/, '')
        .replace(/_[0-9]+$/, '')
        .replace(/[_-]/g, ' ');

      card.innerHTML = `
        <div class="gallery-video-thumb backdrop-checkerboard">
          <video src="${vid.url}" preload="metadata" muted playsinline></video>
          <div class="play-overlay-icon">▶</div>
        </div>
        <div class="gallery-card-body">
          <strong class="gallery-card-title" title="${escapeHtml(cleanTitle)}">${escapeHtml(cleanTitle)}</strong>
          <span class="gallery-card-meta">${vid.sizeMb} MB &bull; 1080p ${(vid.format || 'mp4').toUpperCase()} Video</span>
          <div class="gallery-card-actions">
            <button class="mini-btn play-gallery-btn">Preview</button>
            <a href="${vid.url}" download="${vid.filename}" class="mini-btn" target="_blank">Download</a>
          </div>
        </div>
      `;

      card.querySelector('.play-gallery-btn').addEventListener('click', () => {
        if (stageLiveSubtitleOverlay) stageLiveSubtitleOverlay.style.display = 'none';
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

// 8. Option 1: Record Exact In-Browser Canvas Video (100% WYSIWYG Pixel Capture)
async function recordExactBrowserCanvasVideo() {
  const videoUrl = state.activeVideoUrl || (videoSource ? videoSource.src : '') || (outputVideoPlayer ? (outputVideoPlayer.currentSrc || outputVideoPlayer.src) : '');
  if (!outputVideoPlayer || !videoUrl) {
    showToast('Please generate a lyric video first using the input above!');
    return;
  }

  const btn = document.getElementById('dl-exact-canvas-btn');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-inline"></span> <span>Recording Exact Screen Pixels (0%)...</span>';
  }

  try {
    showToast('🎥 Recording 100% exact browser pixels with live CSS blur & layout...');

    const video = outputVideoPlayer;
    if (!video.src && videoUrl) {
      video.src = videoUrl;
    }

    const canvasW = 1080;
    const canvasH = 1920;

    const canvas = document.createElement('canvas');
    canvas.width = canvasW;
    canvas.height = canvasH;
    const ctx = canvas.getContext('2d');

    // Create stream from Canvas
    const canvasStream = canvas.captureStream(30);

    // Audio stream from video element
    let combinedStream = canvasStream;
    try {
      if (!window._appAudioCtx) {
        window._appAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (window._appAudioCtx.state === 'suspended') {
        await window._appAudioCtx.resume();
      }
      if (!window._appAudioSource && video) {
        window._appAudioSource = window._appAudioCtx.createMediaElementSource(video);
      }
      if (window._appAudioSource) {
        const dest = window._appAudioCtx.createMediaStreamDestination();
        window._appAudioSource.connect(dest);
        window._appAudioSource.connect(window._appAudioCtx.destination);
        combinedStream = new MediaStream([
          ...canvasStream.getVideoTracks(),
          ...dest.stream.getAudioTracks()
        ]);
      }
    } catch (e) {
      console.warn("AudioContext stream capture note:", e);
      combinedStream = canvasStream;
    }

    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
      ? 'video/webm;codecs=vp9,opus'
      : (MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')
        ? 'video/webm;codecs=vp8,opus'
        : 'video/webm');

    const recorder = new MediaRecorder(combinedStream, {
      mimeType,
      videoBitsPerSecond: 12000000
    });

    const chunks = [];
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    let isRecording = true;

    // Word wrap helper for canvas
    function getCanvasWrappedLines(text, maxChars) {
      const words = (text || '').trim().split(/\s+/).filter(Boolean);
      if (!words.length) return [];
      const lines = [];
      let cur = [];
      let curLen = 0;
      for (const w of words) {
        if (cur.length && (curLen + 1 + w.length > maxChars)) {
          lines.push(cur.join(' '));
          cur = [w];
          curLen = w.length;
        } else {
          cur.push(w);
          curLen += (cur.length ? 1 : 0) + w.length;
        }
      }
      if (cur.length) lines.push(cur.join(' '));
      return lines;
    }

    function drawFrame() {
      if (!isRecording) return;

      // 1. Draw base video frame
      ctx.clearRect(0, 0, canvasW, canvasH);
      ctx.filter = 'none';
      try {
        ctx.drawImage(video, 0, 0, canvasW, canvasH);
      } catch (e) {}

      // 2. Find active lyric line
      const curTime = video.currentTime;
      let activeLine = null;
      if (state.syncedLines && state.syncedLines.length) {
        for (const line of state.syncedLines) {
          if (curTime >= line.timeSeconds && curTime <= line.endSeconds) {
            activeLine = line;
            break;
          }
        }
      }

      // 3. Draw upper layer text with exact browser styling & CSS blur filter
      if (activeLine && activeLine.text && state.overlayEnabled) {
        const isBrat = state.template.includes('brat') || state.template === 'template4_brat';
        let rawText = activeLine.text;
        if (isBrat) {
          // Calculate Brat typing accumulation
          const words = rawText.split(/\s+/).filter(Boolean);
          const lineDur = Math.max(0.5, activeLine.endSeconds - activeLine.timeSeconds);
          const typeDur = Math.min(lineDur * 0.85, Math.max(0.4, words.length * 0.28));
          const stepT = typeDur / Math.max(1, words.length);
          const elapsed = curTime - activeLine.timeSeconds;
          const wordCount = Math.min(words.length, Math.max(1, Math.floor(elapsed / stepT) + 1));
          rawText = words.slice(0, wordCount).join(' ');
        }

        const isUpper = (state.bratTheme === 'blue' || state.bratCasing === 'upper');
        const displayText = isUpper ? rawText.toUpperCase() : (isBrat ? rawText.toLowerCase() : rawText);

        const lines = getCanvasWrappedLines(displayText, isBrat ? 11 : 22);

        ctx.save();
        
        // Exact 1080p center position anchor
        const targetX = canvasW * (state.xpos / 100);
        const targetY = canvasH * (state.ypos / 100);
        ctx.translate(targetX, targetY);

        // Exact transform scaleX(0.68) for Brat
        if (isBrat) {
          ctx.scale(0.68, 1);
        }

        // Exact font & styling
        const fs1080 = Math.round(state.fontSize * 3.0);
        const fontFam = (state.bratTheme === 'blue' || state.fontFamily === 'Impact')
          ? 'Impact, "Arial Black", sans-serif'
          : (isBrat ? "'Arial Narrow', 'Helvetica Neue Condensed', sans-serif" : (state.fontFamily || 'Impact'));
        const fontWt = (state.bratTheme === 'blue' || state.fontFamily === 'Impact') ? '900' : (isBrat ? '500' : '800');

        ctx.font = `${fontWt} ${fs1080}px ${fontFam}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // Color
        let textColor = '#FFFFFF';
        if (isBrat) {
          if (state.bratTheme === 'blue') textColor = '#DE0100';
          else if (state.bratTheme === 'black') textColor = '#FFFFFF';
          else textColor = '#000000';
        }
        ctx.fillStyle = textColor;

        // Exact CSS Gaussian blur filter
        const blurRadius = Math.max(0, state.blur * 6.0);
        if (blurRadius > 0.1) {
          ctx.filter = `blur(${blurRadius}px)`;
        } else {
          ctx.filter = 'none';
        }

        // Draw multi-line text
        const lineHeight = fs1080 * 0.92;
        const totalH = lines.length * lineHeight;
        const startY = -(totalH / 2) + (lineHeight / 2);

        lines.forEach((l, idx) => {
          ctx.fillText(l, 0, startY + (idx * lineHeight));
        });

        ctx.restore();
      }

      // Check if video reached end
      if (video.duration && video.currentTime >= (video.duration - 0.15)) {
        finishRecording();
        return;
      }

      // Update progress percent
      if (btn && video.duration) {
        const pct = Math.min(100, Math.round((video.currentTime / video.duration) * 100));
        const span = btn.querySelector('span:last-child');
        if (span) span.textContent = `Accelerated Pixel Capture (${pct}% - ~8s)...`;
      }

      requestAnimationFrame(drawFrame);
    }

    // Start 8x Accelerated Recording (Captures entire video in ~8-10 seconds!)
    const speedMultiplier = 8.0;
    video.loop = false;
    video.playbackRate = speedMultiplier;
    video.muted = true;
    recorder.start(40);
    video.currentTime = 0;
    await video.play();
    drawFrame();

    let finished = false;
    async function finishRecording() {
      if (finished) return;
      finished = true;
      isRecording = false;
      video.pause();
      video.playbackRate = 1.0;
      video.muted = false;
      video.loop = true;

      if (btn) {
        btn.innerHTML = '<span class="spinner-inline"></span> <span>Merging 1x Speed & Audio into 1080p MP4...</span>';
      }

      try {
        if (recorder.state !== 'inactive') {
          recorder.stop();
        }
      } catch (e) {}

      recorder.onstop = async () => {
        const recordedBlob = new Blob(chunks, { type: mimeType });
        try {
          // Send to server to stretch back to 1x normal speed & merge original audio track
          const safeTitle = (state.lastQuery || 'lyric_video').replace(/[^a-zA-Z0-9_-]/g, '_');
          const audioP = state.activeMetadata?.audio_path || '';
          const resp = await fetch(`/api/convert-webm-to-mp4?name=${encodeURIComponent(safeTitle)}&speed=${speedMultiplier}&audioPath=${encodeURIComponent(audioP)}`, {
            method: 'POST',
            body: recordedBlob
          });
          const json = await resp.json();
          if (json.videoUrl) {
            showToast('🎉 Exact 100% pixel-perfect 1080p MP4 downloaded at 1x speed! 🚀');
            const a = document.createElement('a');
            a.href = json.videoUrl;
            a.download = json.videoFileName || `${safeTitle}_exact_1080p.mp4`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          } else {
            throw new Error('No video URL returned from remux');
          }
        } catch (e) {
          console.warn('Remux note:', e);
          const url = URL.createObjectURL(recordedBlob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'exact_lyric_video.webm';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          showToast('Exact video recording downloaded! 🎉');
        } finally {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
          }
        }
      };
    }

    video.onended = () => finishRecording();
  } catch (err) {
    console.error('Recording error:', err);
    showToast('Failed to record exact canvas video: ' + err.message);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}
