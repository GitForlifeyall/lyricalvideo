"""
YouTube-Powered 1080p Transparent Lyric-Video Overlay Generator in Python
Uses yt-dlp to extract both audio (MP3) and synchronized subtitles/captions (VTT) directly from YouTube.
Renders a 1080p 30fps VP9 yuva420p transparent video overlay using FFmpeg.
"""

import os
import re
import sys
import glob
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import yt_dlp

# Check if JSON progress mode is enabled
JSON_MODE = "--json-progress" in sys.argv


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


def download_youtube_audio_and_subtitles(
    query_or_url: str,
    output_audio_path: str = "temp_audio.mp3",
    output_vtt_prefix: str = "temp_subs"
) -> Dict[str, Any]:
    """
    Use yt-dlp to extract the audio track as MP3 and the best synchronized subtitle/caption stream.
    """
    emit_progress("ytdlp_start", 15, f"Searching YouTube for '{query_or_url}'...")
    audio_basename = str(Path(output_audio_path).with_suffix(""))

    # Clean previous temp files
    for old_file in glob.glob(f"{output_vtt_prefix}*") + [output_audio_path]:
        try:
            os.remove(old_file)
        except OSError:
            pass

    is_direct_url = (
        query_or_url.startswith("http://") or 
        query_or_url.startswith("https://") or 
        "youtube.com" in query_or_url or 
        "youtu.be" in query_or_url
    )
    search_target = query_or_url if is_direct_url else f"ytsearch1:{query_or_url}"

    probe_opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "android", "web", "ios"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }

    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(search_target, download=False)
        video_info = info["entries"][0] if "entries" in info and len(info["entries"]) > 0 else info

    video_url = video_info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_info.get('id')}"
    title = video_info.get("title", query_or_url)
    duration = video_info.get("duration") or 0.0
    uploader = video_info.get("uploader") or video_info.get("channel") or "YouTube"

    # Identify best subtitle language key to prevent downloading dozens of auto-translated languages
    subtitles_dict = video_info.get("subtitles", {})
    auto_captions_dict = video_info.get("automatic_captions", {})
    
    target_lang = None
    # 1. Check manual creator subtitles for English
    for lang in subtitles_dict.keys():
        if lang.startswith("en") and lang != "live_chat":
            target_lang = lang
            break
    # 2. Check auto-captions for English
    if not target_lang:
        for lang in auto_captions_dict.keys():
            if lang.startswith("en") and lang != "live_chat":
                target_lang = lang
                break
    # 3. Check any available language
    if not target_lang:
        available_langs = [l for l in list(subtitles_dict.keys()) + list(auto_captions_dict.keys()) if l != "live_chat"]
        if available_langs:
            target_lang = available_langs[0]

    emit_progress("ytdlp_downloading", 35, f"Downloading audio and captions ({target_lang or 'auto'})...")

    ydl_download_opts = {
        "format": "bestaudio/best",
        "outtmpl": {
            "default": f"{audio_basename}.%(ext)s",
            "subtitle": f"{output_vtt_prefix}.%(ext)s",
        },
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
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "android", "web", "ios"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "retries": 3,
        "fragment_retries": 3,
    }

    if target_lang:
        ydl_download_opts["writesubtitles"] = True
        ydl_download_opts["writeautomaticsub"] = True
        ydl_download_opts["subtitlesformat"] = "vtt"
        ydl_download_opts["subtitleslangs"] = [target_lang]

    with yt_dlp.YoutubeDL(ydl_download_opts) as ydl:
        ydl.download([video_url])

    expected_audio = f"{audio_basename}.mp3"
    if not os.path.exists(expected_audio) and os.path.exists(output_audio_path):
        expected_audio = output_audio_path

    vtt_candidates = glob.glob(f"{output_vtt_prefix}*.vtt")
    
    emit_progress("ytdlp_done", 55, f"Audio & subtitles extracted: '{title}'", {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
        "subtitles_count": len(vtt_candidates),
        "target_lang": target_lang
    })

    return {
        "title": title,
        "duration": duration,
        "uploader": uploader,
        "audio_path": expected_audio,
        "vtt_files": vtt_candidates
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


def parse_vtt_cues(vtt_path: str) -> List[Tuple[float, float, str]]:
    """Parse WebVTT cues into (start_sec, end_sec, text) tuples with cleaning and deduplication."""
    with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # VTT timestamp regex: 00:00:12.345 --> 00:00:15.678 or 00:12.345 --> 00:15.678
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

        raw_text = match.group(9).strip()
        # Clean HTML/VTT styling tags (<c>, <b>, <v ...>, etc.)
        clean_text = re.sub(r"<[^>]+>", "", raw_text)
        # Normalize whitespace and strip common caption artifacts
        clean_text = " ".join(clean_text.split())
        clean_text = clean_text.replace("♪", "").replace("♫", "").strip()

        if clean_text:
            cues.append((start_sec, end_sec, clean_text))

    # Deduplicate consecutive cues with duplicate text
    deduped: List[Tuple[float, float, str]] = []
    for c in cues:
        if deduped and deduped[-1][2].lower() == c[2].lower():
            # Extend end time of existing cue
            deduped[-1] = (deduped[-1][0], max(deduped[-1][1], c[1]), deduped[-1][2])
        else:
            deduped.append(c)

    return deduped


def vtt_to_ass(
    vtt_files: List[str],
    output_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    audio_duration: float = 180.0
) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Step 2: Convert parsed VTT subtitle cues to 1080p ASS subtitle format.
    """
    emit_progress("ass_start", 60, "Step 2: Formatting YouTube subtitles into 1080p ASS format...")

    cues: List[Tuple[float, float, str]] = []
    if vtt_files:
        chosen_vtt = vtt_files[0]
        for vf in vtt_files:
            if "en" in vf:
                chosen_vtt = vf
                break
        cues = parse_vtt_cues(chosen_vtt)

    if not cues:
        cues = [
            (2.0, max(6.0, audio_duration - 2.0), "[Music Playing - YouTube Subtitles]")
        ]

    # Build ASS header targeting 1920x1080 canvas
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
    output_path: str = "output_lyric_video.webm",
    duration: Optional[float] = None
) -> str:
    """Step 3: Run FFmpeg to render ASS subtitles over 1080p 30fps transparent VP9 canvas with Opus audio."""
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    emit_progress("ffmpeg_start", 75, f"Step 3: Rendering 1080p 30fps transparent video overlay ({duration:.1f}s)...")
    
    normalized_ass = ass_path.replace("\\", "/")
    if ":" in normalized_ass:
        normalized_ass = normalized_ass.replace(":", "\\:")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black@0.0:s=1920x1080:r=30:d={duration:.2f}",
        "-i", audio_path,
        "-vf", f"ass={normalized_ass}",
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-deadline", "realtime",
        "-cpu-used", "8",
        "-row-mt", "1",
        "-c:a", "libopus",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]

    emit_progress("ffmpeg_rendering", 85, "Step 3: Encoding VP9 yuva420p alpha channel video with Opus audio...")
    subprocess.run(ffmpeg_cmd, check=True)
    emit_progress("ffmpeg_done", 95, f"Step 3: Video successfully rendered to '{output_path}'.")
    return output_path


def generate_lyric_video(
    song_query: str,
    output_path: str = "output_lyric_video.webm",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0
) -> Dict[str, Any]:
    """
    Main generator pipeline powered 100% by yt-dlp & FFmpeg.
    """
    emit_progress("init", 5, f"Initiating YouTube Audio & Subtitle Generator for '{song_query}'...")

    yt_data = download_youtube_audio_and_subtitles(
        query_or_url=song_query,
        output_audio_path=temp_audio_path,
        output_vtt_prefix="temp_subs"
    )

    audio_path = yt_data["audio_path"]
    duration = yt_data["duration"] or get_audio_duration(audio_path)

    ass_path, structured_lines, raw_lrc = vtt_to_ass(
        vtt_files=yt_data["vtt_files"],
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

    emit_progress("completed", 100, "🎉 1080p Transparent Lyric Video ready!", final_result)
    return final_result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    query = args[0] if len(args) > 0 else "Rick Astley - Never Gonna Give You Up"
    out = args[1] if len(args) > 1 else "output_lyric_video.webm"
    
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
