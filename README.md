# 🎬 LyricalVideo: Automated 1080p MP4 Lyric Video Generator

A full-stack, hardware-accelerated lyric video generator built with Node.js/Express, Python 3.10+, FFmpeg, and Pillow.

> [!CRITICAL]
> **AGENT DIRECTIVE**: **DO NOT CHANGE TEMPLATES UNLESS ORDERED TO.**
> See [AGENTS.md](file:///c:/Users/khann/OneDrive/Documents/Projects/New%20lyrics%202/AGENTS.md) for full agent architecture and invariant rules.

---

## 🚀 Getting Started

### 1. Install Node Dependencies
```bash
npm install
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Run the Development Server
```bash
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## 🎨 Supported Templates

| Template | Aesthetic | Canvas & Layout |
|---|---|---|
| **Template 1** | Bold Impact (White with black shadow) | Portrait 9:16 |
| **Template 2** | Montserrat (Yellow accents) | Portrait 9:16 |
| **Template 3** | Arial Subtitle | Landscape 16:9 |
| **Brat Minimal** | Charli XCX Aesthetic (Dynamic accumulation) | Portrait 9:16, customizable swatches |
| **YT Hindi Type** | Cinematic EB Garamond lyrics + Georgia Italic header with Apple emojis | Centered rectangular video from `videos/input/` with black letterbox top & bottom |

---

## 📁 Folder Structure

- `videos/input/`: Place your background video clips here for cinematic stitching.
- `videos/output/`: Generated final MP4 videos are saved here.
- `headers.txt`: Add custom top header lines for the *YT Hindi Type* template (one per line).
- `emoji_assets/`: Apple-style emoji PNGs for inline header compositing.
- `fonts/`: Local font files (`EB Garamond`, `Cormorant Garamond`, `Segoe UI Emoji`).

---

## 🛠️ Tech Stack & Dependencies

- **Backend**: Express.js (Node.js ES Modules) + SSE streaming
- **Engine**: Python 3.10+ with `yt-dlp`, `requests`, `Pillow`, and `AI4Bharat IndicXlit`
- **Video Renderer**: FFmpeg with GPU hardware acceleration (`h264_mf` / `h264_nvenc`)
- **Subtitle Engine**: `libass` with custom font mappings
