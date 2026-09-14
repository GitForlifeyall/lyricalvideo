"""Spotify-style lyric carousel renderer.

Creates one PNG slide per lyric line from a JSON or CSV source. This module is
deliberately independent from the video templates in ``generator.py``.

Examples:
    .venv310\Scripts\python.exe carousel_renderer.py examples/carousel_input.json output/carousel --format 4:5
    .venv310\Scripts\python.exe carousel_renderer.py songs.csv output/stories --format 9:16 --workers 4
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont


RGB = Tuple[int, int, int]
CANVAS_SIZES = {"4:5": (1080, 1350), "9:16": (1080, 1920)}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class CarouselInputError(ValueError):
    """Raised when the input source cannot be converted to carousel data."""


@dataclass(frozen=True)
class SongData:
    title: str
    artist: str
    lyrics_lines: List[str]
    album_cover: Optional[str] = None


@dataclass(frozen=True)
class CarouselConfig:
    aspect_ratio: str = "4:5"
    workers: int = 1
    card_radius: int = 38
    card_padding: int = 50

    @property
    def canvas_size(self) -> Tuple[int, int]:
        try:
            return CANVAS_SIZES[self.aspect_ratio]
        except KeyError as error:
            raise CarouselInputError(
                f"Unsupported format '{self.aspect_ratio}'. Use one of: {', '.join(CANVAS_SIZES)}."
            ) from error


def _first_value(data: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _coerce_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(line).strip() for line in value if str(line).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            decoded = json.loads(stripped)
            if isinstance(decoded, list):
                return _coerce_lines(decoded)
        except json.JSONDecodeError:
            pass
        return [line.strip() for line in stripped.split("|") if line.strip()]
    return []


def song_data_from_mapping(data: Dict[str, Any]) -> SongData:
    """Accept common JSON field names without requiring a rigid envelope."""
    nested_song = data.get("song")
    merged = {**nested_song, **data} if isinstance(nested_song, dict) else data
    lyrics = _coerce_lines(merged.get("lyrics_lines") or merged.get("lyrics"))
    if not lyrics:
        raise CarouselInputError("Input must include a non-empty 'lyrics_lines' array.")
    return SongData(
        title=_first_value(merged, ("song_title", "title", "track_name", "track"), "Unknown song"),
        artist=_first_value(merged, ("artist_name", "artist", "artists"), "Unknown artist"),
        album_cover=_first_value(
            merged, ("album_cover", "album_cover_url", "cover_url", "cover", "artwork_url")
        ) or None,
        lyrics_lines=lyrics,
    )


def load_song_data(input_path: str | Path) -> SongData:
    """Load JSON or CSV input and normalize it to ``SongData``.

    CSV accepts a JSON/pipe-separated ``lyrics_lines`` value, or one lyric per
    row in ``lyric_line``, ``lyrics_line``, ``text``, or ``lyric``.
    """
    source = Path(input_path)
    if not source.exists():
        raise CarouselInputError(f"Input file does not exist: {source}")
    try:
        if source.suffix.lower() == ".json":
            with source.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            if isinstance(payload, list):
                if not payload:
                    raise CarouselInputError("JSON input array is empty.")
                first = dict(payload[0])
                first["lyrics_lines"] = [
                    _first_value(row, ("lyric_line", "lyrics_line", "text", "lyric"))
                    for row in payload if isinstance(row, dict)
                ]
                return song_data_from_mapping(first)
            if not isinstance(payload, dict):
                raise CarouselInputError("JSON input must be an object or an array of lyric rows.")
            return song_data_from_mapping(payload)
        if source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            if not rows:
                raise CarouselInputError("CSV input has no data rows.")
            first = dict(rows[0])
            explicit_lines = _coerce_lines(first.get("lyrics_lines") or first.get("lyrics"))
            row_lines = [_first_value(row, ("lyric_line", "lyrics_line", "text", "lyric")) for row in rows]
            first["lyrics_lines"] = explicit_lines or [line for line in row_lines if line]
            return song_data_from_mapping(first)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as error:
        raise CarouselInputError(f"Could not read input '{source.name}': {error}") from error
    raise CarouselInputError("Input must be a .json or .csv file.")


def _clamp(value: float) -> int:
    return max(0, min(255, round(value)))


def _blend(base: RGB, overlay: RGB, overlay_alpha: float) -> RGB:
    return tuple(_clamp(a * (1.0 - overlay_alpha) + b * overlay_alpha) for a, b in zip(base, overlay))  # type: ignore[return-value]


def _luminance(color: RGB) -> float:
    return (0.2126 * color[0]) + (0.7152 * color[1]) + (0.0722 * color[2])


def dominant_color(image: Image.Image) -> RGB:
    """Return the most frequent representative album-art color."""
    sample = image.convert("RGB").resize((80, 80), Image.Resampling.LANCZOS)
    palette = sample.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    colors = palette.getcolors() or []
    if not colors:
        return (93, 93, 93)
    _, index = max(colors, key=lambda item: item[0])
    palette_data = palette.getpalette()
    offset = index * 3
    return tuple(palette_data[offset:offset + 3])  # type: ignore[return-value]


def card_tint(background: RGB) -> RGB:
    target = (255, 255, 255) if _luminance(background) < 132 else (0, 0, 0)
    return _blend(background, target, 0.13)


def _fallback_cover(size: int = 512) -> Image.Image:
    image = Image.new("RGB", (size, size), (45, 45, 45))
    draw = ImageDraw.Draw(image)
    draw.ellipse((size * 0.18, size * 0.18, size * 0.82, size * 0.82), fill=(95, 95, 95))
    draw.rectangle((size * 0.45, size * 0.28, size * 0.55, size * 0.70), fill=(25, 25, 25))
    return image


def load_album_cover(location: Optional[str], timeout_seconds: float = 10.0) -> Image.Image:
    """Load a local or remote cover, returning a safe fallback on failure."""
    if not location:
        return _fallback_cover()
    try:
        if location.startswith(("https://", "http://")):
            response = requests.get(location, timeout=timeout_seconds, headers={"User-Agent": "LyricCarousel/1.0"})
            response.raise_for_status()
            with Image.open(io.BytesIO(response.content)) as cover:
                return cover.convert("RGB").copy()
        local_path = Path(location)
        if local_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise CarouselInputError("Album cover must be a supported image file.")
        with Image.open(local_path) as cover:
            return cover.convert("RGB").copy()
    except (requests.RequestException, OSError, ValueError, CarouselInputError) as error:
        print(f"[carousel] Album cover unavailable ({error}); using generated fallback art.")
        return _fallback_cover()


class FontBook:
    """Caches platform-aware typefaces shared by all generated slides."""

    def __init__(self) -> None:
        root = Path(__file__).resolve().parent
        self.bold_candidates = [Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/seguisb.ttf"), root / "fonts" / "EBGaramond-Variable.ttf"]
        self.regular_candidates = [Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/segoeui.ttf"), root / "fonts" / "EBGaramond-Variable.ttf"]
        self._cache: Dict[Tuple[bool, int], ImageFont.ImageFont] = {}

    def get(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        key = (bold, size)
        if key in self._cache:
            return self._cache[key]
        for candidate in self.bold_candidates if bold else self.regular_candidates:
            if candidate.exists():
                try:
                    font = ImageFont.truetype(str(candidate), size)
                    self._cache[key] = font
                    return font
                except OSError:
                    continue
        font = ImageFont.load_default()
        self._cache[key] = font
        return font


def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *size), radius=radius, fill=255)
    return mask


def _cover_thumbnail(cover: Image.Image, size: int = 110) -> Image.Image:
    copy = cover.copy()
    copy.thumbnail((size, size), Image.Resampling.LANCZOS)
    thumb = Image.new("RGB", (size, size), (30, 30, 30))
    thumb.paste(copy, ((size - copy.width) // 2, (size - copy.height) // 2))
    thumb.putalpha(_rounded_mask((size, size), 14))
    return thumb


def _measure_lines(draw: ImageDraw.ImageDraw, lines: Sequence[str], font: ImageFont.ImageFont, spacing: int) -> int:
    if not lines:
        return 0
    return sum(max(0, draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1]) for line in lines) + spacing * (len(lines) - 1)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    lines: List[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
            while draw.textlength(current, font=font) > max_width and len(current) > 1:
                split_at = len(current) - 1
                while split_at > 1 and draw.textlength(current[:split_at], font=font) > max_width:
                    split_at -= 1
                lines.append(current[:split_at])
                current = current[split_at:]
        if current:
            lines.append(current)
    return lines


def _fitted_lyrics(draw: ImageDraw.ImageDraw, text: str, fonts: FontBook, max_width: int, max_height: int) -> Tuple[ImageFont.ImageFont, List[str], int]:
    for size in range(66, 29, -2):
        font = fonts.get(size, bold=True)
        spacing = max(10, int(size * 0.20))
        lines = _wrap_text(draw, text, font, max_width)
        if _measure_lines(draw, lines, font, spacing) <= max_height:
            return font, lines, spacing
    font = fonts.get(30, bold=True)
    return font, _wrap_text(draw, text, font, max_width), 10


def _draw_spotify_badge(draw: ImageDraw.ImageDraw, x: int, y: int, color: RGB, fonts: FontBook) -> None:
    """Draw a compact vector-style Spotify badge without an external asset."""
    radius = 26
    draw.ellipse((x, y, x + radius * 2, y + radius * 2), fill=color)
    line_color = (255, 255, 255) if _luminance(color) < 140 else (0, 0, 0)
    for index, offset in enumerate((15, 24, 33)):
        inset = 10 + index * 2
        draw.arc((x + inset, y + offset - 10, x + radius * 2 - inset + 3, y + offset + 8), 200, 340, fill=line_color, width=3)
    draw.text((x + 62, y + 3), "Spotify", font=fonts.get(32, bold=True), fill=color)


class CarouselRenderer:
    """Renders a consistent slide set while varying only the lyric text."""

    def __init__(self, song: SongData, config: CarouselConfig) -> None:
        self.song = song
        self.config = config
        self.width, self.height = config.canvas_size
        self.cover = load_album_cover(song.album_cover)
        self.background = dominant_color(self.cover)
        self.card_color = _blend(self.background, card_tint(self.background), 0.90)
        self.text_color = (0, 0, 0) if _luminance(self.card_color) > 150 else (255, 255, 255)
        self.fonts = FontBook()
        self.card_width = min(900, self.width - 120)
        self.card_height = 630 if self.config.aspect_ratio == "4:5" else 700
        self.card_x = (self.width - self.card_width) // 2
        self.card_y = (self.height - self.card_height) // 2
        self.thumbnail = _cover_thumbnail(self.cover)

    def _slide_image(self, lyric: str) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height), self.background)
        draw = ImageDraw.Draw(image)
        card_box = (self.card_x, self.card_y, self.card_x + self.card_width, self.card_y + self.card_height)
        draw.rounded_rectangle(card_box, radius=self.config.card_radius, fill=self.card_color)
        px, py = self.card_x + self.config.card_padding, self.card_y + self.config.card_padding
        image.paste(self.thumbnail, (px, py), self.thumbnail)
        title_x = px + 140
        title_font, artist_font = self.fonts.get(30, bold=True), self.fonts.get(26)
        title = self.song.title
        while draw.textlength(title, font=title_font) > self.card_width - 220 and len(title) > 3:
            title = title[:-2].rstrip() + "…"
        draw.text((title_x, py + 9), title, font=title_font, fill=self.text_color)
        draw.text((title_x, py + 50), self.song.artist, font=artist_font, fill=self.text_color)
        lyrics_y = py + 190
        footer_y = self.card_y + self.card_height - self.config.card_padding - 55
        lyric_font, lyric_lines, spacing = _fitted_lyrics(
            draw, lyric, self.fonts, self.card_width - (self.config.card_padding * 2), footer_y - lyrics_y - 45
        )
        draw.multiline_text((px, lyrics_y), "\n".join(lyric_lines), font=lyric_font, fill=self.text_color, spacing=spacing)
        _draw_spotify_badge(draw, px, footer_y, self.text_color, self.fonts)
        return image

    def render(self, output_dir: str | Path) -> List[Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        count = len(self.song.lyrics_lines)
        index_width = max(2, len(str(count)))

        def render_one(item: Tuple[int, str]) -> Path:
            index, lyric = item
            path = output / f"slide_{index:0{index_width}d}.png"
            # Normal PNG compression is markedly faster than Pillow's
            # exhaustive optimize pass and preserves the same pixels.
            self._slide_image(lyric).save(path, format="PNG", compress_level=6)
            return path

        items = list(enumerate(self.song.lyrics_lines, start=1))
        workers = max(1, min(self.config.workers, count))
        if workers == 1:
            return [render_one(item) for item in items]
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="carousel") as pool:
            return list(pool.map(render_one, items))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Spotify-style lyric carousel slides from JSON or CSV.")
    parser.add_argument("input", help="Path to a .json or .csv input source")
    parser.add_argument("output", help="Folder for generated slide_XX.png images")
    parser.add_argument("--format", dest="aspect_ratio", choices=tuple(CANVAS_SIZES), default="4:5")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent slide workers (default: 1)")
    args = parser.parse_args()
    try:
        song = load_song_data(args.input)
        renderer = CarouselRenderer(song, CarouselConfig(aspect_ratio=args.aspect_ratio, workers=max(1, args.workers)))
        paths = renderer.render(args.output)
    except CarouselInputError as error:
        parser.error(str(error))
        return 2
    except Exception as error:
        print(f"[carousel] Rendering failed: {error}")
        return 1
    print(f"[carousel] Rendered {len(paths)} slide(s) to {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
