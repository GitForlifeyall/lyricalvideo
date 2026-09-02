# 🧠 AGENT BRAIN & REPOSITORY INSTRUCTIONS

> [!CRITICAL]
> **PRIMARY DIRECTIVE: DO NOT CHANGE TEMPLATES UNLESS ORDERED TO.**
> **Never modify, rewrite, remove, or alter existing templates (Template 1, Template 2, Template 3, Brat, YT Hindi Type) or their default visual styles unless the user explicitly requests changes to that specific template.**

---

## 📌 Architecture Overview

This project is a high-performance **Lyric Video Generation Engine** built with Node.js/Express, Python 3.10+, FFmpeg, and Pillow.

```
├── generator.py            # Main Python engine (Audio, Captions, Transliteration, Rendering)
├── indicxlit_runner.py     # AI4Bharat IndicXlit subprocess runner (isolated environment)
├── headers.txt             # Random pool of top header captions for YT Hindi Type
├── emoji_assets/           # Apple-style emoji PNGs for Pillow inline compositing
├── fonts/                  # Custom font TTFs (EB Garamond, Cormorant Garamond, Segoe UI)
├── videos/
│   ├── input/              # Source background videos for cinematic stitching
│   └── output/             # Final generated MP4 videos
├── src/
│   └── index.js            # Express server & SSE real-time streaming endpoint
└── public/
    ├── index.html          # Web Studio UI
    ├── app.js              # Frontend controller & live preview layer
    └── index.css           # UI styling & design system
```

---

## 🎯 Template Invariants

Each template serves a distinct aesthetic and must remain untouched unless explicitly instructed:

| Template Key | Name | Visual Specification | Background & Layout |
|---|---|---|---|
| `template1` | **Template 1** | Impact 62pt, uppercase, white with black border/shadow | Black canvas, portrait 9:16 |
| `template2` | **Template 2** | Montserrat 54pt, yellow accent | Black canvas, portrait 9:16 |
| `template3` | **Template 3** | Arial 48pt, clean subtitle style | Black canvas, landscape 16:9 |
| `template4_brat` | **Brat Minimal** | Arial Narrow 72pt, lowercase, dynamic word accumulation | Solid colors (`#8ACE00`, White, SWEAT Tour Blue, etc.) |
| `yt_hindi_type` | **YT Hindi Type** | **EB Garamond** (centered, natural casing, `\fad(180,180)` fade) + **Georgia Italic** top header with Apple emojis | Centered rectangular video clip from `videos/input/` with black letterbox top & bottom |

---

## 🎼 Lyrics Retrieval & Transliteration Hierarchy

1. **YouTube Manual Subtitles**: Creator-provided subtitles (preferred if available).
2. **Spotify Synced Lyrics**: Queries local API (`http://localhost:8080/?trackid=...&format=lrc`) using `SP_DC`. Must verify `syncType != "UNSYNCED"` and non-zero timestamps.
3. **LRCLIB**: Fast synced lyrics database fallback.
4. **YouTube Auto Captions**: Extracted via `yt-dlp`.
5. **Genius API**: Fallback for romanized song lyrics.

### 🔤 Indic Script Transliteration (Hinglish / Roman Punjabi)
- If lyrics contain Devanagari or Gurmukhi script (`\u0900-\u097F`, `\u0A00-\u0A7F`), the engine automatically transliterates them into Roman script using **AI4Bharat IndicXlit**.
- **No Devanagari script** should appear in the final rendered video for `yt_hindi_type`.

---

## 🎬 Rendering & FFmpeg Rules

1. **Single-Pass Rendering**: Always composite background video + top header + ASS subtitles + audio in one FFmpeg process.
2. **Hardware Acceleration**:
   - `final` mode (`1080x1920`, 30 FPS): Uses GPU encoder (`h264_mf` on Windows / `h264_nvenc`) with `libx264` fallback.
   - `fast` mode (`540x960`, 24 FPS): Uses `libx264 -preset ultrafast -crf 26`.
3. **Header & Emoji Engine**:
   - Top header is rendered via Pillow with **Georgia Italic** font.
   - Inline emojis (`🤌`, `🤍`, `❤️`, `🫶`, etc.) are composited from `emoji_assets/*.png`.
   - Header is centered horizontally `(canvas_width - text_width) / 2` in the top black letterbox above the video clip.
4. **No-Lyrics Guard**:
   - If all lyrics providers return 0 lines, exit cleanly before FFmpeg rendering.
   - Emit: `"No usable lyrics found. Video generation stopped before FFmpeg rendering."`
   - Never output a blank MP4 or corrupt video.

---

## 🛠️ Development & Execution Guidelines

- **Python Virtual Environment**: Always use `.venv310\Scripts\python.exe` (required for PyTorch and IndicXlit).
- **Node Server**: `npm run dev` (starts server on `http://localhost:3000`).
- **Do not modify `.env`** or log API keys/cookies in console logs.
