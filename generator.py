"""
YouTube-Powered 1080p MP4 Lyric-Video Overlay Generator in Python
Supports Portrait (9:16 - 1080x1920) and Landscape (16:9 - 1920x1080) with Customizable Fonts.
Renders high-quality 1080p 30fps H.264 / AAC MP4 video using FFmpeg.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests
import yt_dlp

# Check if JSON progress mode is enabled
JSON_MODE = "--json-progress" in sys.argv

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.youtube.com",
    "Referer": "https://www.youtube.com/",
}


def emit_progress(step: str, percent: int, message: str, details: Optional[Dict[str, Any]] = None):
    """Emit progress update to stdout in JSON format or human-readable format."""
    payload = {
        "type": "progress",
        "step": step,
        "percent": percent,
        "message": message,
        "details": details or {}
    }
    if JSON_MODE:
        print(f"__JSON_PROGRESS__{json.dumps(payload)}", flush=True)
    else:
        print(f"[{percent}% - {step}] {message}", flush=True)


def fetch_direct_youtube_subtitles(video_info: Dict[str, Any], target_lang: str = "auto") -> Tuple[List[Tuple[float, float, str]], str]:
    """
    Directly fetches and parses YouTube timedtext JSON3/VTT subtitles via HTTP GET.
    Prioritizes original native audio captions (-orig) and manual tracks when in auto mode.
    """
    subtitles_dict = video_info.get("subtitles", {})
    auto_captions_dict = video_info.get("automatic_captions", {})
    lang_pref = (target_lang or "auto").lower().strip()

    candidate_langs = []

    if lang_pref == "auto":
        # 1. First priority: Any creator manual subtitles
        for k, v in subtitles_dict.items():
            if k != "live_chat":
                candidate_langs.append(("manual", k, v))

        # 2. Second priority: Original spoken audio auto-caption (e.g. 'en-orig', 'pa-orig')
        for k, v in auto_captions_dict.items():
            if k.endswith("-orig") or "orig" in k:
                candidate_langs.append(("auto_orig", k, v))

        # 3. Third priority: English auto-caption
        for k, v in auto_captions_dict.items():
            if k.startswith("en"):
                candidate_langs.append(("auto_en", k, v))

        # 4. Fourth priority: Any first available auto-caption
        for k, v in auto_captions_dict.items():
            if k != "live_chat" and k not in [c[1] for c in candidate_langs]:
                candidate_langs.append(("auto_fallback", k, v))

    else:
        # User specified a specific language code (e.g. 'pa', 'en', 'es', 'hi', 'ja')
        # Check aliases: pa / punjabi / panjabi
        aliases = [lang_pref]
        if lang_pref in ["pa", "punjabi", "panjabi"]:
            aliases = ["pa", "punjabi", "panjabi", "pam"]
        elif lang_pref in ["hi", "hindi"]:
            aliases = ["hi", "hindi"]
        elif lang_pref in ["es", "spanish"]:
            aliases = ["es", "spa", "spanish"]

        # 1. Match in manual subtitles
        for k, v in subtitles_dict.items():
            if k != "live_chat" and any(a in k.lower() for a in aliases):
                candidate_langs.append(("manual_target", k, v))

        # 2. Match in auto-captions
        for k, v in auto_captions_dict.items():
            if k != "live_chat" and any(a in k.lower() for a in aliases):
                candidate_langs.append(("auto_target", k, v))

        # DO NOT fallback to hi-orig or arbitrary languages when user asked for a specific language!

    for kind, lang_key, formats in candidate_langs:
        json3_fmt = next((f for f in formats if f.get("ext") == "json3"), None)
        vtt_fmt = next((f for f in formats if f.get("ext") == "vtt"), None)
        chosen_fmt = json3_fmt or vtt_fmt or (formats[0] if formats else None)

        if not chosen_fmt or not chosen_fmt.get("url"):
            continue

        try:
            url = chosen_fmt["url"]
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
            if resp.status_code == 200 and resp.text.strip():
                if chosen_fmt.get("ext") == "json3" or "json3" in url:
                    data = resp.json()
                    cues = parse_json3_timedtext(data)
                    if cues:
                        print(f"[Subtitles] Selected '{lang_key}' ({kind}) with {len(cues)} lines")
                        return cues, lang_key
                else:
                    cues = parse_vtt_text(resp.text)
                    if cues:
                        print(f"[Subtitles] Selected VTT '{lang_key}' ({kind}) with {len(cues)} lines")
                        return cues, lang_key
        except Exception as e:
            print(f"[Warning] Failed to fetch subtitles for {lang_key}: {e}")

    return [], "none"


def parse_json3_timedtext(data: Dict[str, Any]) -> List[Tuple[float, float, str]]:
    """Parse YouTube JSON3 timedtext structure into list of (start_sec, end_sec, text)."""
    events = data.get("events", [])
    cues: List[Tuple[float, float, str]] = []

    for ev in events:
        t_start = ev.get("tStartMs", 0) / 1000.0
        t_dur = ev.get("dDurationMs", 0) / 1000.0
        segs = ev.get("segs", [])
        
        raw_text = "".join([s.get("utf8", "") for s in segs if s.get("utf8")])
        clean_text = raw_text.replace("\n", " ").strip()
        clean_text = clean_text.replace("♪", "").replace("♫", "").strip()
        clean_text = " ".join(clean_text.split())

        if clean_text and clean_text != "\n":
            dur = t_dur if t_dur > 0 else 2.5
            end_sec = max(t_start + 1.5, t_start + dur)
            cues.append((t_start, end_sec, clean_text))

    deduped: List[Tuple[float, float, str]] = []
    for c in cues:
        if deduped and deduped[-1][2].lower() == c[2].lower():
            deduped[-1] = (deduped[-1][0], max(deduped[-1][1], c[1]), deduped[-1][2])
        else:
            deduped.append(c)

    return deduped


def parse_vtt_text(content: str) -> List[Tuple[float, float, str]]:
    """Parse WebVTT content into list of (start_sec, end_sec, text)."""
    cue_pattern = re.compile(
        r"(?:(\d{2}:)?(\d{2}):(\d{2})\.(\d{3}))\s*-->\s*(?:(\d{2}:)?(\d{2}):(\d{2})\.(\d{3})).*?\n((?:(?!\n\n|\r\n\r\n|\d{2}:).)*)",
        re.DOTALL
    )
    cues = []
    for match in cue_pattern.finditer(content):
        h1 = int(match.group(1).replace(":", "")) if match.group(1) else 0
        m1 = int(match.group(2))
        s1 = int(match.group(3))
        ms1 = int(match.group(4))
        start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0

        h2 = int(match.group(5).replace(":", "")) if match.group(5) else 0
        m2 = int(match.group(6))
        s2 = int(match.group(7))
        ms2 = int(match.group(8))
        end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

        clean_text = re.sub(r"<[^>]+>", "", match.group(9).strip())
        clean_text = " ".join(clean_text.split())
        clean_text = clean_text.replace("♪", "").replace("♫", "").strip()

        if clean_text:
            if end_sec <= start_sec:
                end_sec = start_sec + 2.5
            cues.append((start_sec, end_sec, clean_text))

    deduped: List[Tuple[float, float, str]] = []
    for c in cues:
        if deduped and deduped[-1][2].lower() == c[2].lower():
            deduped[-1] = (deduped[-1][0], max(deduped[-1][1], c[1]), deduped[-1][2])
        else:
            deduped.append(c)

    return deduped


GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY", "ypkO8jfBDy2rrh0H_LUff5Adg2XIRrHx5GA3K73ENrTGdG2V8_I4WxIWjDp8bps8")


def clean_genius_lyrics_text(raw: str) -> List[str]:
    """Clean genius lyrics annotations and embedded metadata."""
    lines = []
    for line in raw.splitlines():
        line = re.sub(r'^\d+Embed$', '', line)
        line = re.sub(r'Embed$', '', line)
        line = re.sub(r'\[.*?\]', '', line)
        line = re.sub(r'\(.*?\)', '', line)
        line = line.strip()
        if line and len(line) > 1:
            lines.append(line)
    return lines


def fetch_genius_lyrics_fallback(
    song_title: str,
    artist_name: str = "",
    duration: float = 180.0
) -> Tuple[List[Tuple[float, float, str]], str]:
    """
    Fallback lyrics retriever using the Genius API when YouTube has no captions or for non-English songs.
    """
    try:
        import lyricsgenius
    except ImportError:
        return [], "none"

    if not GENIUS_API_KEY:
        return [], "none"

    emit_progress("genius_fallback", 45, f"Querying Genius API for '{song_title}' lyrics...")

    # Clean title to maximize Genius hit rate
    clean_q = re.sub(r'\(.*?\)|\[.*?\]|official|music|video|audio|lyrics|latest|punjabi|hindi|songs|remix|hd|4k|\d{4}', '', song_title, flags=re.I).strip()
    clean_q = re.sub(r'[\|\-_]', ' ', clean_q).strip()

    try:
        genius = lyricsgenius.Genius(GENIUS_API_KEY)
        genius.verbose = False
        genius.remove_section_headers = True

        song = None
        if artist_name and artist_name != "YouTube":
            clean_artist = re.sub(r'VEVO|Official|Topic|\(.*?\)', '', artist_name, flags=re.I).strip()
            song = genius.search_song(clean_q, clean_artist)

        if not song:
            song = genius.search_song(clean_q)

        if not song and song_title != clean_q:
            song = genius.search_song(song_title)

        if song and song.lyrics:
            lines = clean_genius_lyrics_text(song.lyrics)
            if lines:
                print(f"[Genius] Found {len(lines)} lines for '{song.title}' by '{song.artist}'")
                
                # Distribute lines across track duration
                intro_lead = 5.0
                outro_lead = 4.0
                usable_time = max(10.0, (duration or 180.0) - intro_lead - outro_lead)
                step = usable_time / len(lines)

                cues = []
                for i, text in enumerate(lines):
                    t_start = intro_lead + (i * step)
                    dur = min(step * 0.95, 4.5)
                    t_end = t_start + max(1.5, dur)
                    cues.append((round(t_start, 2), round(t_end, 2), text))

                return cues, "genius"
    except Exception as e:
        print(f"[Genius Fallback Warning] {e}")

    return [], "none"


# Cache detected encoder
_CACHED_ENCODER = None

def detect_fastest_h264_encoder() -> Tuple[str, List[str]]:
    """Automatically detect if GPU hardware acceleration (NVENC, AMF, MF) is available."""
    global _CACHED_ENCODER
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER

    test_candidates = [
        ("h264_nvenc", ["-preset", "p1", "-cq", "19"]),
        ("h264_amf", ["-quality", "speed", "-rc", "cqp", "-qp_i", "19", "-qp_p", "19"]),
        ("h264_mf", ["-rate_control", "cbr", "-b:v", "3M"]),
        ("libx264", ["-preset", "ultrafast", "-tune", "fastdecode", "-crf", "18"]),
    ]

    for enc_name, extra_flags in test_candidates:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=0.1",
            "-c:v", enc_name
        ] + extra_flags + ["-f", "null", "-"]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                _CACHED_ENCODER = (enc_name, extra_flags)
                return _CACHED_ENCODER
        except Exception:
            pass

    _CACHED_ENCODER = ("libx264", ["-preset", "ultrafast", "-tune", "fastdecode", "-crf", "18"])
    return _CACHED_ENCODER


def download_youtube_audio(
    query_or_url: str,
    output_audio_path: str = "temp_audio.mp3",
    target_lang: str = "auto"
) -> Dict[str, Any]:
    """Download audio as MP3 and probe video subtitle metadata in requested language with parallel streams."""
    emit_progress("ytdlp_start", 15, f"Searching YouTube for '{query_or_url}' (Language: {target_lang})...")
    audio_basename = str(Path(output_audio_path).with_suffix(""))

    if os.path.exists(output_audio_path):
        try:
            os.remove(output_audio_path)
        except OSError:
            pass

    is_direct_url = (
        query_or_url.startswith("http://") or 
        query_or_url.startswith("https://") or 
        "youtube.com" in query_or_url or 
        "youtu.be" in query_or_url
    )
    search_target = query_or_url if is_direct_url else f"ytsearch1:{query_or_url}"

    ydl_opts = {
        "format": "ba[ext=m4a]/ba[ext=mp3]/140/bestaudio/best",
        "outtmpl": f"{audio_basename}.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "concurrent_fragment_downloads": 8,
        "buffersize": 1024 * 64,
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "android", "web", "ios"]
            }
        },
        "http_headers": BROWSER_HEADERS,
        "retries": 3,
        "fragment_retries": 3,
    }

    emit_progress("ytdlp_downloading", 35, f"Extracting audio track and fetching captions in '{target_lang}'...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=True)
        video_info = info["entries"][0] if "entries" in info and len(info["entries"]) > 0 else info

    title = video_info.get("title", query_or_url)
    duration = video_info.get("duration") or 0.0
    uploader = video_info.get("uploader") or video_info.get("channel") or "YouTube"

    expected_audio = f"{audio_basename}.mp3"
    if not os.path.exists(expected_audio) and os.path.exists(output_audio_path):
        expected_audio = output_audio_path

    cues, matched_lang = fetch_direct_youtube_subtitles(video_info, target_lang=target_lang)

    # Genius API Fallback for songs without subtitles or non-English tracks
    if not cues:
        emit_progress("genius_fallback", 50, f"No native YouTube captions. Fetching verified lyrics from Genius API...")
        genius_cues, genius_lang = fetch_genius_lyrics_fallback(title, uploader, duration)
        if genius_cues:
            cues = genius_cues
            matched_lang = genius_lang

    emit_progress("ytdlp_done", 55, f"Audio & lyrics ready: '{title}' ({len(cues)} lines, source: {matched_lang})", {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
        "matched_lang": matched_lang,
        "cues_count": len(cues)
    })

    return {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
        "matched_lang": matched_lang,
        "cues": cues
    }


def seconds_to_ass_timestamp(total_seconds: float) -> str:
    total_seconds = max(0.0, total_seconds)
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    cs = min(99, int(round((total_seconds - int(total_seconds)) * 100)))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def seconds_to_lrc_timestamp(total_seconds: float) -> str:
    total_seconds = max(0.0, total_seconds)
    m = int(total_seconds // 60)
    s = int(total_seconds % 60)
    cs = min(99, int(round((total_seconds - int(total_seconds)) * 100)))
    return f"{m:02d}:{s:02d}.{cs:02d}"


TEMPLATES = {
    "template1": {
        "id": "template1",
        "name": "Template 1",
        "aspect_ratio": "portrait",
        "font_name": "Impact",
        "font_size": 62,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": -1,
        "outline_width": 4,
        "shadow_depth": 3,
        "margin_v": 440,
    },
    "template2": {
        "id": "template2",
        "name": "Template 2",
        "aspect_ratio": "portrait",
        "font_name": "Montserrat",
        "font_size": 54,
        "primary_color": "&H0000FFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": -1,
        "outline_width": 3,
        "shadow_depth": 2,
        "margin_v": 420,
    },
    "template3": {
        "id": "template3",
        "name": "Template 3",
        "aspect_ratio": "landscape",
        "font_name": "Arial",
        "font_size": 48,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
        "bold": -1,
        "outline_width": 3,
        "shadow_depth": 2,
        "margin_v": 80,
    },
    "brat": {
        "id": "brat",
        "name": "brat",
        "aspect_ratio": "portrait",
        "font_name": "Arial",
        "font_size": 58,
        "primary_color": "&H00000000",
        "outline_color": "&H0000CE8A",
        "back_color": "&H0000CE8A",
        "border_style": 3,
        "bold": 0,
        "outline_width": 14,
        "shadow_depth": 0,
        "margin_v": 450,
        "lowercase": True,
    }
}


def build_ass_and_lrc_content(
    cues: List[Tuple[float, float, str]],
    output_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    audio_duration: float = 180.0,
    aspect_ratio: str = "portrait",
    font_name: str = "Impact",
    font_size: Optional[int] = None,
    template_key: Optional[str] = "template1"
) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Convert cues into ASS subtitle format configured with Template presets (1, 2, 3, brat)
    or custom typography.
    """
    tpl = TEMPLATES.get((template_key or "").lower(), TEMPLATES["template1"])
    effective_aspect = aspect_ratio or tpl["aspect_ratio"]
    effective_font = font_name if font_name and font_name != "Impact" else tpl["font_name"]

    is_portrait = (effective_aspect.lower() == "portrait" or effective_aspect == "9:16")
    emit_progress("ass_start", 60, f"Step 2: Applying {tpl['name']} ({'Portrait 9:16' if is_portrait else 'Landscape 16:9'})...")

    if not cues:
        cues = [
            (2.0, max(6.0, audio_duration - 2.0), "[Music Playing - Native YouTube Audio]")
        ]

    # Configure canvas & typography parameters
    if is_portrait:
        res_x = 1080
        res_y = 1920
        margin_l = 70
        margin_r = 70
        margin_v = tpl.get("margin_v", 440)
        alignment = 2   # Bottom-center
        outline_width = tpl.get("outline_width", 4)
        shadow_depth = tpl.get("shadow_depth", 3)
    else:
        res_x = 1920
        res_y = 1080
        margin_l = 60
        margin_r = 60
        margin_v = tpl.get("margin_v", 80)
        alignment = 2
        outline_width = tpl.get("outline_width", 3)
        shadow_depth = tpl.get("shadow_depth", 2)

    actual_font_size = font_size if font_size and font_size > 0 else tpl.get("font_size", 54)
    primary_color = tpl.get("primary_color", "&H00FFFFFF")
    outline_color = tpl.get("outline_color", "&H00000000")
    back_color = tpl.get("back_color", "&H80000000")
    bold_val = tpl.get("bold", -1)
    border_style = tpl.get("border_style", 1)
    is_lowercase = tpl.get("lowercase", False)

    ass_header = f"""[Script Info]
; Script generated by YouTube Lyric-Video Overlay Generator
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{effective_font},{actual_font_size},{primary_color},&H000000FF,{outline_color},{back_color},{bold_val},0,0,0,100,100,0,0,{border_style},{outline_width},{shadow_depth},{alignment},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    structured_lines = []
    raw_lrc_lines = []

    for i, (start_sec, end_sec, text) in enumerate(cues):
        adjusted_start = max(0.0, start_sec + offset_seconds)
        adjusted_end = max(adjusted_start + 1.0, end_sec + offset_seconds)

        clean_text = text.replace("{", "\\{").replace("}", "\\}")
        if is_lowercase:
            clean_text = clean_text.lower()

        dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(adjusted_start)},{seconds_to_ass_timestamp(adjusted_end)},Default,,0,0,0,,{clean_text}")

        ts_formatted = seconds_to_lrc_timestamp(adjusted_start)
        structured_lines.append({
            "index": i,
            "timestamp": ts_formatted,
            "timeSeconds": adjusted_start,
            "endSeconds": adjusted_end,
            "text": clean_text
        })
        raw_lrc_lines.append(f"[{ts_formatted}] {clean_text}")

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogues) + "\n")

    raw_lrc = "\n".join(raw_lrc_lines)
    emit_progress("ass_done", 70, f"Step 2: Applied {tpl['name']} ({len(dialogues)} events, {res_x}x{res_y}).")
    return output_ass_path, structured_lines, raw_lrc


def get_audio_duration(audio_path: str) -> float:
    """Use ffprobe to get exact audio duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    try:
        probe = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(probe.stdout.strip())
    except Exception:
        return 180.0


def render_lyric_video_ffmpeg(
    audio_path: str,
    ass_path: str,
    output_path: str = "output_lyric_video.mp4",
    duration: Optional[float] = None,
    aspect_ratio: str = "portrait"
) -> str:
    """Step 3: Run FFmpeg to render ASS subtitles over Portrait or Landscape MP4 video with GPU Acceleration."""
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    is_portrait = (aspect_ratio.lower() == "portrait" or aspect_ratio == "9:16")
    res_str = "1080x1920" if is_portrait else "1920x1080"

    encoder_name, encoder_flags = detect_fastest_h264_encoder()
    emit_progress("ffmpeg_start", 75, f"Step 3: Rendering {res_str} 30fps MP4 video using {encoder_name} ({duration:.1f}s)...")
    
    normalized_ass = ass_path.replace("\\", "/")
    if ":" in normalized_ass:
        normalized_ass = normalized_ass.replace(":", "\\:")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-f", "lavfi", "-i", f"color=c=black:s={res_str}:r=30:d={duration:.2f}",
        "-i", audio_path,
        "-vf", f"ass={normalized_ass}",
        "-c:v", encoder_name,
    ] + encoder_flags + [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]

    emit_progress("ffmpeg_rendering", 85, f"Step 3: Hardware encoding {res_str} video with {encoder_name}...")
    subprocess.run(ffmpeg_cmd, check=True)
    emit_progress("ffmpeg_done", 95, f"Step 3: Video successfully rendered to '{output_path}'.")
    return output_path


def generate_lyric_video(
    song_query: str,
    output_path: str = "output_lyric_video.mp4",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    aspect_ratio: str = "portrait",
    font_name: str = "Impact",
    font_size: Optional[int] = None,
    lang: str = "auto",
    template: str = "template1"
) -> Dict[str, Any]:
    """Main generator pipeline supporting Templates (1, 2, 3), Portrait/Landscape, and Subtitle Language."""
    tpl = TEMPLATES.get((template or "").lower(), TEMPLATES["template1"])
    effective_aspect = aspect_ratio or tpl["aspect_ratio"]
    effective_font = font_name if font_name and font_name != "Impact" else tpl["font_name"]

    emit_progress("init", 5, f"Initiating Generator with {tpl['name']} (Lang: {lang})...")

    yt_data = download_youtube_audio(
        query_or_url=song_query,
        output_audio_path=temp_audio_path,
        target_lang=lang
    )
    audio_path = yt_data["audio_path"]
    duration = yt_data["duration"] or get_audio_duration(audio_path)

    ass_path, structured_lines, raw_lrc = build_ass_and_lrc_content(
        cues=yt_data["cues"],
        output_ass_path=temp_ass_path,
        offset_seconds=offset_seconds,
        audio_duration=duration,
        aspect_ratio=effective_aspect,
        font_name=effective_font,
        font_size=font_size,
        template_key=template
    )

    render_lyric_video_ffmpeg(
        audio_path=audio_path,
        ass_path=ass_path,
        output_path=output_path,
        duration=duration,
        aspect_ratio=effective_aspect
    )

    final_result = {
        "status": "success",
        "query": song_query,
        "output_path": output_path,
        "audio_path": audio_path,
        "ass_path": ass_path,
        "track_name": yt_data.get("title"),
        "artist_name": yt_data.get("uploader"),
        "duration": duration,
        "aspect_ratio": effective_aspect,
        "font_name": effective_font,
        "template": template,
        "language": yt_data.get("matched_lang", lang),
        "totalLines": len(structured_lines),
        "syncedLines": structured_lines,
        "rawLrc": raw_lrc
    }

    emit_progress("completed", 100, f"🎉 1080p MP4 ready using {tpl['name']}!", final_result)
    return final_result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if len(args) > 0 else "Rick Astley - Never Gonna Give You Up"
    out = args[1] if len(args) > 1 else "output_lyric_video.mp4"
    
    offset = 0.0
    aspect = None
    font = None
    size = None
    lang = "auto"
    template = "template1"

    for a in sys.argv[1:]:
        if a.startswith("--offset="):
            try:
                offset = float(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--aspect="):
            aspect = a.split("=")[1].strip()
        elif a.startswith("--font="):
            font = a.split("=")[1].strip()
        elif a.startswith("--fontsize="):
            try:
                size = int(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--lang="):
            lang = a.split("=")[1].strip()
        elif a.startswith("--template="):
            template = a.split("=")[1].strip()

    res = generate_lyric_video(
        song_query=query,
        output_path=out,
        offset_seconds=offset,
        aspect_ratio=aspect or "portrait",
        font_name=font or "Impact",
        font_size=size,
        lang=lang,
        template=template
    )
    if JSON_MODE:
        print(f"__FINAL_RESULT__{json.dumps(res)}", flush=True)
