"""
Parallel Lyric-Video Overlay Generator in Python
Produces a 1080p 30fps transparent lyric video overlay synced with audio from YouTube & LRCLIB.
Includes intelligent Studio Audio duration-matching to eliminate music video intros/outros.
"""

import os
import re
import sys
import json
import asyncio
import subprocess
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests
import yt_dlp

USER_AGENT = "LyricGenerator/1.0"
LRCLIB_SEARCH_API = "https://lrclib.net/api/search"

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


def fetch_lyrics_task(song_query: str) -> Dict[str, Any]:
    """Task B: Query LRCLIB search API with User-Agent & extract syncedLyrics."""
    emit_progress("lyrics_start", 10, f"Task B: Querying LRCLIB API for '{song_query}'...")
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(LRCLIB_SEARCH_API, params={"q": song_query}, headers=headers, timeout=15)
    response.raise_for_status()
    results = response.json()

    if not results or not isinstance(results, list):
        raise ValueError(f"No lyrics found for query: '{song_query}'")

    # Filter/rank track with syncedLyrics
    best_track = next((item for item in results if item.get("syncedLyrics") and item["syncedLyrics"].strip()), results[0])
    if not best_track.get("syncedLyrics"):
        raise ValueError(f"No synced LRC lyrics found for '{song_query}' (only plain text available).")

    duration = float(best_track.get("duration") or 0.0)
    emit_progress("lyrics_done", 40, f"Task B: Synced lyrics retrieved for '{best_track.get('trackName')}' ({duration:.0f}s)", {
        "track_name": best_track.get("trackName"),
        "artist_name": best_track.get("artistName"),
        "album_name": best_track.get("albumName"),
        "duration": duration
    })

    return {
        "track_name": best_track.get("trackName"),
        "artist_name": best_track.get("artistName"),
        "album_name": best_track.get("albumName"),
        "duration": duration,
        "synced_lyrics": best_track.get("syncedLyrics"),
        "plain_lyrics": best_track.get("plainLyrics"),
    }


def find_best_studio_audio_candidate(ydl: yt_dlp.YoutubeDL, song_query: str, target_duration: Optional[float] = None) -> Dict[str, Any]:
    """
    Search YouTube specifically for Studio Audio / Topic tracks to avoid music videos with long cinematic intros.
    Ranks candidate entries by duration closeness to LRCLIB and title keywords.
    """
    search_queries = [
        f"ytsearch5:{song_query} (Official Audio)",
        f"ytsearch5:{song_query} Audio",
        f"ytsearch5:{song_query} - Topic",
        f"ytsearch5:{song_query}"
    ]

    candidates = []
    for sq in search_queries:
        try:
            res = ydl.extract_info(sq, download=False)
            if res and "entries" in res:
                candidates.extend(res["entries"])
        except Exception:
            pass

    # Deduplicate candidates by id
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c and c.get("id") and c["id"] not in seen:
            seen.add(c["id"])
            unique_candidates.append(c)

    if not unique_candidates:
        # Fallback to direct search
        info = ydl.extract_info(f"ytsearch1:{song_query}", download=False)
        return info["entries"][0] if "entries" in info and len(info["entries"]) > 0 else info

    # Score and rank candidates
    scored = []
    for c in unique_candidates:
        dur = float(c.get("duration") or 0.0)
        dur_diff = abs(dur - target_duration) if (target_duration and target_duration > 0 and dur > 0) else 999.0
        title = (c.get("title") or "").lower()

        score = dur_diff
        # Boost studio audio & topic releases
        if "official audio" in title or "- topic" in title:
            score -= 8.0
        elif "audio" in title:
            score -= 4.0

        # Penalize official music videos that often contain cinematic acting intros
        if "official music video" in title or "music video" in title or "movie" in title or "short film" in title:
            score += 25.0
        if "live" in title or "concert" in title or "reaction" in title or "remix" in title:
            score += 35.0

        scored.append((score, c))

    scored.sort(key=lambda x: x[0])
    best_candidate = scored[0][1]
    print(f"[Audio Engine] Selected studio track: '{best_candidate.get('title')}' (Duration: {best_candidate.get('duration')}s)")
    return best_candidate


def fetch_audio_task(song_query: str, output_audio_path: str = "temp_audio.mp3", target_duration: Optional[float] = None) -> Dict[str, Any]:
    """
    Task A: Search YouTube for studio master audio matching the LRCLIB track duration,
    extract audio and convert to MP3.
    """
    emit_progress("audio_start", 15, f"Task A: Searching YouTube for Studio Audio matching '{song_query}'...")
    audio_basename = str(Path(output_audio_path).with_suffix(""))

    if os.path.exists(output_audio_path):
        try:
            os.remove(output_audio_path)
        except OSError:
            pass

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

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        best_candidate = find_best_studio_audio_candidate(ydl, song_query, target_duration)
        video_url = best_candidate.get("webpage_url") or f"https://www.youtube.com/watch?v={best_candidate.get('id')}"
        emit_progress("audio_downloading", 30, f"Task A: Downloading Studio Audio: '{best_candidate.get('title')}'...")
        ydl.download([video_url])

    duration = best_candidate.get("duration")
    title = best_candidate.get("title", song_query)
    expected_file = f"{audio_basename}.mp3"
    if not os.path.exists(expected_file) and os.path.exists(output_audio_path):
        expected_file = output_audio_path

    emit_progress("audio_done", 50, f"Task A: Studio Audio extracted ({duration or 0}s): '{title}'", {
        "title": title,
        "duration": duration,
        "audio_path": expected_file
    })

    return {"title": title, "duration": duration, "audio_path": expected_file}


def parse_lrc_timestamp_to_seconds(ts_str: str) -> float:
    match = re.match(r"(\d{2}):(\d{2})(?:\.(\d{2,3}))?", ts_str.strip())
    if not match:
        return 0.0
    m, s, frac = int(match.group(1)), int(match.group(2)), match.group(3) or "0"
    ms = int(frac) * 10 if len(frac) == 2 else int(frac)
    return m * 60 + s + (ms / 1000.0)


def seconds_to_ass_timestamp(total_seconds: float) -> str:
    total_seconds = max(0.0, total_seconds)
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    cs = min(99, int(round((total_seconds - int(total_seconds)) * 100)))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def lrc_to_ass(
    lrc_content: str,
    output_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    fallback_line_duration: float = 4.0
) -> Tuple[str, List[Dict[str, Any]]]:
    """Step 2: Convert LRC timestamped string into a styled 1080p .ass subtitle file with optional offset adjustment."""
    emit_progress("ass_start", 55, f"Step 2: Converting LRC timestamps to 1080p ASS (Offset: {offset_seconds:+.2f}s)...")
    
    lrc_regex = re.compile(r"\[(\d{2}:\d{2}(?:\.\d{2,3})?)\](.*)")
    entries = []
    for line in lrc_content.splitlines():
        match = lrc_regex.match(line.strip())
        if match and match.group(2).strip():
            raw_sec = parse_lrc_timestamp_to_seconds(match.group(1))
            adjusted_sec = max(0.0, raw_sec + offset_seconds)
            entries.append((adjusted_sec, match.group(1), match.group(2).strip()))

    entries.sort(key=lambda x: x[0])

    ass_header = """[Script Info]
; Script generated by Parallel Lyric-Video Overlay Generator
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
    
    for i, (start_sec, ts_formatted, text) in enumerate(entries):
        end_sec = min(entries[i + 1][0], start_sec + 8.0) if i + 1 < len(entries) else start_sec + fallback_line_duration
        if end_sec <= start_sec:
            end_sec = start_sec + 2.0
            
        clean_text = text.replace("{", "\\{").replace("}", "\\}")
        dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(start_sec)},{seconds_to_ass_timestamp(end_sec)},Default,,0,0,0,,{clean_text}")
        structured_lines.append({
            "index": i,
            "timestamp": ts_formatted,
            "timeSeconds": start_sec,
            "endSeconds": end_sec,
            "text": text
        })

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(dialogues) + "\n")

    emit_progress("ass_done", 65, f"Step 2: Generated styled ASS with {len(dialogues)} lyric dialogue lines.")
    return output_ass_path, structured_lines


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
    """Step 3: Run FFmpeg subprocess that renders ASS onto 1080p 30fps transparent canvas."""
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    emit_progress("ffmpeg_start", 70, f"Step 3: Rendering 1080p 30fps transparent video overlay ({duration:.1f}s)...")
    
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

    emit_progress("ffmpeg_rendering", 80, "Step 3: Encoding VP9 yuva420p alpha channel video with libopus audio...")
    subprocess.run(ffmpeg_cmd, check=True)
    emit_progress("ffmpeg_done", 95, f"Step 3: Video successfully rendered to '{output_path}'.")
    return output_path


async def generate_lyric_video_async(
    song_query: str,
    output_path: str = "output_lyric_video.webm",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0
) -> Dict[str, Any]:
    """Parallel Execution Pipeline using native asyncio and ThreadPoolExecutor."""
    emit_progress("init", 5, f"Initiating concurrent engines for '{song_query}'...")

    loop = asyncio.get_running_loop()
    
    # Query LRCLIB first or in parallel to get target studio duration
    lyrics_future = loop.run_in_executor(None, fetch_lyrics_task, song_query)
    
    # Run audio extraction with studio candidate ranking
    # If lyrics finishes immediately, pass target duration to audio fetcher
    try:
        lyrics_res = await asyncio.wait_for(asyncio.shield(lyrics_future), timeout=1.5)
        target_dur = lyrics_res.get("duration")
    except Exception:
        target_dur = None

    audio_future = loop.run_in_executor(None, fetch_audio_task, song_query, temp_audio_path, target_dur)
    
    # Wait for both tasks
    if target_dur is not None:
        audio_res = await audio_future
    else:
        audio_res, lyrics_res = await asyncio.gather(audio_future, lyrics_future)

    ass_path, structured_lines = lrc_to_ass(lyrics_res["synced_lyrics"], temp_ass_path, offset_seconds)
    duration = audio_res.get("duration") or get_audio_duration(audio_res["audio_path"])
    
    render_lyric_video_ffmpeg(audio_res["audio_path"], ass_path, output_path, duration)

    final_result = {
        "status": "success",
        "query": song_query,
        "output_path": output_path,
        "audio_path": audio_res["audio_path"],
        "ass_path": ass_path,
        "track_name": lyrics_res.get("track_name"),
        "artist_name": lyrics_res.get("artist_name"),
        "album_name": lyrics_res.get("album_name"),
        "duration": duration,
        "totalLines": len(structured_lines),
        "syncedLines": structured_lines,
        "rawLrc": lyrics_res.get("synced_lyrics")
    }

    emit_progress("completed", 100, f"🎉 1080p Transparent Lyric Video ready!", final_result)
    return final_result


def generate_lyric_video(
    song_query: str,
    output_path: str = "output_lyric_video.webm",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0
) -> Dict[str, Any]:
    """Synchronous entrypoint for generate_lyric_video."""
    return asyncio.run(
        generate_lyric_video_async(
            song_query=song_query,
            output_path=output_path,
            temp_audio_path=temp_audio_path,
            temp_ass_path=temp_ass_path,
            offset_seconds=offset_seconds
        )
    )


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
