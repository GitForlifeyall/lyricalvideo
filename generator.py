"""
Parallel Lyric-Video Overlay Generator in Python
Produces a 1080p 30fps transparent lyric video overlay synced with audio from YouTube & LRCLIB.
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


def fetch_audio_task(song_query: str, output_audio_path: str = "temp_audio.mp3") -> Dict[str, Any]:
    """
    Task A: Use yt-dlp to search YouTube (ytsearch1:{song_query}), extract the best audio track,
    and save it locally as an MP3 file.
    """
    print(f"[Task A: Audio] Searching YouTube & downloading audio for '{song_query}'...")
    
    # Remove existing audio file if present
    if os.path.exists(output_audio_path):
        try:
            os.remove(output_audio_path)
        except OSError:
            pass

    audio_basename = str(Path(output_audio_path).with_suffix(""))

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
        "default_search": "ytsearch1",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch1:{song_query}"
        info = ydl.extract_info(search_query, download=True)
        if "entries" in info and len(info["entries"]) > 0:
            video_info = info["entries"][0]
        else:
            video_info = info

    duration = video_info.get("duration")
    title = video_info.get("title", song_query)
    
    # Ensure file exists (yt-dlp adds .mp3 after postprocessing)
    expected_file = f"{audio_basename}.mp3"
    if not os.path.exists(expected_file) and os.path.exists(output_audio_path):
        expected_file = output_audio_path

    print(f"[Task A: Audio] Downloaded '{title}' (Duration: {duration}s) -> {expected_file}")
    return {
        "title": title,
        "duration": duration,
        "audio_path": expected_file
    }


def fetch_lyrics_task(song_query: str) -> Dict[str, Any]:
    """
    Task B: Query LRCLIB search endpoint with custom User-Agent, extract syncedLyrics (LRC format).
    """
    print(f"[Task B: Lyrics] Querying LRCLIB API for '{song_query}'...")
    headers = {"User-Agent": USER_AGENT}
    params = {"q": song_query}

    response = requests.get(LRCLIB_SEARCH_API, params=params, headers=headers, timeout=15)
    response.raise_for_status()
    results = response.json()

    if not isinstance(results, list) or len(results) == 0:
        raise ValueError(f"No lyrics found on LRCLIB for query: '{song_query}'")

    # Pick the best matching track with synced lyrics
    best_track = None
    for item in results:
        if item.get("syncedLyrics") and item["syncedLyrics"].strip():
            best_track = item
            break

    if not best_track:
        best_track = results[0]
        if not best_track.get("syncedLyrics"):
            raise ValueError(f"Found track '{best_track.get('trackName')}', but no synchronized (LRC) lyrics are available.")

    print(f"[Task B: Lyrics] Found synced lyrics: '{best_track.get('trackName')}' by '{best_track.get('artistName')}'")
    return {
        "track_name": best_track.get("trackName"),
        "artist_name": best_track.get("artistName"),
        "album_name": best_track.get("albumName"),
        "duration": best_track.get("duration"),
        "synced_lyrics": best_track.get("syncedLyrics"),
        "plain_lyrics": best_track.get("plainLyrics"),
    }


def parse_lrc_timestamp_to_seconds(ts_str: str) -> float:
    """Converts mm:ss.xx or mm:ss.xxx to total seconds (float)."""
    match = re.match(r"(\d{2}):(\d{2})(?:\.(\d{2,3}))?", ts_str.strip())
    if not match:
        return 0.0
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    frac_str = match.group(3) or "0"
    millis = int(frac_str) * 10 if len(frac_str) == 2 else int(frac_str)
    return minutes * 60 + seconds + (millis / 1000.0)


def seconds_to_ass_timestamp(total_seconds: float) -> str:
    """Converts seconds float to ASS timestamp format: h:mm:ss.cc"""
    if total_seconds < 0:
        total_seconds = 0.0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = int(total_seconds % 60)
    centis = int(round((total_seconds - int(total_seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def lrc_to_ass(lrc_content: str, output_ass_path: str = "lyrics.ass", fallback_line_duration: float = 4.0) -> str:
    """
    Step 2: Parse LRC timestamped string and convert into a valid .ass subtitle file.
    Applies styled 1920x1080 karaoke canvas with white text, black outline, and semi-transparent shadow.
    """
    print(f"[ASS Converter] Converting LRC to ASS format -> {output_ass_path}...")
    
    # 1. Parse lines from LRC
    raw_lines = lrc_content.splitlines()
    lrc_regex = re.compile(r"\[(\d{2}:\d{2}(?:\.\d{2,3})?)\](.*)")
    
    parsed_entries: List[Tuple[float, str]] = []
    for line in raw_lines:
        match = lrc_regex.match(line.strip())
        if match:
            ts_str, text = match.group(1), match.group(2).strip()
            if text:  # Ignore empty lines
                start_sec = parse_lrc_timestamp_to_seconds(ts_str)
                parsed_entries.append((start_sec, text))

    if not parsed_entries:
        raise ValueError("LRC content contained no valid timestamped lyric lines.")

    # Sort entries by start time
    parsed_entries.sort(key=lambda x: x[0])

    # 2. Build ASS header and styles targeting 1920x1080
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

    dialogue_lines: List[str] = []
    total_entries = len(parsed_entries)
    
    for i in range(total_entries):
        start_sec, text = parsed_entries[i]
        if i + 1 < total_entries:
            next_start_sec = parsed_entries[i + 1][0]
            # End time is next line's start time, capped if gap is overly large
            end_sec = min(next_start_sec, start_sec + 8.0)
            if end_sec <= start_sec:
                end_sec = start_sec + 2.0
        else:
            # Final line fallback to +4.0s
            end_sec = start_sec + fallback_line_duration

        start_ass = seconds_to_ass_timestamp(start_sec)
        end_ass = seconds_to_ass_timestamp(end_sec)
        
        # Escape curly braces for ASS
        clean_text = text.replace("{", "\\{").replace("}", "\\}")
        dialogue_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{clean_text}")

    full_ass_content = ass_header + "\n".join(dialogue_lines) + "\n"
    
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    print(f"[ASS Converter] Generated {len(dialogue_lines)} dialogue entries in {output_ass_path}")
    return output_ass_path


def get_audio_duration(audio_path: str) -> float:
    """Use ffprobe to get exact audio duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[Warning] ffprobe failed: {e}. Falling back to 180s default.")
        return 180.0


def render_lyric_video_ffmpeg(
    audio_path: str,
    ass_path: str,
    output_path: str = "output_lyric_video.webm",
    duration: Optional[float] = None
) -> str:
    """
    Step 3: Run FFmpeg subprocess that renders the ASS file onto a transparent canvas layered over MP3 audio.
    """
    if duration is None or duration <= 0:
        duration = get_audio_duration(audio_path)

    print(f"[FFmpeg Renderer] Rendering 1080p 30fps transparent video overlay (Duration: {duration:.2f}s)...")
    
    # Format ass path properly for FFmpeg filter on Windows/POSIX
    # Using forward slashes and escaped colons if absolute
    normalized_ass = ass_path.replace("\\", "/")
    if ":" in normalized_ass:
        normalized_ass = normalized_ass.replace(":", "\\:")

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=black@0.0:s=1920x1080:r=30:d={duration:.2f}",
        "-i", audio_path,
        "-vf", f"ass={normalized_ass}",
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-c:a", "copy",
        output_path
    ]

    print(f"[FFmpeg Renderer] Running: {' '.join(ffmpeg_cmd)}")
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"[FFmpeg Renderer] Successfully generated: {output_path}")
    return output_path


async def generate_lyric_video_async(
    song_query: str,
    output_path: str = "output_lyric_video.webm",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass"
) -> Dict[str, Any]:
    """
    Parallel Execution Pipeline using native asyncio and ThreadPoolExecutor.
    Triggers Task A (Audio Engine) and Task B (Lyric Engine) concurrently.
    """
    print("=" * 60)
    print(f"🎬 Starting Parallel Lyric-Video Generation for: '{song_query}'")
    print("=" * 60)

    loop = asyncio.get_running_loop()
    
    # Execute Task A (Audio) and Task B (Lyrics) in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        task_a_future = loop.run_in_executor(executor, fetch_audio_task, song_query, temp_audio_path)
        task_b_future = loop.run_in_executor(executor, fetch_lyrics_task, song_query)

        # Wait for both tasks to complete concurrently
        audio_result, lyrics_result = await asyncio.gather(task_a_future, task_b_future)

    print("\n✅ Both Task A (Audio) and Task B (Lyrics) completed successfully!")

    # Step 2: Convert LRC to ASS
    lrc_content = lyrics_result["synced_lyrics"]
    lrc_to_ass(lrc_content, temp_ass_path)

    # Step 3: Render FFmpeg video overlay
    audio_path = audio_result["audio_path"]
    duration = audio_result.get("duration") or get_audio_duration(audio_path)

    render_lyric_video_ffmpeg(
        audio_path=audio_path,
        ass_path=temp_ass_path,
        output_path=output_path,
        duration=duration
    )

    print("=" * 60)
    print(f"🎉 Lyric Video Overlay successfully created at: {output_path}")
    print("=" * 60)

    return {
        "status": "success",
        "output_path": output_path,
        "audio_path": audio_path,
        "ass_path": temp_ass_path,
        "track_name": lyrics_result.get("track_name"),
        "artist_name": lyrics_result.get("artist_name"),
        "duration": duration
    }


def generate_lyric_video(
    song_query: str,
    output_path: str = "output_lyric_video.webm",
    temp_audio_path: str = "temp_audio.mp3",
    temp_ass_path: str = "lyrics.ass"
) -> Dict[str, Any]:
    """
    Synchronous entrypoint for generate_lyric_video.
    """
    return asyncio.run(
        generate_lyric_video_async(
            song_query=song_query,
            output_path=output_path,
            temp_audio_path=temp_audio_path,
            temp_ass_path=temp_ass_path
        )
    )


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Rick Astley - Never Gonna Give You Up"
    out = sys.argv[2] if len(sys.argv) > 2 else "output_lyric_video.webm"
    generate_lyric_video(query, out)
