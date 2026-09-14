"""Fetch carousel metadata and synced lyrics without downloading audio."""

import json
import sys

from generator import (
    fetch_lrclib_lyrics,
    fetch_spotify_lyrics,
    fetch_spotify_track_metadata,
)


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print(json.dumps({"error": "A Spotify link or song query is required"}))
        return 2

    metadata = fetch_spotify_track_metadata(query)
    title = metadata.get("title") or query
    artist = metadata.get("artists") or ""
    duration = float(metadata.get("duration") or 0.0)

    cues, source = fetch_spotify_lyrics(query, artist, duration)
    if not cues:
        cues, source = fetch_lrclib_lyrics(title, artist, duration)

    lines = [
        {"index": index, "start": start, "end": end, "text": text}
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    print(json.dumps({
        "title": title,
        "artist": artist,
        "cover_url": metadata.get("cover_url") or "",
        "source": source,
        "lines": lines,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
