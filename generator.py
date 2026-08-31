"""
YouTube-Powered 1080p Transparent Lyric-Video Overlay Generator in Python
Uses yt-dlp to extract high-quality audio and fetches direct YouTube timedtext subtitles
without triggering HTTP 429 rate-limiting.
Renders a 1080p 30fps VP9 yuva420p transparent video overlay using FFmpeg.
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


def fetch_direct_youtube_subtitles(video_info: Dict[str, Any]) -> List[Tuple[float, float, str]]:
    """
    Directly fetches and parses YouTube timedtext JSON3/VTT subtitles via HTTP GET
    to prevent yt-dlp's internal subtitle downloader from triggering HTTP 429 rate limits.
    """
    subtitles_dict = video_info.get("subtitles", {})
    auto_captions_dict = video_info.get("automatic_captions", {})

    # Priority order for language keys: manual English, auto English, then any available
    candidate_langs = []
    for k in subtitles_dict.keys():
        if k.startswith("en") and k != "live_chat":
            candidate_langs.append(("manual", k, subtitles_dict[k]))
    for k in auto_captions_dict.keys():
        if k.startswith("en") and k != "live_chat":
            candidate_langs.append(("auto", k, auto_captions_dict[k]))
    for k, v in list(subtitles_dict.items()) + list(auto_captions_dict.items()):
        if k != "live_chat" and k not in [c[1] for c in candidate_langs]:
            candidate_langs.append(("fallback", k, v))

    for kind, lang_key, formats in candidate_langs:
        # Prefer json3 format for precision, then vtt
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
                        print(f"[Subtitles] Successfully fetched {len(cues)} cues from YouTube ({kind} - {lang_key})")
                        return cues
                else:
                    cues = parse_vtt_text(resp.text)
                    if cues:
                        print(f"[Subtitles] Successfully parsed {len(cues)} VTT cues from YouTube ({kind} - {lang_key})")
                        return cues
        except Exception as e:
            print(f"[Warning] Failed to fetch subtitles for {lang_key}: {e}")

    return []


def parse_json3_timedtext(data: Dict[str, Any]) -> List[Tuple[float, float, str]]:
    """Parse YouTube JSON3 timedtext structure into list of (start_sec, end_sec, text)."""
    events = data.get("events", [])
    cues: List[Tuple[float, float, str]] = []

    for ev in events:
        t_start = ev.get("tStartMs", 0) / 1000.0
        t_dur = ev.get("dDurationMs", 0) / 1000.0
        segs = ev.get("segs", [])
        
        # Combine word segments
        raw_text = "".join([s.get("utf8", "") for s in segs if s.get("utf8")])
        clean_text = raw_text.replace("\n", " ").strip()
        clean_text = clean_text.replace("♪", "").replace("♫", "").strip()
        clean_text = " ".join(clean_text.split())

        if clean_text and clean_text != "\n":
            end_sec = max(t_start + 1.0, t_start + t_dur)
            cues.append((t_start, end_sec, clean_text))

    # Deduplicate consecutive identical lines
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
            cues.append((start_sec, end_sec, clean_text))

    deduped: List[Tuple[float, float, str]] = []
    for c in cues:
        if deduped and deduped[-1][2].lower() == c[2].lower():
            deduped[-1] = (deduped[-1][0], max(deduped[-1][1], c[1]), deduped[-1][2])
        else:
            deduped.append(c)

    return deduped


def download_youtube_audio(query_or_url: str, output_audio_path: str = "temp_audio.mp3") -> Dict[str, Any]:
    """
    Download audio as MP3 and probe video subtitle metadata without triggering yt-dlp 429 errors.
    """
    emit_progress("ytdlp_start", 15, f"Searching YouTube for '{query_or_url}'...")
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
        "format": "bestaudio/best",
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
        "writesubtitles": False,       # Handled directly via HTTP GET to avoid 429
        "writeautomaticsub": False,
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "android", "web", "ios"]
            }
        },
        "http_headers": BROWSER_HEADERS,
        "retries": 3,
        "fragment_retries": 3,
    }

    emit_progress("ytdlp_downloading", 35, "Extracting audio track and fetching captions...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=True)
        video_info = info["entries"][0] if "entries" in info and len(info["entries"]) > 0 else info

    title = video_info.get("title", query_or_url)
    duration = video_info.get("duration") or 0.0
    uploader = video_info.get("uploader") or video_info.get("channel") or "YouTube"

    expected_audio = f"{audio_basename}.mp3"
    if not os.path.exists(expected_audio) and os.path.exists(output_audio_path):
        expected_audio = output_audio_path

    # Fetch subtitles directly via HTTP
    cues = fetch_direct_youtube_subtitles(video_info)

    emit_progress("ytdlp_done", 55, f"Audio & captions ready: '{title}' ({len(cues)} lines)", {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
        "cues_count": len(cues)
    })

    return {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
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


def build_ass_and_lrc_content(
    cues: List[Tuple[float, float, str]],
    output_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    audio_duration: float = 180.0
) -> Tuple[str, List[Dict[str, Any]], str]:
    """Convert cues into 1080p ASS subtitle format and structured JSON timestamps."""
    emit_progress("ass_start", 60, "Step 2: Formatting captions into 1080p ASS subtitle canvas...")

    if not cues:
        cues = [
            (2.0, max(6.0, audio_duration - 2.0), "[Music Playing - Native YouTube Audio]")
        ]

    ass_header = """[Script Info]
; Script generated by YouTube Lyric-Video Overlay Generator
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,60,1

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
        dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(adjusted_start)},{seconds_to_ass_timestamp(adjusted_end)},Default,,0,0,0,,{clean_text}")

        ts_formatted = seconds_to_lrc_timestamp(adjusted_start)
        structured_lines.append({
            "index": i,
            "timestamp": ts_formatted,
            "timeSeconds": adjusted_start,
            "endSeconds": adjusted_end,
            "text": text
        })
        raw_lrc_lines.append(f"[{ts_formatted}] {text}")

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogues) + "\n")

    raw_lrc = "\n".join(raw_lrc_lines)
    emit_progress("ass_done", 70, f"Step 2: Generated styled 1080p ASS with {len(dialogues)} subtitle events.")
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
    duration: Optional[float] = None
) -> str:
    """Step 3: Run FFmpeg to render ASS subtitles over 1080p 30fps MP4 video with H.264 video and AAC audio."""
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    emit_progress("ffmpeg_start", 75, f"Step 3: Rendering 1080p 30fps MP4 video ({duration:.1f}s)...")
    
    normalized_ass = ass_path.replace("\\", "/")
    if ":" in normalized_ass:
        normalized_ass = normalized_ass.replace(":", "\\:")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:r=30:d={duration:.2f}",
        "-i", audio_path,
        "-vf", f"ass={normalized_ass}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]

    emit_progress("ffmpeg_rendering", 85, "Step 3: Encoding 1080p H.264 video with AAC audio...")
    subprocess.run(ffmpeg_cmd, check=True)
    emit_progress("ffmpeg_done", 95, f"Step 3: Video successfully rendered to '{output_path}'.")
    return output_path


def generate_lyric_video(
    song_query: str,
    output_path: str = "output_lyric_video.mp4",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0
) -> Dict[str, Any]:
    """Main generator pipeline."""
    emit_progress("init", 5, f"Initiating YouTube Audio & Subtitle Generator for '{song_query}'...")

    yt_data = download_youtube_audio(query_or_url=song_query, output_audio_path=temp_audio_path)
    audio_path = yt_data["audio_path"]
    duration = yt_data["duration"] or get_audio_duration(audio_path)

    ass_path, structured_lines, raw_lrc = build_ass_and_lrc_content(
        cues=yt_data["cues"],
        output_ass_path=temp_ass_path,
        offset_seconds=offset_seconds,
        audio_duration=duration
    )

    render_lyric_video_ffmpeg(audio_path, ass_path, output_path, duration)

    final_result = {
        "status": "success",
        "query": song_query,
        "output_path": output_path,
        "audio_path": audio_path,
        "ass_path": ass_path,
        "track_name": yt_data.get("title"),
        "artist_name": yt_data.get("uploader"),
        "duration": duration,
        "totalLines": len(structured_lines),
        "syncedLines": structured_lines,
        "rawLrc": raw_lrc
    }

    emit_progress("completed", 100, "🎉 1080p MP4 Lyric Video ready!", final_result)
    return final_result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if len(args) > 0 else "Rick Astley - Never Gonna Give You Up"
    out = args[1] if len(args) > 1 else "output_lyric_video.mp4"
    
    offset = 0.0
    for a in sys.argv[1:]:
        if a.startswith("--offset="):
            try:
                offset = float(a.split("=")[1])
            except ValueError:
                pass

    res = generate_lyric_video(query, out, offset_seconds=offset)
    if JSON_MODE:
        print(f"__FINAL_RESULT__{json.dumps(res)}", flush=True)
