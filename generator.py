"""
YouTube-Powered 1080p MP4 Lyric-Video Overlay Generator in Python
Supports Portrait (9:16 - 1080x1920) and Landscape (16:9 - 1920x1080) with Customizable Fonts.
Renders high-quality 1080p 30fps H.264 / AAC MP4 video using FFmpeg.
"""

import os
import re
import sys
import json
import glob
import random
import math
import textwrap
import tempfile

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import time
import requests
import yt_dlp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

YT_HINDI_TRANSITION_SECONDS = 0.42


def detect_tempo_transition_seconds(audio_path: str) -> float:
    """Return a tempo-sensitive transition duration for YT Hindi Type.

    Faster songs receive shorter transitions; slower songs receive longer
    transitions. The bounds prevent extreme BPM estimates from producing
    distracting cuts or transitions longer than a lyric segment.
    """
    analysis_path = audio_path
    temporary_wav = None
    try:
        import aubio

        # The Windows aubio wheel's source reader is WAV-only. Convert a
        # temporary mono copy so MP3/M4A inputs work consistently.
        if Path(audio_path).suffix.lower() != ".wav":
            temporary_wav = os.path.join(
                tempfile.gettempdir(),
                f"lyric_aubio_{os.getpid()}_{int(time.time() * 1000)}.wav",
            )
            conversion = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", audio_path, "-vn", "-ac", "1",
                    "-ar", "44100", "-c:a", "pcm_s16le", temporary_wav,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if conversion.returncode != 0 or not os.path.exists(temporary_wav):
                raise RuntimeError("FFmpeg could not prepare audio for aubio")
            analysis_path = temporary_wav

        win_size = 1024
        hop_size = 512
        source = aubio.source(analysis_path, 0, hop_size)
        tempo = aubio.tempo("specdiff", win_size, hop_size, source.samplerate)
        beat_times = []
        while True:
            samples, read = source()
            if tempo(samples):
                beat_times.append(float(tempo.get_last_s()))
            if read < hop_size:
                break

        bpm = float(tempo.get_bpm() or 0.0)
        if len(beat_times) >= 4:
            intervals = [
                beat_times[index] - beat_times[index - 1]
                for index in range(1, len(beat_times))
                if beat_times[index] > beat_times[index - 1]
            ]
            if intervals:
                intervals.sort()
                bpm = 60.0 / intervals[len(intervals) // 2]

        if not 40.0 <= bpm <= 220.0:
            raise ValueError(f"unreliable BPM estimate: {bpm:.1f}")

        # 0.42s at 100 BPM; faster tempo => shorter transition.
        transition = 0.42 * (100.0 / bpm)
        return max(0.18, min(0.65, transition))
    except Exception as exc:
        print(f"[YT Hindi] BPM detection unavailable; using 0.42s transition ({type(exc).__name__})")
        return YT_HINDI_TRANSITION_SECONDS
    finally:
        if temporary_wav:
            try:
                os.remove(temporary_wav)
            except OSError:
                pass


# Force UTF-8 on Windows consoles to prevent cp1252 charmap encoding errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def format_brat_multiline(text: str, max_chars_per_line: int = 15) -> str:
    """
    Wraps single-line text into multi-line Brat block using ASS line breaks (\\N).
    """
    text_clean = text.lower().strip()
    if not text_clean:
        return ""
    wrapped_lines = textwrap.wrap(
        text_clean,
        width=max_chars_per_line,
        break_long_words=False,
        replace_whitespace=True
    )
    return r"\N".join(wrapped_lines)

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

        is_manual = kind.startswith("manual")
        try:
            url = chosen_fmt["url"]
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10)
            if resp.status_code == 200 and resp.text.strip():
                if chosen_fmt.get("ext") == "json3" or "json3" in url:
                    data = resp.json()
                    cues = parse_json3_timedtext(data)
                    if cues:
                        print(f"[Subtitles] Selected '{lang_key}' ({kind}) with {len(cues)} lines (manual={is_manual})")
                        return cues, lang_key, is_manual
                else:
                    cues = parse_vtt_text(resp.text)
                    if cues:
                        print(f"[Subtitles] Selected VTT '{lang_key}' ({kind}) with {len(cues)} lines (manual={is_manual})")
                        return cues, lang_key, is_manual
        except Exception as e:
            print(f"[Warning] Failed to fetch subtitles for {lang_key}: {e}")

    return [], "none", False



def is_lyric_metadata(text: str) -> bool:
    """Reject subtitle metadata/descriptions that are not actual lyric lines."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return True
    metadata_phrases = (
        "music playing", "native youtube audio", "instrumental", "music only",
        "applause", "cheering", "speaking foreign language", "inaudible",
        "[music]", "(music)", "music", "♪", "♫"
    )
    clean_no_brackets = re.sub(r"[\[\]\(\)\{\}\-♪♫]", " ", normalized).strip()
    if clean_no_brackets in ("music", "music playing", "native youtube audio", "instrumental", "applause", "cheering", ""):
        return True
    return any(phrase in normalized for phrase in metadata_phrases if len(phrase) > 5)


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

        if clean_text and clean_text != "\n" and not is_lyric_metadata(clean_text):
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

        if clean_text and not is_lyric_metadata(clean_text):
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


def fetch_lrclib_lyrics(song_title: str, artist_name: str = "", duration: float = 0.0) -> Tuple[List[Tuple[float, float, str]], str]:
    """Fetch timestamped lyrics from LRCLIB as synced lyrics fallback with intelligent artist extraction and script preference."""
    try:
        raw_chunks = re.split(r'[\-\|\–\—\/]', song_title)
        fluff_pattern = r'(?i)\b(official|music|video|audio|lyrics|lyrical|dance\s*songs|full\s*song|hd|4k|remix|vevo|topic|feat\.?|ft\.?|starring|records|t-series|tips\s*official|zee\s*music)\b|\(.*?\)|\[.*?\]'
        
        cleaned_chunks = []
        for c in raw_chunks:
            c_clean = re.sub(fluff_pattern, ' ', c).strip()
            c_clean = " ".join(c_clean.split())
            if c_clean and len(c_clean) > 1:
                cleaned_chunks.append(c_clean)
                
        title_main = cleaned_chunks[0] if cleaned_chunks else re.sub(fluff_pattern, ' ', song_title).strip()
        
        potential_artists = [c for c in cleaned_chunks[1:] if len(c) > 2]
        if artist_name and artist_name != "YouTube":
            clean_art = re.sub(fluff_pattern, ' ', artist_name).strip()
            if clean_art and clean_art not in potential_artists:
                potential_artists.insert(0, clean_art)
                
        search_terms = []
        for art in potential_artists[:3]:
            search_terms.append(f"{title_main} {art}".strip())
        search_terms.append(title_main)
        
        unique_terms = []
        for t in search_terms:
            if t and t not in unique_terms:
                unique_terms.append(t)
                
        results = []
        seen_ids = set()
        for term in unique_terms:
            try:
                resp = requests.get("https://lrclib.net/api/search", params={"q": term}, headers=BROWSER_HEADERS, timeout=10)
                if resp.ok and isinstance(resp.json(), list):
                    for item in resp.json():
                        iid = item.get("id")
                        if iid and iid not in seen_ids:
                            seen_ids.add(iid)
                            results.append(item)
            except Exception:
                pass
                
        synced_results = [item for item in results if item.get("syncedLyrics") and not item.get("instrumental")]
        if not synced_results:
            return [], "none"
            
        def score_lrclib_candidate(item: Dict[str, Any]) -> Tuple[int, int, float]:
            lyrics = item.get("syncedLyrics", "")
            cand_artist = (item.get("artistName") or "").lower()
            cand_track = (item.get("trackName") or "").lower()
            
            # Penalize non-Devanagari, non-Latin foreign scripts (e.g. Arabic/Urdu script: [\u0600-\u06FF])
            has_arabic_urdu = bool(re.search(r'[\u0600-\u06FF]', lyrics))
            has_indic = bool(re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', lyrics))
            has_latin = bool(re.search(r'[a-zA-Z]', lyrics))
            
            if has_arabic_urdu:
                script_penalty = 100
            elif has_indic and not (has_latin and len(re.findall(r'[a-zA-Z]', lyrics)) > 20):
                script_penalty = 1
            else:
                script_penalty = 0
                
            artist_match_penalty = 0
            if potential_artists:
                any_match = any(
                    any(token.lower() in cand_artist or token.lower() in cand_track for token in re.findall(r'\w+', art) if len(token) > 2)
                    for art in potential_artists
                )
                artist_match_penalty = 0 if any_match else 2
                
            dur_diff = abs(float(item.get("duration") or duration) - float(duration or 0)) if duration > 0 else 0.0
            return (script_penalty, artist_match_penalty, dur_diff)

        best = min(synced_results, key=score_lrclib_candidate, default=synced_results[0])


        
        lrc_lines = []
        for line in best["syncedLyrics"].splitlines():
            m = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)', line)
            if m and m.group(3).strip():
                start = int(m.group(1)) * 60 + float(m.group(2))
                txt = m.group(3).strip()
                if not is_lyric_metadata(txt):
                    lrc_lines.append((start, txt))
                    
        cues = []
        for i, (start, txt) in enumerate(lrc_lines):
            end = lrc_lines[i + 1][0] if i + 1 < len(lrc_lines) else (start + 3.5)
            cues.append((start, end, txt))
            
        if cues:
            print(f"[LRCLIB] Found {len(cues)} synced lines for '{best.get('trackName')}' by '{best.get('artistName')}'")
            return cues, "lrclib"
    except Exception as e:
        print(f"[LRCLIB Warning] {e}")
        
    return [], "none"



SPOTIFY_LYRICS_API_URL = os.environ.get("SPOTIFY_LYRICS_API_URL", "http://localhost:8080").rstrip("/")
SPOTIFY_SP_DC = os.environ.get("SPOTIFY_SP_DC", "")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def fetch_spotify_track_metadata(spotify_url: str) -> Dict[str, Any]:
    """Read public Spotify track metadata used for accurate YouTube matching.

    This follows Sunnify's approach: Spotify supplies metadata only; yt-dlp
    still downloads the permitted audio source from YouTube.
    """
    match = re.search(
        r"(?:open\.spotify\.com/track/|spotify:track:)([A-Za-z0-9]{22})",
        spotify_url,
    )
    if not match:
        return {}

    track_id = match.group(1)
    try:
        response = requests.get(
            f"https://open.spotify.com/embed/track/{track_id}",
            headers={"User-Agent": BROWSER_HEADERS["User-Agent"]},
            timeout=8,
        )
        response.raise_for_status()
        next_data = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>',
            response.text,
        )
        if not next_data:
            return {}
        payload = json.loads(next_data.group(1))

        def find_track(node: Any) -> Optional[Dict[str, Any]]:
            if isinstance(node, dict):
                if (node.get("duration") or 0) and (node.get("name") or node.get("title")):
                    return node
                for value in node.values():
                    found = find_track(value)
                    if found:
                        return found
            elif isinstance(node, list):
                for value in node:
                    found = find_track(value)
                    if found:
                        return found
            return None

        entity = find_track(payload) or {}
        artists_data = entity.get("artists") or []
        if isinstance(artists_data, list):
            artists = ", ".join(
                str(item.get("name", "")) for item in artists_data if isinstance(item, dict)
            ).strip()
        else:
            artists = str(entity.get("subtitle") or "").strip()
        return {
            "title": str(entity.get("name") or entity.get("title") or "").strip(),
            "artists": artists,
            "duration": float(entity.get("duration") or 0) / 1000.0,
        }
    except Exception as exc:
        emit_progress("spotify_metadata_warning", 42, f"Spotify metadata lookup unavailable: {type(exc).__name__}")
        return {}


def fetch_spotify_lyrics(song_title: str, artist_name: str = "", duration: float = 0.0) -> Tuple[List[Tuple[float, float, str]], str]:
    """
    Fetch synced lyrics from Spotify via local/Docker akashrchandran/spotify-lyrics-api REST API.
    1. Checks for direct Spotify track link or resolves the Spotify track ID for the song.
    2. Queries http://localhost:8080/?trackid={track_id}&format=lrc.
    3. Parses synced lyrics into (start_sec, end_sec, text) cues.
    """
    try:
        # Check if direct Spotify link was provided
        direct_match = re.search(r'spotify\.com/track/([a-zA-Z0-9]{22})', song_title)
        if direct_match:
            track_ids = [direct_match.group(1)]
            search_query = song_title
        else:
            raw_chunks = re.split(r'[\-\|\–\—\/]', song_title)
            fluff_pattern = r'(?i)\b(official|music|video|audio|lyrics|lyrical|dance\s*songs|full\s*song|hd|4k|remix|vevo|topic|feat\.?|ft\.?|starring|records|t-series|tips\s*official|zee\s*music)\b|\(.*?\)|\[.*?\]'
            
            cleaned_chunks = []
            for c in raw_chunks:
                c_clean = re.sub(fluff_pattern, ' ', c).strip()
                c_clean = " ".join(c_clean.split())
                if c_clean and len(c_clean) > 1:
                    cleaned_chunks.append(c_clean)
                    
            title_main = cleaned_chunks[0] if cleaned_chunks else re.sub(fluff_pattern, ' ', song_title).strip()
            artists_part = " ".join(cleaned_chunks[1:3]) if len(cleaned_chunks) > 1 else (artist_name if artist_name != "YouTube" else "")
            search_query = f"{title_main} {artists_part}".strip()
            
            emit_progress("spotify_start", 42, f"Searching Spotify (Primary) for synced lyrics: '{search_query}'...")

            # Multi-engine search for Spotify track ID
            track_ids = []
            
            # Engine 0: Official Spotify Developer API (if configured in .env)
            if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
                try:
                    auth_resp = requests.post(
                        "https://accounts.spotify.com/api/token",
                        data={"grant_type": "client_credentials"},
                        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
                        timeout=4
                    )
                    if auth_resp.ok:
                        app_token = auth_resp.json().get("access_token")
                        if app_token:
                            search_res = requests.get(
                                "https://api.spotify.com/v1/search",
                                params={"q": search_query, "type": "track", "limit": 3},
                                headers={"Authorization": f"Bearer {app_token}"},
                                timeout=4
                            )
                            if search_res.ok:
                                for itm in search_res.json().get("tracks", {}).get("items", []):
                                    if itm.get("id") and itm["id"] not in track_ids:
                                        track_ids.append(itm["id"])
                except Exception:
                    pass

            
            # Engine 1: Jina AI Reader on open.spotify.com/search (bypasses JS rendering & DDG rate limits)
            for query_variant in [f"{title_main} {artists_part}".strip(), title_main]:
                if not query_variant:
                    continue
                try:
                    jina_url = f"https://r.jina.ai/https://open.spotify.com/search/{urllib.parse.quote(query_variant)}"
                    jina_resp = requests.get(jina_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
                    if jina_resp.ok:
                        found_ids = re.findall(r'open\.spotify\.com/track/([a-zA-Z0-9]{22})', jina_resp.text)
                        for tid in found_ids:
                            if tid not in track_ids:
                                track_ids.append(tid)
                except Exception:
                    pass
                if track_ids:
                    break

            # Engine 2: DuckDuckGo HTML search fallback
            if not track_ids:
                search_queries = [
                    f"site:open.spotify.com/track {search_query}",
                    f"site:open.spotify.com/track {title_main}"
                ]
                for sq in search_queries:
                    try:
                        ddg_resp = requests.get(
                            "https://html.duckduckgo.com/html/",
                            params={"q": sq},
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                            timeout=5
                        )
                        if ddg_resp.ok:
                            found_ids = re.findall(r'open\.spotify\.com(?:%2F|/)track(?:%2F|/)([a-zA-Z0-9]{22})', ddg_resp.text)
                            for tid in found_ids:
                                if tid not in track_ids:
                                    track_ids.append(tid)
                    except Exception:
                        pass
                    if track_ids:
                        break


        # 2. Query spotify-lyrics-api for candidate track IDs
        for tid in track_ids[:3]:
            try:
                lrc_resp = requests.get(
                    f"{SPOTIFY_LYRICS_API_URL}/",
                    params={"trackid": tid, "format": "lrc"},
                    timeout=5
                )
                if not lrc_resp.ok:
                    continue
                data = lrc_resp.json()
                if data.get("error") or data.get("syncType", "").upper() == "UNSYNCED":
                    continue
                
                lines_data = data.get("lines", [])
                if not lines_data:
                    continue
                
                cues = []
                for idx, item in enumerate(lines_data):
                    time_tag = item.get("timeTag") or item.get("startTimeMs") or "00:00.00"
                    if isinstance(time_tag, (int, float)):
                        s_sec = float(time_tag) / 1000.0
                    else:
                        m = re.match(r'(\d+):(\d+(?:\.\d+)?)', str(time_tag))
                        s_sec = int(m.group(1)) * 60 + float(m.group(2)) if m else 0.0
                        
                    txt = (item.get("words") or "").strip()
                    if txt and not is_lyric_metadata(txt):
                        if idx + 1 < len(lines_data):
                            next_tag = lines_data[idx + 1].get("timeTag") or lines_data[idx + 1].get("startTimeMs") or ""
                            if isinstance(next_tag, (int, float)):
                                e_sec = float(next_tag) / 1000.0
                            else:
                                mn = re.match(r'(\d+):(\d+(?:\.\d+)?)', str(next_tag))
                                e_sec = int(mn.group(1)) * 60 + float(mn.group(2)) if mn else (s_sec + 3.0)
                        else:
                            e_sec = s_sec + 3.5
                        cues.append((s_sec, max(s_sec + 1.2, e_sec), txt))
                        
                if cues and len(cues) > 1:
                    timestamps = [c[0] for c in cues]
                    if max(timestamps) - min(timestamps) < 0.5:
                        # Unsynced lyrics with identical timestamps, skip
                        continue
                    emit_progress("spotify_done", 46, f"Retrieved {len(cues)} synced lines from Spotify (Track: {tid})")
                    print(f"[Spotify-Lyrics-API] Found {len(cues)} synced lines on Spotify (Track ID: {tid})")
                    return cues, "spotify"

            except Exception:
                continue

    except Exception as err:
        print(f"[Spotify-Lyrics-API Warning] {err}")

    return [], "none"




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


def get_python_executable() -> str:
    """Resolve preferred virtualenv Python interpreter (.venv310 -> .venv -> sys.executable)."""
    project_root = Path(__file__).resolve().parent
    venv310_py = project_root / ".venv310" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if venv310_py.exists():
        return str(venv310_py)
    venv_py = project_root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def transliterate_hindi_cues(cues: List[Tuple[float, float, str]]) -> Tuple[List[Tuple[float, float, str]], str]:
    """Transliterate Devanagari/Indic script cues to Romanized Hinglish using AI4Bharat IndicXlit."""
    if not cues or not any(re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', text) for _, _, text in cues):
        return cues, "none"

    py_bin = get_python_executable()
    runner_script = Path(__file__).resolve().parent / "indicxlit_runner.py"
    payload = json.dumps([text for _, _, text in cues], ensure_ascii=False)

    try:
        proc = subprocess.run(
            [py_bin, str(runner_script)],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        stdout_text = proc.stdout or ""
        result_json_str = ""
        for line in stdout_text.splitlines():
            if line.startswith("__INDICXLIT_RESULT__"):
                result_json_str = line.replace("__INDICXLIT_RESULT__", "").strip()
                break
        if not result_json_str:
            match = re.search(r'\[.*\]', stdout_text, re.DOTALL)
            if match:
                result_json_str = match.group(0)

        if result_json_str:
            converted = json.loads(result_json_str)
            return [(s, e, converted[i] if i < len(converted) else text) for i, (s, e, text) in enumerate(cues)], "indicxlit"
    except Exception as error:
        emit_progress("indicxlit_warning", 50, f"IndicXlit transliteration warning: {error}")

    return cues, "none"


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

    is_youtube_url = ("youtube.com" in query_or_url or "youtu.be" in query_or_url)
    is_search_query = False
    spotify_metadata: Dict[str, Any] = {}
    expected_duration = 0.0
    expected_title = ""
    expected_artists = ""
    if "spotify.com/track/" in query_or_url or query_or_url.startswith("spotify:track:"):
        spotify_metadata = fetch_spotify_track_metadata(query_or_url)
        expected_title = spotify_metadata.get("title") or ""
        expected_artists = spotify_metadata.get("artists") or ""
        expected_duration = float(spotify_metadata.get("duration") or 0)
        sp_title = f"{expected_artists} - {expected_title}".strip(" -") or query_or_url
        try:
            if not expected_title:
                oembed_resp = requests.get(f"https://open.spotify.com/oembed?url={query_or_url}", timeout=4)
                if oembed_resp.ok:
                    sp_title = oembed_resp.json().get("title", query_or_url)
        except Exception:
            pass
        search_target = f"ytsearch20:{sp_title}"
        is_search_query = True
    elif is_youtube_url:
        search_target = query_or_url
    else:
        search_target = f"ytsearch20:{query_or_url}"
        is_search_query = True


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
        # A plain YouTube search can return several versions of a track.
        # Select the result with the most representative runtime. A pasted
        # URL remains authoritative and is never silently replaced.
        if is_search_query:
            search_opts = dict(ydl_opts)
            # Flat search entries frequently omit the channel and catalogue
            # metadata needed to distinguish Topic audio from uploads.
            search_opts["extract_flat"] = False
            with yt_dlp.YoutubeDL(search_opts) as search_ydl:
                search_info = search_ydl.extract_info(search_target, download=False)
            candidates = search_info.get("entries", []) if isinstance(search_info, dict) else []
            candidates = [
                item for item in candidates
                if item and (item.get("webpage_url") or item.get("url"))
            ]
            duration_values = sorted(
                float(item.get("duration") or 0)
                for item in candidates
                if float(item.get("duration") or 0) > 0
            )
            median_duration = (
                duration_values[len(duration_values) // 2]
                if duration_values
                else 0.0
            )
            if len(duration_values) % 2 == 0 and duration_values:
                median_duration = (
                    duration_values[len(duration_values) // 2 - 1] + median_duration
                ) / 2.0

            def duration_score(item: Dict[str, Any]) -> int:
                # Prefer the result closest to the common runtime returned by
                # YouTube search, avoiding snippets, edits, and outliers.
                item_duration = float(item.get("duration") or 0)
                if median_duration and item_duration:
                    duration_delta = abs(item_duration - median_duration)
                    return max(0, int(160 - min(160, duration_delta * 8)))
                return 0

            if candidates:
                # For Spotify links, compare against Spotify's exact track
                # duration and title. This is Sunnify's key matching step.
                selection_pool = candidates
                if expected_title:
                    title_core = re.sub(r"[^\w\s]", " ", expected_title.lower())
                    title_matches = [
                        item for item in candidates
                        if title_core and title_core in re.sub(
                            r"[^\w\s]", " ", (item.get("title") or "").lower()
                        )
                    ]
                    if title_matches:
                        selection_pool = title_matches
                        artist_tokens = [
                            token.strip().lower()
                            for token in re.split(r"[,&]+|\s+(?:feat\.?|ft\.?)\s+", expected_artists, flags=re.I)
                            if token.strip()
                        ]
                        if artist_tokens:
                            artist_matches = [
                                item for item in title_matches
                                if any(
                                    token in (item.get("title") or "").lower()
                                    for token in artist_tokens
                                )
                            ]
                            if artist_matches:
                                selection_pool = artist_matches

                if expected_duration and any(item.get("duration") for item in selection_pool):
                    def spotify_match_key(item: Dict[str, Any]) -> Tuple[float, int]:
                        item_title = (item.get("title") or "").lower()
                        unwanted_variant = bool(re.search(
                            r"\b(?:8d|slowed|reverb|nightcore|sped\s*up|remix|edit|live|karaoke|cover|bass\s*boost(?:ed)?)\b",
                            item_title,
                        ))
                        return (
                            abs(float(item["duration"]) - expected_duration),
                            1 if unwanted_variant else 0,
                        )

                    selected = min(
                        (item for item in selection_pool if item.get("duration")),
                        key=spotify_match_key,
                    )
                    if abs(float(selected["duration"]) - expected_duration) > 30:
                        raise yt_dlp.utils.DownloadError(
                            "No YouTube result matched the Spotify title and duration closely enough."
                        )
                else:
                    selected = max(selection_pool, key=duration_score)
                selected_url = selected.get("webpage_url") or selected.get("url")
                if selected_url:
                    search_target = selected_url
                    comparison_duration = expected_duration or median_duration
                    emit_progress("ytdlp_source_selected", 34, f"Selected the YouTube result closest to the Spotify track duration ({comparison_duration:.1f}s)...")

        info = ydl.extract_info(search_target, download=True)
        video_info = info["entries"][0] if "entries" in info and len(info["entries"]) > 0 else info

    title = video_info.get("title", query_or_url)
    duration = video_info.get("duration") or 0.0
    uploader = video_info.get("uploader") or video_info.get("channel") or "YouTube"
    artist = video_info.get("artist") or video_info.get("creator") or uploader

    expected_audio = f"{audio_basename}.mp3"
    if not os.path.exists(expected_audio) and os.path.exists(output_audio_path):
        expected_audio = output_audio_path

    cues, matched_lang, is_manual = fetch_direct_youtube_subtitles(video_info, target_lang=target_lang)

    # Check if lyrics contain non-Latin Indic/Gurmukhi/Devanagari script
    has_indic_script = any(bool(re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', c[2])) for c in cues) if cues else False
    is_punjabi_or_hindi_requested = target_lang in ["pa", "punjabi", "panjabi", "hi", "hindi"]

    if is_manual and cues:
        # 1. Manual / Creator-uploaded subtitles found:
        # DO NOT fallback to Spotify or LRCLIB (even if in Devanagari script).
        # Directly transliterate Devanagari lyrics into Hinglish with IndicXlit.
        if has_indic_script:
            emit_progress("indicxlit_start", 50, "Manual creator Devanagari captions found; transliterating with AI4Bharat IndicXlit...")
            cues, xlit_src = transliterate_hindi_cues(cues)
            if xlit_src == "indicxlit":
                matched_lang = "indicxlit"
    else:
        # 2. YouTube Auto-generated subtitles or No manual subtitles found:
        # Strict priority: 1) Spotify Lyrics API -> 2) LRCLIB -> 3) Auto-captions fallback
        query_hint = query_or_url if ("spotify.com" in query_or_url or "spotify:" in query_or_url) else title
        spotify_cues, spotify_lang = fetch_spotify_lyrics(query_hint, artist, duration)
        if spotify_cues:
            cues = spotify_cues
            matched_lang = spotify_lang
        else:
            emit_progress("lrclib_fallback", 45, "Searching LRCLIB for verified synced lyrics...")
            lrclib_cues, lrclib_lang = fetch_lrclib_lyrics(title, artist, duration)
            if lrclib_cues:
                cues = lrclib_cues
                matched_lang = lrclib_lang

        # Transliterate any Devanagari script in active cues (from LRCLIB or YouTube auto-captions)
        has_indic_script = any(bool(re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', c[2])) for c in cues) if cues else False
        if has_indic_script:
            emit_progress("indicxlit_start", 50, "Devanagari/Indic script detected; transliterating lyrics with AI4Bharat IndicXlit...")
            cues, xlit_src = transliterate_hindi_cues(cues)
            if xlit_src == "indicxlit":
                matched_lang = "indicxlit"


    # Enforce Romanized Hinglish/Punjabi lyrics via Genius when Indic script is still present or no captions found
    has_remaining_indic = any(bool(re.search(r'[\u0900-\u097F\u0A00-\u0A7F]', c[2])) for c in cues) if cues else False
    if not cues or has_remaining_indic or (not cues and is_punjabi_or_hindi_requested):
        emit_progress("genius_fallback", 50, f"Fetching verified Romanized Punjabi/Hinglish lyrics from Genius API...")
        genius_cues, genius_lang = fetch_genius_lyrics_fallback(title, uploader, duration)
        if genius_cues:
            if cues and len(cues) > 5 and len(genius_cues) > 5 and has_remaining_indic:
                aligned_cues = []
                num_cues = min(len(cues), len(genius_cues))
                for i in range(num_cues):
                    aligned_cues.append((cues[i][0], cues[i][1], genius_cues[i][2]))
                cues = aligned_cues
            else:
                cues = genius_cues
            matched_lang = "punjabi_hinglish"




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


BRAT_THEMES = {
    "green": {
        "name": "Brat Lime",
        "bg_color": "0x8ACE00",
        "text_color": "&H00000000",
        "hex_bg": "#8ACE00",
        "hex_text": "#000000",
    },
    "white": {
        "name": "Brat White",
        "bg_color": "0xFFFFFF",
        "text_color": "&H00000000",
        "hex_bg": "#FFFFFF",
        "hex_text": "#000000",
    },
    "red": {
        "name": "The Moment (Red/Blue)",
        "bg_color": "0xFF0000",
        "text_color": "&H00FF0000",
        "hex_bg": "#FF0000",
        "hex_text": "#0000FF",
    },
    "black": {
        "name": "Brat Black",
        "bg_color": "0x000000",
        "text_color": "&H00FFFFFF",
        "hex_bg": "#000000",
        "hex_text": "#FFFFFF",
    },
    "blue": {
        "name": "SWEAT Tour (Blue/Red)",
        "bg_color": "0x0A00AD",
        "text_color": "&H000001DE",
        "outline_color": "&H00000000",
        "hex_bg": "#0A00AD",
        "hex_text": "#DE0100",
        "font_name": "Impact",
        "bold": -1,
        "scale_x": 100,
        "outline_width": 0,
        "shadow_depth": 0,
        "uppercase": True,
    },
    "strike": {
        "name": "Brat Strike",
        "bg_color": "0x8ACE00",
        "text_color": "&H00000000",
        "hex_bg": "#8ACE00",
        "hex_text": "#000000",
        "strikeout": 1,
    }
}


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
        "bg_color": "black",
        "scale_x": 100,
        "blur": 0.0,
        "force_lowercase": False,
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
        "bg_color": "black",
        "scale_x": 100,
        "blur": 0.0,
        "force_lowercase": False,
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
        "bg_color": "black",
        "scale_x": 100,
        "blur": 0.0,
        "force_lowercase": False,
    },
    "template4_brat": {
        "id": "template4_brat",
        "name": "Template 4 (Brat Minimal)",
        "aspect_ratio": "portrait",
        "font_name": "Arial Narrow",
        "font_size": 72,
        "primary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": 0,
        "outline_width": 0,
        "shadow_depth": 0,
        "margin_v": 80,
        "bg_color": "0x8ACE00",
        "scale_x": 68,
        "blur": 1.5,
        "spacing": -1,
        "force_lowercase": True,
    },
    "template_4_brat": {
        "id": "template_4_brat",
        "name": "Template 4 (Brat Minimal)",
        "aspect_ratio": "portrait",
        "font_name": "Arial Narrow",
        "font_size": 72,
        "primary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": 0,
        "outline_width": 0,
        "shadow_depth": 0,
        "margin_v": 80,
        "bg_color": "0x8ACE00",
        "scale_x": 68,
        "blur": 1.5,
        "spacing": -1,
        "force_lowercase": True,
    },
    "brat": {
        "id": "brat",
        "name": "Brat Minimal (Charli XCX)",
        "aspect_ratio": "portrait",
        "font_name": "Arial Narrow",
        "font_size": 72,
        "primary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": 0,
        "outline_width": 0,
        "shadow_depth": 0,
        "margin_v": 80,
        "bg_color": "0x8ACE00",
        "scale_x": 68,
    },
    "yt_hindi_type": {
        "id": "yt_hindi_type",

        "name": "YT Hindi Type (Cinematic Video)",
        "aspect_ratio": "portrait",
        "font_name": "EB Garamond",
        "font_size": 38,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": 0,
        "outline_width": 0,
        "shadow_depth": 0,
        "margin_v": 0,
        "bg_color": "black",
        "scale_x": 100,
        "blur": 0.0,
        "force_lowercase": False,
    },
    "yt_hindi_intro": {
        "id": "yt_hindi_intro",
        "name": "YT Hindi (Film Burn Intro)",
        "aspect_ratio": "portrait",
        "font_name": "EB Garamond",
        "font_size": 38,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": 0,
        "outline_width": 0,
        "shadow_depth": 0,
        "margin_v": 0,
        "bg_color": "black",
        "scale_x": 100,
        "blur": 0.0,
        "force_lowercase": False,
        "film_burn_intro": True,
    }
}


def get_top_header_text(user_header: Optional[str] = None) -> str:
    """Read top header from user input or pick a random line from headers.txt."""
    if user_header and user_header.strip():
        cleaned = user_header.strip()
        # If it's a default/placeholder string, ignore and pick from headers.txt
        if cleaned.lower() not in ("default", "none", "null", "(when lyrics feel too personal...)", "when lyrics feel too personal..."):
            return cleaned
    headers_file = os.path.join(os.path.dirname(__file__), "headers.txt")
    if os.path.exists(headers_file):
        try:
            with open(headers_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
                if lines:
                    return random.choice(lines)
        except Exception:
            pass
    return "When Lyrics Feel Too Personal... 🤌🤍"


def get_intro_header_text(user_intro: Optional[str] = None, song_title: str = "", duration: float = 0.0) -> str:
    """Read intro text from user input or pick a random line from intro_headers.txt, dynamically populating placeholders."""
    raw_text = ""
    if user_intro and user_intro.strip():
        cleaned = user_intro.strip()
        if cleaned.lower() not in ("default", "none", "null"):
            raw_text = cleaned

    if not raw_text:
        intro_file = os.path.join(os.path.dirname(__file__), "intro_headers.txt")
        if os.path.exists(intro_file):
            try:
                with open(intro_file, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
                    if lines:
                        raw_text = random.choice(lines)
            except Exception:
                pass

    if not raw_text:
        raw_text = "Close your eyes and feel the music 🤌✨"

    clean_title = song_title.strip() if song_title else "This Song"
    clean_title = re.sub(r'[\(\[\{].*?(official|video|audio|lyrics|feat|ft\.).*?[\)\]\}]', '', clean_title, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = song_title.strip() or "This Song"

    dur_str = str(int(round(duration))) if duration > 0 else "30"

    formatted = raw_text
    formatted = re.sub(r'\{song_name\}', clean_title, formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\{duration\}', dur_str, formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\(Duration\)', dur_str, formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\(song name\)', clean_title, formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'"song name"', clean_title, formatted, flags=re.IGNORECASE)
    formatted = re.sub(r'\+citadel-font', '', formatted, flags=re.IGNORECASE)

    return formatted



def get_all_background_videos() -> List[str]:
    """Retrieve all background video clips from videos/input/."""
    input_dir = os.path.join(os.path.dirname(__file__), "videos", "input")
    if os.path.exists(input_dir):
        exts = (".mp4", ".mov", ".mkv", ".webm", ".avi")
        return [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith(exts)]
    return []


def get_random_background_video() -> Optional[str]:
    """Select a random background video clip from videos/input/."""
    videos = get_all_background_videos()
    return random.choice(videos) if videos else None


def get_all_film_overlays() -> List[str]:
    """Retrieve all authentic film overlay video clips from 'FILM OVERLAY/' directory."""
    folder = os.path.join(os.path.dirname(__file__), "FILM OVERLAY")
    if os.path.exists(folder):
        exts = (".mp4", ".mov", ".mkv", ".webm")
        return [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(exts) and not f.startswith(".")
        ]
    return []


def create_header_overlay_image(
    header_text: str,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    top_margin_height: int = 600,
    output_png_path: str = "header_overlay.png"
) -> str:
    """
    Renders a centered Georgia Italic header with inline Apple-style PNG emojis.
    Positioned elegantly just above the video rectangle with a small gap.
    Saves a transparent RGBA image matching the canvas dimensions.
    """
    img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    scale = canvas_width / 1080.0
    font_size = int(32 * scale)
    font_paths = [
        "C:/Windows/Fonts/georgiai.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "CormorantGaramond-Italic.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "EBGaramond-Variable.ttf")
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    emoji_pattern = re.compile(
        r'([\U00010000-\U0010ffff][\ufe00-\ufe0f]?|[\u2600-\u27bf][\ufe00-\ufe0f]?|\u2764[\ufe00-\ufe0f]?)'
    )
    tokens = []
    last_idx = 0
    for m in emoji_pattern.finditer(header_text):
        if m.start() > last_idx:
            txt_part = re.sub(r'[\ufe00-\ufe0f]', '', header_text[last_idx:m.start()])
            if txt_part:
                tokens.append(("text", txt_part))
        tokens.append(("emoji", m.group()))
        last_idx = m.end()
    if last_idx < len(header_text):
        txt_part = re.sub(r'[\ufe00-\ufe0f]', '', header_text[last_idx:])
        if txt_part:
            tokens.append(("text", txt_part))

    emoji_size = int(font_size * 1.1)
    measured_tokens = []
    total_w = 0
    for t_type, t_val in tokens:
        if t_type == "text":
            bbox = draw.textbbox((0, 0), t_val, font=font)
            w = bbox[2] - bbox[0]
            measured_tokens.append((t_type, t_val, w))
            total_w += w
        else:
            w = emoji_size + int(6 * scale)
            measured_tokens.append((t_type, t_val, w))
            total_w += w

    start_x = max(10, (canvas_width - total_w) // 2)
    gap = int(24 * scale)
    y_pos = int(top_margin_height - font_size - gap)

    curr_x = start_x
    for t_type, t_val, w in measured_tokens:
        if t_type == "text":
            draw.text((curr_x, y_pos), t_val, font=font, fill=(255, 255, 255, 240))
            curr_x += w
        else:
            hex_code = "-".join(f"{ord(c):x}" for c in t_val if ord(c) != 0xfe0f).lower()
            png_path = os.path.join(os.path.dirname(__file__), "emoji_assets", f"{hex_code}.png")
            if not os.path.exists(png_path):
                hex_code_single = f"{ord(t_val[0]):x}".lower()
                png_path = os.path.join(os.path.dirname(__file__), "emoji_assets", f"{hex_code_single}.png")
            if os.path.exists(png_path):
                try:
                    emoji_img = Image.open(png_path).convert("RGBA")
                    emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
                    e_y = y_pos + (font_size - emoji_size) // 2 + int(2 * scale)
                    img.paste(emoji_img, (curr_x, e_y), emoji_img)
                except Exception:
                    pass
            else:
                print(f"[Emoji Info] Missing local asset for {t_val} (hex: {hex_code})")
            curr_x += w

    img.save(output_png_path, "PNG")
    return output_png_path


def create_intro_overlay_image(
    intro_text: str,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    output_png_path: str = "intro_overlay.png"
) -> str:
    """
    Renders centered intro text supporting:
    1. {highlighted text}yellow syntax -> warm aesthetic yellow (#FFD43F)
    2. Default white text -> (255, 255, 255, 245)
    3. Inline Apple emojis composited from emoji_assets
    """
    img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    if not intro_text or not intro_text.strip():
        img.save(output_png_path, "PNG")
        return output_png_path

    draw = ImageDraw.Draw(img)
    scale = canvas_width / 1080.0
    font_size = int(36 * scale)
    font_paths = [
        "C:/Windows/Fonts/georgiai.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        os.path.join(os.path.dirname(__file__), "fonts", "CormorantGaramond-Italic.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "EBGaramond-Variable.ttf")
    ]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Parse spans for yellow highlights: e.g. {This Masterpiece>>>}yellow or (word)yellow
    span_pattern = re.compile(r'(?:\{([^}]+)\}|\(([^)]+)\))\s*yellow', re.IGNORECASE)
    chunks = []
    last_end = 0
    for m in span_pattern.finditer(intro_text):
        if m.start() > last_end:
            chunks.append((intro_text[last_end:m.start()], False))
        highlighted = m.group(1) or m.group(2) or ""
        chunks.append((highlighted, True))
        last_end = m.end()
    if last_end < len(intro_text):
        chunks.append((intro_text[last_end:], False))

    emoji_pattern = re.compile(
        r'([𐀀-􏿿][︀-️]?|[☀-➿][︀-️]?|❤[︀-️]?)'
    )
    tokens = []
    WHITE_COLOR = (255, 255, 255, 245)
    YELLOW_COLOR = (255, 212, 63, 255)

    for chunk_text, is_yellow in chunks:
        color = YELLOW_COLOR if is_yellow else WHITE_COLOR
        last_idx = 0
        for m in emoji_pattern.finditer(chunk_text):
            if m.start() > last_idx:
                txt_part = re.sub(r'[︀-️]', '', chunk_text[last_idx:m.start()])
                if txt_part:
                    tokens.append(("text", txt_part, color))
            tokens.append(("emoji", m.group(), color))
            last_idx = m.end()
        if last_idx < len(chunk_text):
            txt_part = re.sub(r'[︀-️]', '', chunk_text[last_idx:])
            if txt_part:
                tokens.append(("text", txt_part, color))

    emoji_size = int(font_size * 1.1)
    measured_tokens = []
    total_w = 0
    for t_type, t_val, color in tokens:
        if t_type == "text":
            bbox = draw.textbbox((0, 0), t_val, font=font)
            w = bbox[2] - bbox[0]
            measured_tokens.append((t_type, t_val, color, w))
            total_w += w
        else:
            w = emoji_size + int(6 * scale)
            measured_tokens.append((t_type, t_val, color, w))
            total_w += w

    start_x = max(10, (canvas_width - total_w) // 2)
    y_pos = int((canvas_height - font_size) // 2)

    curr_x = start_x
    for t_type, t_val, color, w in measured_tokens:
        if t_type == "text":
            draw.text((curr_x, y_pos), t_val, font=font, fill=color)
            curr_x += w
        else:
            hex_code = "-".join(f"{ord(c):x}" for c in t_val if ord(c) != 0xfe0f).lower()
            png_path = os.path.join(os.path.dirname(__file__), "emoji_assets", f"{hex_code}.png")
            if not os.path.exists(png_path):
                hex_code_single = f"{ord(t_val[0]):x}".lower()
                png_path = os.path.join(os.path.dirname(__file__), "emoji_assets", f"{hex_code_single}.png")
            if os.path.exists(png_path):
                try:
                    emoji_img = Image.open(png_path).convert("RGBA")
                    emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
                    emoji_y = y_pos - int(2 * scale)
                    img.paste(emoji_img, (curr_x, emoji_y), emoji_img)
                except Exception:
                    pass
            curr_x += w

    img.save(output_png_path, "PNG")
    return output_png_path


def create_lyric_line_overlay_image(
    text: str,
    rect_w: int = 1080,
    rect_h: int = 720,
    font_name: str = "EB Garamond",
    base_font_size: int = 50,
    output_png_path: str = "line_overlay.png"
) -> str:
    """
    Renders a single lyric line centered horizontally and vertically
    on a transparent RGBA image of size (rect_w, rect_h).
    Guarantees that the text NEVER exceeds 88% of the video rectangle width (950px on 1080p).
    """
    img = Image.new("RGBA", (rect_w, rect_h), (0, 0, 0, 0))
    if not text or not text.strip():
        img.save(output_png_path, "PNG")
        return output_png_path

    clean_text = text.strip()
    # Preserves natural casing or formats all-caps to sentence case
    letters = [c for c in clean_text if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(letters) > 3:
        clean_text = clean_text.capitalize()

    draw = ImageDraw.Draw(img)
    scale = rect_w / 1080.0
    target_font_size = int(base_font_size * scale)

    font_paths = [
        os.path.join(os.path.dirname(__file__), "fonts", "EBGaramond-Variable.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "CormorantGaramond-Regular.ttf"),
        "C:/Windows/Fonts/georgia.ttf"
    ]

    def get_font(size: int):
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    font = get_font(target_font_size)
    max_allowed_w = int(rect_w * 0.88)  # Safe 88% inner area (950px on 1080p)

    # Auto-scale font size down until text width <= max_allowed_w
    bbox = draw.textbbox((0, 0), clean_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    while text_w > max_allowed_w and target_font_size > int(20 * scale):
        target_font_size = max(int(20 * scale), int(target_font_size * (max_allowed_w / max(1, text_w)) * 0.98))
        font = get_font(target_font_size)
        bbox = draw.textbbox((0, 0), clean_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

    x_pos = (rect_w - text_w) // 2
    y_pos = (rect_h - text_h) // 2

    draw.text((x_pos, y_pos), clean_text, font=font, fill=(255, 255, 255, 255))
    img.save(output_png_path, "PNG")
    return output_png_path






def build_ass_and_lrc_content(
    cues: List[Tuple[float, float, str]],
    output_ass_path: str = "lyrics.ass",
    offset_seconds: float = 0.0,
    audio_duration: float = 180.0,
    aspect_ratio: str = "portrait",
    font_name: str = "Impact",
    font_size: Optional[int] = None,
    template_key: Optional[str] = "template1",
    placement: str = "center",
    y_percent: Optional[float] = 50.0,
    x_percent: Optional[float] = 50.0,
    brat_theme: str = "green",
    blur_amount: Optional[float] = None,
    spacing: Optional[int] = None,
    word_spacing: Optional[int] = None
) -> Tuple[str, List[Dict[str, Any]], str]:
    """
    Convert cues into ASS subtitle format configured with Template presets (1, 2, 3, 4 Brat),
    custom typography, dynamic reflow, and interactive dynamic placement (Center default).
    """
    tpl_id = (template_key or "").lower().strip()
    is_yt_hindi = tpl_id in ("yt_hindi_type", "yt_hindi_intro")
    if tpl_id in ["template4", "brat", "template_brat", "template4_brat", "template_4_brat"]:
        tpl = TEMPLATES["template4_brat"]
        is_brat = True
    elif is_yt_hindi:
        tpl = TEMPLATES.get(tpl_id, TEMPLATES["yt_hindi_type"])
        is_brat = False
    else:
        tpl = TEMPLATES.get(tpl_id, TEMPLATES["template1"])
        is_brat = False

    effective_aspect = aspect_ratio or tpl["aspect_ratio"]
    is_portrait = (effective_aspect.lower() == "portrait" or effective_aspect == "9:16")

    # Font handling
    if is_brat:
        effective_font = "Arial Narrow" if not font_name or font_name == "Impact" else font_name
    elif is_yt_hindi:
        effective_font = font_name if font_name and font_name != "Impact" else "EB Garamond"
    else:
        effective_font = font_name if font_name and font_name != "Impact" else tpl["font_name"]

    emit_progress("ass_start", 60, f"Step 2: Applying {tpl['name']} ({'Portrait 9:16' if is_portrait else 'Landscape 16:9'}) with '{placement}' placement...")

    if not cues:
        cues = [
            (2.0, max(6.0, audio_duration - 2.0), "[Music Playing - Native YouTube Audio]")
        ]

    # Configure canvas resolution & 1080p Normalization (Matches 360px Browser Preview 1:1)
    res_x = 1080 if is_portrait else 1920
    res_y = 1920 if is_portrait else 1080
    scale_factor = res_x / 360.0  # 3.0 for 1080x1920 portrait
    margin_l = int(res_x * 0.08)
    margin_r = int(res_x * 0.08)

    # Dynamic Placement configuration (Exact 1:1 Center Anchor with Live Layer)
    place_mode = (placement or "center").lower().strip()
    x_pos_val = float(x_percent) if x_percent is not None else 50.0
    y_pos_val = float(y_percent) if y_percent is not None else 50.0

    target_x = int(res_x * (x_pos_val / 100.0))
    target_y = int(res_y * (y_pos_val / 100.0))
    pos_override_tag = f"{{\\an5\\pos({target_x},{target_y})}}"
    alignment = 5
    margin_v = 0

    # Brat theme styling
    if is_brat:
        b_theme = BRAT_THEMES.get((brat_theme or "green").lower(), BRAT_THEMES["green"])
        primary_color = b_theme["text_color"]
        outline_color = b_theme.get("outline_color", "&H00000000")
        back_color = "&H00000000"
        bold_val = b_theme.get("bold", 0)
        scale_x_val = b_theme.get("scale_x", 68)
        raw_spacing = int(spacing) if spacing is not None else b_theme.get("spacing", -1)
        strikeout_val = b_theme.get("strikeout", 0)
        outline_width = int(b_theme.get("outline_width", 0) * scale_factor)
        shadow_depth = int(b_theme.get("shadow_depth", 0) * scale_factor)
        if b_theme.get("font_name"):
            effective_font = b_theme["font_name"]
    elif is_yt_hindi:
        primary_color = "&H00FFFFFF"
        outline_color = "&H00000000"
        back_color = "&H00000000"
        bold_val = 0
        scale_x_val = 100
        raw_spacing = int(spacing) if spacing is not None else 0
        strikeout_val = 0
        outline_width = 0
        shadow_depth = 0

    else:
        primary_color = tpl.get("primary_color", "&H00FFFFFF")
        outline_color = tpl.get("outline_color", "&H00000000")
        back_color = tpl.get("back_color", "&H80000000")
        bold_val = tpl.get("bold", -1)
        scale_x_val = tpl.get("scale_x", 100)
        raw_spacing = int(spacing) if spacing is not None else 0
        strikeout_val = 0
        outline_width = int(tpl.get("outline_width", 4) * scale_factor)
        shadow_depth = int(tpl.get("shadow_depth", 3) * scale_factor)

    raw_fs = font_size if font_size and font_size > 0 else (tpl.get("font_size") or 72)
    actual_font_size = int(raw_fs * scale_factor) if raw_fs <= 140 else int(raw_fs)
    spacing_val = int(raw_spacing * scale_factor)
    w_space_val = int((int(word_spacing) if word_spacing is not None else 0) * scale_factor)
    eff_blur = float((float(blur_amount) if (blur_amount is not None and blur_amount >= 0) else (tpl.get("blur") or 1.8)) * 8.5)

    def apply_word_spacing(txt: str, let_sp: int, wrd_sp: int) -> str:
        if not wrd_sp:
            return txt
        space_sub = f"{{\\fsp{let_sp + wrd_sp}}} {{\\fsp{let_sp}}}"
        return txt.replace(" ", space_sub)

    wrap_style = 2 if is_yt_hindi else 0
    ass_header = f"""[Script Info]
; Script generated by YouTube Lyric-Video Overlay Generator
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: {wrap_style}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{effective_font},{actual_font_size},{primary_color},&H000000FF,{outline_color},{back_color},{bold_val},0,0,{strikeout_val},{scale_x_val},100,{spacing_val},0,1,{outline_width},{shadow_depth},{alignment},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Flatten and sanitize cues into strictly 1 line per cue
    single_line_cues: List[Tuple[float, float, str]] = []
    for s_t, e_t, raw_t in cues:
        sub_lines = [l.strip() for l in raw_t.replace("\r", "\n").replace("\\N", "\n").split("\n") if l.strip()]
        if not sub_lines:
            continue
        if len(sub_lines) == 1:
            clean_l = " ".join(sub_lines[0].split())
            if clean_l:
                single_line_cues.append((s_t, e_t, clean_l))
        else:
            # Distribute multi-line cue into equal sub-segments
            n_sub = len(sub_lines)
            cue_dur = max(0.6, e_t - s_t)
            sub_dur = cue_dur / n_sub
            for sub_idx, sl in enumerate(sub_lines):
                c_sl = " ".join(sl.split())
                if c_sl:
                    sub_s = s_t + (sub_idx * sub_dur)
                    sub_e = s_t + ((sub_idx + 1) * sub_dur) if (sub_idx + 1) < n_sub else e_t
                    single_line_cues.append((sub_s, sub_e, c_sl))

    # Sort cues by start timestamp
    single_line_cues.sort(key=lambda x: x[0])

    dialogues = []
    structured_lines = []
    raw_lrc_lines = []

    def wrap_lyrics_multiline(text: str, max_chars: int = 11) -> str:
        words = text.split()
        if not words:
            return text
        lines = []
        current_line = []
        current_len = 0
        for w in words:
            w_len = len(w)
            if current_line and (current_len + 1 + w_len > max_chars):
                lines.append(" ".join(current_line))
                current_line = [w]
                current_len = w_len
            else:
                current_line.append(w)
                current_len += (1 if current_line else 0) + w_len
        if current_line:
            lines.append(" ".join(current_line))
        return r"\N".join(lines)

    for i, (start_t, end_t, text) in enumerate(single_line_cues):
        adjusted_start = max(0.0, start_t + offset_seconds)
        if is_yt_hindi and (i + 1 < len(single_line_cues)):
            next_start = max(0.0, single_line_cues[i + 1][0] + offset_seconds)
            adjusted_end = max(adjusted_start + 0.4, next_start)
        else:
            adjusted_end = max(adjusted_start + 0.5, end_t + offset_seconds)
        clean_text = text.replace("{", "\\{").replace("}", "\\}").replace("\n", " ").replace("\\N", " ").strip()

        if is_brat:
            is_upper = (brat_theme == "blue" or b_theme.get("uppercase", False))
            display_text = clean_text.upper() if is_upper else clean_text.lower()
            words = [w for w in display_text.split() if w.strip()]
            num_words = len(words)
            if num_words == 0:
                words = [display_text]
                num_words = 1

            line_dur = max(0.5, adjusted_end - adjusted_start)
            type_dur = min(line_dur * 0.85, max(0.4, num_words * 0.28))
            step_t = type_dur / num_words

            accumulated_words = []
            for w_idx in range(num_words):
                accumulated_words.append(words[w_idx])
                raw_text_string = " ".join(accumulated_words)
                wrapped_text = wrap_lyrics_multiline(raw_text_string, max_chars=11)
                text_string = apply_word_spacing(wrapped_text, spacing_val, w_space_val)
                
                w_start = adjusted_start + (w_idx * step_t)
                w_end = adjusted_start + ((w_idx + 1) * step_t) if (w_idx + 1) < num_words else adjusted_end

                brat_inline_tag = f"{{\\fs{actual_font_size}\\fsp{spacing_val}\\blur{eff_blur:.1f}}}"
                dlg_text = f"{pos_override_tag}{brat_inline_tag}{text_string}" if pos_override_tag else f"{brat_inline_tag}{text_string}"
                dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(w_start)},{seconds_to_ass_timestamp(w_end)},Default,,0,0,0,,{dlg_text}")
        elif is_yt_hindi:
            # YT Hindi Type: Preserves original casing or formats all-caps to sentence case
            letters = [c for c in clean_text if c.isalpha()]
            if letters and all(c.isupper() for c in letters) and len(letters) > 3:
                clean_text = clean_text.capitalize()

            # Dynamic scaling so the line ALWAYS fits on 1 single line
            line_len = len(clean_text)
            if line_len > 45:
                cur_fs = int(actual_font_size * 0.52)
            elif line_len > 32:
                cur_fs = int(actual_font_size * 0.62)
            elif line_len > 22:
                cur_fs = int(actual_font_size * 0.74)
            elif line_len > 14:
                cur_fs = int(actual_font_size * 0.86)
            else:
                cur_fs = actual_font_size


            wrapped_text = clean_text  # Never wrap, strictly 1 single centered line
            formatted_clean = apply_word_spacing(wrapped_text, spacing_val, w_space_val)
            fade_tag = r"{\fad(220,220)}"
            inline_tag = f"{{\\fs{cur_fs}\\fsp{spacing_val}}}"
            dialogue_text = f"{pos_override_tag}{fade_tag}{inline_tag}{formatted_clean}" if pos_override_tag else f"{fade_tag}{inline_tag}{formatted_clean}"
            dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(adjusted_start)},{seconds_to_ass_timestamp(adjusted_end)},Default,,0,0,0,,{dialogue_text}")


        else:
            wrapped_text = wrap_lyrics_multiline(clean_text, max_chars=22)
            formatted_clean = apply_word_spacing(wrapped_text, spacing_val, w_space_val)
            inline_tag = f"{{\\fs{actual_font_size}\\fsp{spacing_val}\\blur{eff_blur:.1f}}}"
            dialogue_text = f"{pos_override_tag}{inline_tag}{formatted_clean}" if pos_override_tag else f"{inline_tag}{formatted_clean}"
            dialogues.append(f"Dialogue: 0,{seconds_to_ass_timestamp(adjusted_start)},{seconds_to_ass_timestamp(adjusted_end)},Default,,0,0,0,,{dialogue_text}")

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
    emit_progress("ass_done", 70, f"Step 2: Applied {tpl['name']} ({len(dialogues)} word accumulation events, {res_x}x{res_y}, {place_mode}).")
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


def get_pillow_font(font_name: str, size: int):
    font_lower = (font_name or "").lower()
    candidates = []
    if "impact" in font_lower:
        candidates.append("C:/Windows/Fonts/impact.ttf")
    elif "narrow" in font_lower:
        candidates.extend(["C:/Windows/Fonts/ARIALN.TTF", "C:/Windows/Fonts/ARIALNB.TTF", "C:/Windows/Fonts/arial.ttf"])
    candidates.extend([
        f"C:/Windows/Fonts/{font_lower}.ttf",
        f"C:/Windows/Fonts/{font_lower}bd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeui.ttf"
    ])
    for c in candidates:
        if c and os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_exact_pillow_overlay_video(
    cues: List[Tuple[float, float, str]],
    audio_path: str,
    output_path: str,
    duration: float,
    aspect_ratio: str = "portrait",
    font_name: str = "Impact",
    font_size: Optional[int] = None,
    template_key: str = "template1",
    placement: str = "center",
    y_percent: float = 50.0,
    x_percent: float = 50.0,
    brat_theme: str = "green",
    blur_amount: float = 1.8,
    spacing: Optional[int] = None,
    word_spacing: Optional[int] = None
) -> str:
    """Renders 100% pixel-perfect Gaussian blur and word-by-word typography typing using Pillow rasterization and FFmpeg concat overlay."""
    is_portrait = (aspect_ratio.lower() == "portrait" or aspect_ratio == "9:16")
    res_w = 1080 if is_portrait else 1920
    res_h = 1920 if is_portrait else 1080

    tpl_id = (template_key or "").lower().strip()
    is_brat = tpl_id in ["template4", "brat", "template_brat", "template4_brat", "template_4_brat"]

    if is_brat:
        b_theme = BRAT_THEMES.get((brat_theme or "green").lower(), BRAT_THEMES["green"])
        bg_color = b_theme["bg_color"]
        fill_color_hex = b_theme.get("hex_text", "#000000")
        eff_font_name = b_theme.get("font_name", "Arial Narrow")
        is_upper = (brat_theme == "blue" or b_theme.get("uppercase", False))
        scale_x = 100 if brat_theme == "blue" else 68
    else:
        tpl = TEMPLATES.get(tpl_id, TEMPLATES["template1"])
        bg_color = tpl.get("bg_color", "black")
        fill_color_hex = "#FFFFFF"
        eff_font_name = font_name or "Impact"
        is_upper = False
        scale_x = 100

    hex_clean = fill_color_hex.lstrip("#")
    if len(hex_clean) == 6:
        r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
        fill_rgba = (r, g, b, 255)
    else:
        fill_rgba = (255, 255, 255, 255)

    fs_1080 = int((font_size or 72) * 3.0)
    font = get_pillow_font(eff_font_name, fs_1080)
    blur_rad = max(0.0, float(blur_amount or 1.8) * 3.5)

    target_x = int(res_w * (float(x_percent or 50.0) / 100.0))
    target_y = int(res_h * (float(y_percent or 50.0) / 100.0))

    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_cues_{int(time.time()*1000)}")
    os.makedirs(temp_dir, exist_ok=True)

    blank_img = Image.new("RGBA", (res_w, res_h), (0, 0, 0, 0))
    blank_png_path = os.path.join(temp_dir, "blank.png")
    blank_img.save(blank_png_path)

    def wrap_lines(txt, max_chars):
        words = txt.split()
        if not words:
            return []
        lines = []
        cur = []
        cur_l = 0
        for w in words:
            w_l = len(w)
            if cur and (cur_l + 1 + w_l > max_chars):
                lines.append(" ".join(cur))
                cur = [w]
                cur_l = w_l
            else:
                cur.append(w)
                cur_l += (1 if cur else 0) + w_l
        if cur:
            lines.append(" ".join(cur))
        return lines

    sorted_cues = []
    for s_t, e_t, raw_t in cues:
        clean_t = raw_t.strip()
        if clean_t:
            sorted_cues.append((max(0.0, float(s_t)), max(0.0, float(e_t)), clean_t))
    sorted_cues.sort(key=lambda x: x[0])

    concat_lines = []
    current_t = 0.0
    cue_img_idx = 0

    for s_t, e_t, clean_t in sorted_cues:
        if s_t > current_t:
            gap = s_t - current_t
            if gap > 0.02:
                concat_lines.append("file 'blank.png'")
                concat_lines.append(f"duration {gap:.3f}")
            current_t = s_t

        disp_text = clean_t.upper() if is_upper else (clean_t.lower() if is_brat else clean_t)
        
        if is_brat:
            words = [w for w in disp_text.split() if w.strip()]
            num_words = len(words)
            if num_words == 0:
                words = [disp_text]
                num_words = 1

            line_dur = max(0.4, e_t - s_t)
            type_dur = min(line_dur * 0.85, max(0.3, num_words * 0.28))
            step_t = type_dur / num_words

            acc_words = []
            for w_idx in range(num_words):
                acc_words.append(words[w_idx])
                raw_str = " ".join(acc_words)
                lines = wrap_lines(raw_str, 11)

                img = Image.new("RGBA", (res_w, res_h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                line_h = int(fs_1080 * 0.92)
                total_h = len(lines) * line_h
                start_y = int(target_y - (total_h / 2) + (line_h / 2))

                for l_idx, line in enumerate(lines):
                    y = start_y + (l_idx * line_h)
                    draw.text((target_x, y), line, font=font, fill=fill_rgba, anchor="mm", align="center")

                if scale_x < 100:
                    bbox = img.getbbox()
                    if bbox:
                        crop = img.crop(bbox)
                        new_w = max(1, int(crop.width * (scale_x / 100.0)))
                        resized = crop.resize((new_w, crop.height), Image.Resampling.BICUBIC)
                        img = Image.new("RGBA", (res_w, res_h), (0, 0, 0, 0))
                        paste_x = int(target_x - (new_w / 2))
                        paste_y = bbox[1]
                        img.paste(resized, (paste_x, paste_y), resized)

                if blur_rad > 0.1:
                    img = img.filter(ImageFilter.GaussianBlur(radius=blur_rad))

                cue_file = f"cue_{cue_img_idx:05d}.png"
                img.save(os.path.join(temp_dir, cue_file))
                cue_img_idx += 1

                w_dur = step_t if (w_idx + 1) < num_words else max(0.2, e_t - (s_t + (num_words - 1) * step_t))
                concat_lines.append(f"file '{cue_file}'")
                concat_lines.append(f"duration {w_dur:.3f}")
                current_t += w_dur
        else:
            lines = wrap_lines(disp_text, 22)
            img = Image.new("RGBA", (res_w, res_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            line_h = int(fs_1080 * 0.92)
            total_h = len(lines) * line_h
            start_y = int(target_y - (total_h / 2) + (line_h / 2))

            for l_idx, line in enumerate(lines):
                y = start_y + (l_idx * line_h)
                draw.text((target_x, y), line, font=font, fill=fill_rgba, anchor="mm", align="center")

            if blur_rad > 0.1:
                img = img.filter(ImageFilter.GaussianBlur(radius=blur_rad))

            cue_file = f"cue_{cue_img_idx:05d}.png"
            img.save(os.path.join(temp_dir, cue_file))
            cue_img_idx += 1

            dur = max(0.2, e_t - s_t)
            concat_lines.append(f"file '{cue_file}'")
            concat_lines.append(f"duration {dur:.3f}")
            current_t = e_t

    if duration > current_t:
        concat_lines.append("file 'blank.png'")
        concat_lines.append(f"duration {duration - current_t:.3f}")

    concat_lines.append("file 'blank.png'")

    manifest_path = os.path.join(temp_dir, "manifest.txt")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write("\n".join(concat_lines) + "\n")

    encoder_name, encoder_flags = detect_fastest_h264_encoder()

    cmd = [
        "ffmpeg", "-y", "-threads", "0",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={res_w}x{res_h}:r=30:d={duration:.2f}",
        "-f", "concat", "-safe", "0", "-i", manifest_path,
        "-i", audio_path,
        "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
        "-map", "[outv]",
        "-map", "2:a:0",
        "-c:v", encoder_name,
    ] + encoder_flags + [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        output_path
    ]

    try:
        subprocess.run(cmd, check=True)
    finally:
        for f in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass

    return output_path


def render_lyric_video_ffmpeg(
    audio_path: str,
    ass_path: str,
    output_path: str = "output_lyric_video.mp4",
    duration: Optional[float] = None,
    aspect_ratio: str = "portrait",
    bg_color: str = "black",
    is_brat: bool = False,
    blur_amount: Optional[float] = None,
    clean_base: bool = False
) -> str:
    """Step 3: Run FFmpeg to render clean base or ASS burned subtitles over MP4 video."""
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    is_portrait = (aspect_ratio.lower() == "portrait" or aspect_ratio == "9:16")
    res_str = "1080x1920" if is_portrait else "1920x1080"
    res_w = 1080 if is_portrait else 1920
    res_h = 1920 if is_portrait else 1080

    encoder_name, encoder_flags = detect_fastest_h264_encoder()
    mode_desc = "Clean Base Video" if clean_base else "Burned Subtitles Video"
    emit_progress("ffmpeg_start", 75, f"Step 3: Rendering {res_str} 30fps MP4 {mode_desc} using {encoder_name} (BG: {bg_color}, {duration:.1f}s)...")
    
    normalized_ass = ass_path.replace("\\", "/")
    if ":" in normalized_ass:
        normalized_ass = normalized_ass.replace(":", "\\:")

    eff_blur = float((float(blur_amount) if (blur_amount is not None and blur_amount >= 0) else (tpl.get("blur") or 1.8)) * 8.5)
    vf_filter = f"ass={normalized_ass}"

    if clean_base:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-threads", "0",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={res_str}:r=30:d={duration:.2f}",
            "-i", audio_path,
            "-c:v", encoder_name,
        ] + encoder_flags + [
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            output_path
        ]
    else:
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-threads", "0",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={res_str}:r=30:d={duration:.2f}",
            "-i", audio_path,
            "-vf", vf_filter,
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


def render_yt_hindi_video_ffmpeg(
    audio_path: str,
    ass_path: str,
    output_path: str = "output_lyric_video.mp4",
    duration: Optional[float] = None,
    top_header: Optional[str] = None,
    preview_quality: str = "final",
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
    cues: Optional[List[Any]] = None,
    film_burn_intro: bool = False,
    intro_header: Optional[str] = None,
    song_title: str = "",
) -> str:
    """
    Renders complete YT Hindi Type video where:
    1. Every lyric line has a distinct synced background video transition.
    2. The lyric text is merged directly onto the video clip segment first.
    3. Fade-in and fade-out are applied to the MERGED (video + text) segment simultaneously.
    4. All merged segments are concatenated into a seamless video stream.
    5. Top header is overlaid in the upper black margin.
    """
    if not duration or duration <= 0:
        duration = get_audio_duration(audio_path)

    is_fast = (preview_quality.lower() == "fast")
    res_w = 540 if is_fast else 1080
    res_h = 960 if is_fast else 1920
    fps = 24 if is_fast else 30
    rect_w = res_w
    rect_h = int(res_w * 720 / 1080)
    top_margin = (res_h - rect_h) // 2

    temp_dir = os.path.dirname(output_path) or "."
    header_png = None
    if not film_burn_intro:
        # Standard YT Hindi Type has top header throughout
        header_text = get_top_header_text(top_header)
        header_png = os.path.join(temp_dir, f"header_{int(time.time()*1000)}.png")
        create_header_overlay_image(
            header_text=header_text,
            canvas_width=res_w,
            canvas_height=res_h,
            top_margin_height=top_margin,
            output_png_path=header_png
        )

    intro_png = None
    chosen_overlay_video = None
    burn_dur = 3.0
    if film_burn_intro:
        # Intro variation: NO top header. Uses whole video from FILM OVERLAY/ + centered intro text.
        first_lyric_start = cues[0]["timeSeconds"] if cues and len(cues) > 0 and isinstance(cues[0], dict) else (cues[0][0] if cues and len(cues) > 0 else 3.0)
        burn_dur = min(4.0, first_lyric_start) if first_lyric_start >= 2.0 else 3.0
        intro_text = get_intro_header_text(intro_header, song_title=song_title, duration=duration or 0.0)
        intro_png = os.path.join(temp_dir, f"intro_{int(time.time()*1000)}.png")
        create_intro_overlay_image(
            intro_text=intro_text,
            canvas_width=res_w,
            canvas_height=res_h,
            output_png_path=intro_png
        )
        overlay_pool = get_all_film_overlays()
        if overlay_pool:
            chosen_overlay_video = random.choice(overlay_pool)
            print(f"[YT Hindi Intro] Selected film overlay video: {os.path.basename(chosen_overlay_video)}")

    encoder_name, encoder_flags = detect_fastest_h264_encoder()
    if is_fast:
        encoder_name = "libx264"
        encoder_flags = ["-preset", "ultrafast", "-crf", "26"]

    emit_progress("ffmpeg_start", 75, f"Step 3: Rendering YT Hindi Type {res_w}x{res_h} {fps}fps Video using {encoder_name} ({duration:.1f}s)...")

    transition_seconds = detect_tempo_transition_seconds(audio_path)
    emit_progress(
        "tempo_detected",
        76,
        f"Aubio tempo-adaptive transition: {transition_seconds:.2f}s",
    )

    # Build contiguous timeline segments synced to each lyric line:
    # [(seg_start, seg_dur, lyric_text, fade_out_st, fade_out_d)]
    #
    # The segments are concatenated below, so their durations must add up to
    # the output duration exactly.  Do not impose a per-line minimum here:
    # closely spaced cues are valid and a minimum would make the video drift
    # ahead of the audio.
    timeline_segments: List[Tuple[float, float, str, float, float]] = []
    if cues and len(cues) > 0:
        # Check intro gap before first lyric
        first_start = cues[0]["timeSeconds"] if isinstance(cues[0], dict) else cues[0][0]
        # Preserve even short leading silence; dropping it shifts every lyric
        # and transition earlier than the audio.
        if first_start > 0.001:
            intro_dur = min(duration, first_start)
            intro_fade_st = max(0.0, intro_dur - transition_seconds)
            timeline_segments.append((0.0, intro_dur, "", intro_fade_st, min(transition_seconds, intro_dur - intro_fade_st)))
        elif film_burn_intro:
            intro_dur = min(duration, 3.0)
            intro_fade_st = max(0.0, intro_dur - transition_seconds)
            timeline_segments.append((0.0, intro_dur, "", intro_fade_st, min(transition_seconds, intro_dur - intro_fade_st)))

        for idx, item in enumerate(cues):
            s_t = item["timeSeconds"] if isinstance(item, dict) else item[0]
            e_t = item["endSeconds"] if isinstance(item, dict) else item[1]
            txt = item.get("text", "") if isinstance(item, dict) else (item[2] if len(item) > 2 else "")
            if idx + 1 < len(cues):
                next_start = cues[idx + 1]["timeSeconds"] if isinstance(cues[idx + 1], dict) else cues[idx + 1][0]
                seg_end = next_start
            else:
                seg_end = duration

            # Keep every cue inside the rendered timeline and preserve the
            # exact interval up to the next cue.  The final cue ends at the
            # audio duration, so concatenation remains sample/timestamp aligned.
            s_t = max(0.0, min(duration, float(s_t)))
            seg_end = max(s_t, min(duration, float(seg_end)))
            seg_dur = seg_end - s_t
            if seg_dur <= 0.001:
                continue

            line_sing_dur = max(0.0, float(e_t) - float(s_t))

            # Start fading only after the sung portion. If less than 0.42s
            # remains, shorten the fade rather than moving it earlier.
            fade_out_st = min(seg_dur, line_sing_dur)
            fade_out_d = min(transition_seconds, max(0.0, seg_dur - fade_out_st))

            timeline_segments.append((s_t, seg_dur, txt, fade_out_st, fade_out_d))
    else:
        num_seg = max(1, math.ceil(duration / 5.0))
        seg_dur = duration / num_seg
        timeline_segments = [
            (i * seg_dur, seg_dur, "", max(0.0, seg_dur - transition_seconds), min(transition_seconds, seg_dur))
            for i in range(num_seg)
        ]

    all_bg_videos = get_all_background_videos()
    lyric_png_paths = []
    if all_bg_videos and timeline_segments:
        num_segments = len(timeline_segments)
        # If film_burn_intro, segment 0 is a pure black plain with NO background video
        clips_needed = (num_segments - 1) if (film_burn_intro and num_segments > 1) else num_segments
        selected_clips = []
        last_clip = None
        shuffled_pool = []
        for _ in range(max(1, clips_needed)):
            if not shuffled_pool:
                shuffled_pool = list(all_bg_videos)
                random.shuffle(shuffled_pool)
                if len(shuffled_pool) > 1 and shuffled_pool[-1] == last_clip:
                    swap_index = random.randrange(len(shuffled_pool) - 1)
                    shuffled_pool[-1], shuffled_pool[swap_index] = (
                        shuffled_pool[swap_index], shuffled_pool[-1]
                    )
            chosen = shuffled_pool.pop()
            selected_clips.append(chosen)
            last_clip = chosen

        print(f"[YT Hindi] Merging {num_segments} segments ({clips_needed} video clips, intro on black plain={film_burn_intro})")

        # Generate lyric text PNG overlay for each segment (skip intro segment if film_burn_intro)
        for i, (seg_start, seg_dur, seg_text, fade_out_st, fade_out_d) in enumerate(timeline_segments):
            if film_burn_intro and i == 0:
                continue
            eff_text = seg_text
            png_path = os.path.join(temp_dir, f"lyric_seg_{int(time.time()*1000)}_{i}.png")
            create_lyric_line_overlay_image(
                text=eff_text,
                rect_w=rect_w,
                rect_h=rect_h,
                font_name="EB Garamond",
                base_font_size=50,
                output_png_path=png_path
            )
            lyric_png_paths.append(png_path)

        video_inputs = []
        for clip_path in selected_clips:
            video_inputs.extend(["-stream_loop", "-1", "-i", clip_path])

        png_inputs = []
        for p in lyric_png_paths:
            png_inputs.extend(["-i", p])

        filter_parts = []
        video_clip_idx = 0
        lyric_png_idx = 0
        for i, (seg_start, seg_dur, seg_text, fade_out_st, fade_out_d) in enumerate(timeline_segments):
            fade_in_d = min(transition_seconds, seg_dur / 2.0)
            fade_filters = []
            if fade_out_d > 0.001:
                fade_filters.append(f"fade=t=out:st={fade_out_st:.3f}:d={fade_out_d:.3f}")

            if film_burn_intro and i == 0:
                # Segment 0 is 100% solid black plain. NO background video clip during intro.
                fade_str = ("," + ",".join(fade_filters)) if fade_filters else ""
                filter_parts.append(f"color=c=black:s={rect_w}x{rect_h}:r={fps}:d={seg_dur:.3f}{fade_str}[v0];")
            else:
                v_in_idx = video_clip_idx
                p_in_idx = len(selected_clips) + lyric_png_idx
                video_clip_idx += 1
                lyric_png_idx += 1

                # Scale video clip
                filter_parts.append(
                    f"[{v_in_idx}:v]trim=0:{seg_dur:.3f},setpts=PTS-STARTPTS,"
                    f"scale={rect_w}:{rect_h}:force_original_aspect_ratio=increase,"
                    f"crop={rect_w}:{rect_h},setsar=1,fps={fps}[bg{i}];"
                )
                # Merge lyric text directly onto the video clip first
                filter_parts.append(
                    f"[bg{i}][{p_in_idx}:v]overlay=0:0[merged{i}];"
                )
                # Apply fade in & fade out to the MERGED (video + text) segment
                f_list = [f"fade=t=in:st=0:d={fade_in_d:.3f}"] + fade_filters
                filter_parts.append(f"[merged{i}]" + ",".join(f_list) + f"[v{i}];")



        # Concatenate all merged segments
        concat_inputs = "".join(f"[v{i}]" for i in range(num_segments))
        filter_parts.append(f"{concat_inputs}concat=n={num_segments}:v=1:a=0[bg_rect];")
        filter_parts.append(f"[bg_rect]pad={res_w}:{res_h}:0:{top_margin}:color=black[canvas];")

        if film_burn_intro and intro_png:
            extra_inputs = []
            if chosen_overlay_video:
                ov_in_idx = len(selected_clips) + len(lyric_png_paths)
                intro_idx = ov_in_idx + 1
                audio_idx = ov_in_idx + 2
                extra_inputs.extend(["-stream_loop", "-1", "-i", chosen_overlay_video, "-i", intro_png])

                fade_out_burn = max(0.1, burn_dur - 0.42)
                # Scale film overlay to canvas, trim to burn_dur, fade out at end of intro
                filter_parts.append(
                    f"[{ov_in_idx}:v]trim=0:{burn_dur:.3f},setpts=PTS-STARTPTS,"
                    f"scale={res_w}:{res_h}:force_original_aspect_ratio=increase,"
                    f"crop={res_w}:{res_h},setsar=1,fps={fps},"
                    f"fade=t=out:st={fade_out_burn:.3f}:d=0.420[intro_film];"
                )
                filter_parts.append(
                    f"[canvas][intro_film]overlay=0:0:enable='between(t,0,{burn_dur:.3f})'[with_film];"
                )
                base_layer = "[with_film]"
            else:
                intro_idx = len(selected_clips) + len(lyric_png_paths)
                audio_idx = intro_idx + 1
                extra_inputs.extend(["-i", intro_png])
                base_layer = "[canvas]"

            # Intro text with smooth fade in and fade out (loop static image continuously)
            fade_in_d = min(0.5, burn_dur / 3.0)
            fade_out_st = max(0.4, burn_dur - 0.6)
            fade_out_d = min(0.5, burn_dur - fade_out_st)
            filter_parts.append(
                f"[{intro_idx}:v]format=rgba,loop=-1:1:0,fade=t=in:st=0.25:d={fade_in_d:.3f}:alpha=1,"
                f"fade=t=out:st={fade_out_st:.3f}:d={fade_out_d:.3f}:alpha=1[intro_txt];"
            )
            # Overlay intro text strictly during intro window. No top header is added.
            filter_parts.append(
                f"{base_layer}[intro_txt]overlay=0:0:enable='between(t,0,{burn_dur:.3f})'[v_out]"
            )

            extra_image_inputs = extra_inputs
        else:
            hdr_idx = 2 * num_segments
            audio_idx = 2 * num_segments + 1
            filter_parts.append(f"[canvas][{hdr_idx}:v]overlay=0:0[v_out]")
            extra_image_inputs = ["-i", header_png]

        filter_complex = "".join(filter_parts)

        ffmpeg_cmd = (
            ["ffmpeg", "-y", "-threads", "0"] +
            video_inputs +
            png_inputs +
            extra_image_inputs +
            ["-i", audio_path] +
            ["-filter_complex", filter_complex] +
            ["-map", "[v_out]", "-map", f"{audio_idx}:a"] +
            ["-t", f"{duration:.2f}", "-r", str(fps), "-c:v", encoder_name] +
            encoder_flags +
            ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
        )

    else:
        print(f"[YT Hindi] Notice: No background videos found in videos/input/. Using black background.")
        filter_complex = (
            f"[0:v][1:v]overlay=0:0[v_out]"
        )
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-threads", "0",
            "-f", "lavfi", "-i", f"color=c=black:s={res_w}x{res_h}:r={fps}:d={duration:.2f}",
            "-i", header_png,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[v_out]", "-map", "2:a",
            "-t", f"{duration:.2f}",
            "-r", str(fps),
            "-c:v", encoder_name,
        ] + encoder_flags + [
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]


    emit_progress("ffmpeg_rendering", 85, f"Hardware encoding {res_w}x{res_h} video with {encoder_name}...")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
    finally:
        for p in lyric_png_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        try:
            if header_png and os.path.exists(header_png):
                os.remove(header_png)
        except Exception:
            pass
        try:
            if intro_png and os.path.exists(intro_png):
                os.remove(intro_png)
        except Exception:
            pass


    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError(f"Rendered video {output_path} is missing or empty.")

    emit_progress("ffmpeg_done", 95, f"Video successfully rendered to '{output_path}'.")
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
    template: str = "template1",
    placement: str = "center",
    y_percent: Optional[float] = 50.0,
    x_percent: Optional[float] = 50.0,
    brat_theme: str = "green",
    blur_amount: Optional[float] = None,
    spacing: Optional[int] = None,
    word_spacing: Optional[int] = None,
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
    clean_base: bool = False,
    audio_file: Optional[str] = None,
    cues_file: Optional[str] = None,
    top_header: Optional[str] = None,
    preview_quality: str = "final",
    intro_header: Optional[str] = None
) -> Dict[str, Any]:
    """Main generator pipeline supporting Templates (1, 2, 3, 4 Brat, YT Hindi Type), Fonts, Languages, and Interactive Placement."""
    tpl_id = (template or "").lower().strip()
    is_yt_hindi = tpl_id in ("yt_hindi_type", "yt_hindi_intro")
    if tpl_id in ["template4", "brat", "template_brat", "template4_brat", "template_4_brat"]:
        tpl = TEMPLATES["template4_brat"]
        is_brat = True
        b_theme = BRAT_THEMES.get((brat_theme or "green").lower(), BRAT_THEMES["green"])
        bg_color = b_theme["bg_color"]
    elif is_yt_hindi:
        tpl = TEMPLATES.get(tpl_id, TEMPLATES["yt_hindi_type"])
        is_brat = False
        bg_color = "black"
    else:
        tpl = TEMPLATES.get(tpl_id, TEMPLATES["template1"])
        is_brat = False
        bg_color = tpl.get("bg_color", "black")

    effective_aspect = aspect_ratio or tpl["aspect_ratio"]
    effective_font = font_name if font_name and font_name != "Impact" else tpl["font_name"]

    emit_progress("init", 5, f"Initiating Generator with {tpl['name']} ({placement}, Lang: {lang})...")

    if audio_file and os.path.exists(audio_file):
        audio_path = audio_file
        duration = get_audio_duration(audio_path)
        cues = []
        if cues_file and os.path.exists(cues_file):
            try:
                with open(cues_file, "r", encoding="utf-8") as cf:
                    loaded = json.load(cf)
                    if isinstance(loaded, list):
                        for item in loaded:
                            if isinstance(item, dict) and "text" in item:
                                s_t = float(item.get("timeSeconds", 0.0))
                                e_t = float(item.get("endSeconds", s_t + 2.5))
                                cues.append((s_t, e_t, str(item["text"])))
                            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                                cues.append((float(item[0]), float(item[1]), str(item[2])))
            except Exception as e:
                print(f"[WARN] Error reading cues file: {e}", file=sys.stderr)
        yt_data = {
            "audio_path": audio_path,
            "duration": duration,
            "cues": cues,
            "title": song_query,
            "uploader": "YouTube Video"
        }
    else:
        yt_data = download_youtube_audio(
            query_or_url=song_query,
            output_audio_path=temp_audio_path,
            target_lang=lang
        )
        audio_path = yt_data["audio_path"]
        if is_yt_hindi:
            # The downloaded/converted audio is the timing authority for this
            # template. YouTube metadata can differ by padding or encoder
            # delay and cause the concatenated lyric timeline to drift.
            duration = get_audio_duration(audio_path) or yt_data["duration"]
        else:
            duration = yt_data["duration"]

    # If no usable lyrics found across all providers, stop before FFmpeg rendering
    if not yt_data.get("cues"):
        msg = "No usable lyrics found. Video generation stopped before FFmpeg rendering."
        emit_progress("no_lyrics_error", 100, msg)
        print(f"[Error] {msg}", file=sys.stderr)
        final_result = {
            "status": "error",
            "error": msg,
            "message": msg,
            "totalLines": 0,
            "syncedLines": []
        }
        return final_result

    # Restrict render to requested start_seconds and end_seconds window
    requested_start = max(0.0, float(start_seconds or 0.0))
    requested_end = float(end_seconds) if end_seconds is not None else None
    test_start = requested_start
    test_end = min(duration, requested_end if requested_end is not None else duration)
    if test_start > 0.0 or (requested_end is not None and test_end < duration):
        if test_end <= test_start:
            test_end = duration
        trim_dur = max(0.5, test_end - test_start)
        trimmed_audio = temp_audio_path.replace(".mp3", f"_trimmed_{int(test_start)}_{int(test_end)}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{test_start:.3f}", "-t", f"{trim_dur:.3f}",
            "-i", audio_path, "-c:a", "libmp3lame", "-b:a", "192k", trimmed_audio
        ], capture_output=True)
        if os.path.exists(trimmed_audio):
            audio_path = trimmed_audio
        
        # Shift and filter cues
        original_cues = yt_data["cues"]
        yt_data["cues"] = [
            (max(0.0, s - test_start), min(trim_dur, e - test_start), text)
            for s, e, text in original_cues
            if e > test_start and s < test_end
        ]
        duration = trim_dur
        emit_progress("test_range", 55, f"Rendering test window: {test_start:.1f}s to {test_end:.1f}s ({duration:.1f}s total)...")

    ass_path, structured_lines, raw_lrc = build_ass_and_lrc_content(
        cues=yt_data["cues"],
        output_ass_path=temp_ass_path,
        offset_seconds=offset_seconds,
        audio_duration=duration,
        aspect_ratio=effective_aspect,
        font_name=effective_font,
        font_size=font_size,
        template_key=template,
        placement=placement,
        y_percent=y_percent,
        x_percent=x_percent,
        brat_theme=brat_theme,
        blur_amount=blur_amount,
        spacing=spacing,
        word_spacing=word_spacing
    )

    if is_yt_hindi:
        render_yt_hindi_video_ffmpeg(
            audio_path=audio_path,
            ass_path=ass_path,
            output_path=output_path,
            duration=duration,
            top_header=top_header,
            preview_quality=preview_quality,
            start_seconds=test_start,
            end_seconds=test_end,
            cues=structured_lines,
            film_burn_intro=(tpl_id == "yt_hindi_intro"),
            intro_header=intro_header,
            song_title=yt_data.get("title") or song_query
        )

    elif clean_base:
        render_lyric_video_ffmpeg(
            audio_path=audio_path,
            ass_path=ass_path,
            output_path=output_path,
            duration=duration,
            aspect_ratio=effective_aspect,
            bg_color=bg_color,
            is_brat=is_brat,
            blur_amount=blur_amount,
            clean_base=True
        )
    else:
        try:
            render_exact_pillow_overlay_video(
                cues=yt_data["cues"],
                audio_path=audio_path,
                output_path=output_path,
                duration=duration,
                aspect_ratio=effective_aspect,
                font_name=effective_font,
                font_size=font_size,
                template_key=template,
                placement=placement,
                y_percent=y_percent,
                x_percent=x_percent,
                brat_theme=brat_theme,
                blur_amount=blur_amount or 1.8,
                spacing=spacing,
                word_spacing=word_spacing
            )
        except Exception as err:
            print(f"[WARN] Pillow overlay note: {err}. Falling back to ASS render.", file=sys.stderr)
            render_lyric_video_ffmpeg(
                audio_path=audio_path,
                ass_path=ass_path,
                output_path=output_path,
                duration=duration,
                aspect_ratio=effective_aspect,
                bg_color=bg_color,
                is_brat=is_brat,
                blur_amount=blur_amount,
                clean_base=False
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
        "brat_theme": brat_theme if is_brat else None,
        "bg_color": bg_color,
        "placement": placement,
        "y_percent": y_percent,
        "x_percent": x_percent,
        "blur_amount": blur_amount,
        "spacing": spacing,
        "word_spacing": word_spacing,
        "clean_base": clean_base,
        "language": yt_data.get("matched_lang", lang),
        "totalLines": len(structured_lines),
        "syncedLines": structured_lines,
        "rawLrc": raw_lrc
    }

    emit_progress("completed", 100, f"🎉 1080p MP4 ready using {tpl['name']} ({placement.upper()})!", final_result)
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
    placement = "center"
    ypos = 50.0
    xpos = 50.0
    blur = 3.6
    spacing = None
    word_spacing = None
    brat_theme = "green"
    start_seconds = 0.0
    end_seconds = None
    clean_base = False
    audio_file = None
    cues_file = None
    top_header = None
    intro_header = None
    preview_quality = "final"

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
        elif a.startswith("--placement="):
            placement = a.split("=")[1].strip()
        elif a.startswith("--ypos="):
            try:
                ypos = float(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--xpos="):
            try:
                xpos = float(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--blur="):
            try:
                blur = float(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--spacing="):
            try:
                spacing = int(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--word-spacing="):
            try:
                word_spacing = int(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--brat-theme="):
            brat_theme = a.split("=")[1].strip()
        elif a.startswith("--start-seconds="):
            try:
                start_seconds = float(a.split("=")[1])
            except ValueError:
                pass
        elif a.startswith("--end-seconds="):
            try:
                end_seconds = float(a.split("=")[1])
            except ValueError:
                pass
        elif a == "--clean-base" or a.startswith("--clean-base"):
            clean_base = True
        elif a.startswith("--audio-file="):
            audio_file = a.split("=")[1].strip()
        elif a.startswith("--cues-file="):
            cues_file = a.split("=")[1].strip()
        elif a.startswith("--top-header="):
            top_header = a.split("=")[1].strip()
        elif a.startswith("--intro-header="):
            intro_header = a.split("=")[1].strip()
        elif a.startswith("--preview-quality="):
            preview_quality = a.split("=")[1].strip()

    res = generate_lyric_video(
        song_query=query,
        output_path=out,
        offset_seconds=offset,
        aspect_ratio=aspect or "portrait",
        font_name=font or "Impact",
        font_size=size,
        lang=lang,
        template=template,
        placement=placement,
        y_percent=ypos,
        x_percent=xpos,
        brat_theme=brat_theme,
        blur_amount=blur,
        spacing=spacing,
        word_spacing=word_spacing,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        clean_base=clean_base,
        audio_file=audio_file,
        cues_file=cues_file,
        top_header=top_header,
        preview_quality=preview_quality,
        intro_header=intro_header
    )
    if JSON_MODE:
        print(f"__FINAL_RESULT__{json.dumps(res)}", flush=True)


