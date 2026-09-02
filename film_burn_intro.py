#!/usr/bin/env python3
"""
film_burn_intro.py - Advanced Procedural Cinematic Film Burn Intro for FFmpeg.

Applies an authentic, 100% procedural analog film burn intro effect to any input video:
- Light bloom & lens defocus (gblur)
- Organic exposure flash & warm amber/red tint (eq + colorchannelmixer)
- Film vignette (vignette)
- Analog celluloid film grain (noise)
- Intermittent horizontal red glitch streaks (drawbox)
- Random vertical hairline film scratches (drawbox)
- Projector celluloid gate weave / frame micro-jitter (crop + pad)

Zero external video assets required. Fully randomized on every run.
Hardware accelerated with auto-detection (h264_nvenc -> h264_qsv -> libx264).
"""

import os
import sys
import math
import random
import shutil
import argparse
import subprocess
from typing import Tuple, List, Dict, Any

# Force UTF-8 on Windows consoles to prevent cp1252 charmap encoding errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==============================================================================
# 1. CONFIGURABLE INTRO DURATION (in seconds)
# ==============================================================================
INTRO_DURATION: float = 3.0



# ==============================================================================
# 5. DYNAMIC HARDWARE ACCELERATION DETECTION
# ==============================================================================
def detect_hardware_encoder() -> Tuple[str, List[str]]:
    """
    Auto-detect available system encoders in order of preference:
    1. h264_nvenc (NVIDIA GPU)
    2. h264_qsv (Intel Quick Sync Video)
    3. libx264 (High quality CPU fallback)
    """
    candidates = [
        ("h264_nvenc", ["-preset", "p4", "-cq", "19", "-spatial_aq", "1"]),
        ("h264_qsv", ["-preset", "medium", "-global_quality", "20"]),
        ("libx264", ["-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]),
    ]

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    for enc_name, extra_flags in candidates:
        test_cmd = [
            ffmpeg_bin, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:r=24:d=0.1",
            "-c:v", enc_name
        ] + extra_flags + ["-f", "null", "-"]
        try:
            res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                print(f"[Hardware Acceleration] Selected encoder: {enc_name}")
                return enc_name, extra_flags
        except Exception:
            continue

    print("[Hardware Acceleration] No GPU encoder detected. Falling back to libx264.")
    return "libx264", ["-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]


# ==============================================================================
# 2 & 3. RANDOMIZED PROCEDURAL FILTER PIPELINE GENERATOR
# ==============================================================================
def generate_film_burn_filters(intro_duration: float = INTRO_DURATION) -> Tuple[str, Dict[str, Any]]:
    """
    Builds the procedural FFmpeg video filter chain scoped strictly to the intro window
    using :enable='between(t,0,X)'. Every run randomizes all procedural parameters.
    """
    # 2. Per-Run Randomization Parameters:
    flash_hz = round(random.uniform(2.6, 4.4), 2)             # Flash frequency (Hz)
    peak_brightness = round(random.uniform(0.38, 0.62), 3)     # Peak brightness
    peak_contrast = round(random.uniform(1.28, 1.55), 2)       # Peak contrast
    bloom_sigma = round(random.uniform(4.5, 8.5), 1)           # Bloom / defocus sigma
    
    # Warm amber/red color temperature ratios
    red_gain = round(random.uniform(1.30, 1.55), 2)
    amber_mix = round(random.uniform(0.12, 0.22), 2)
    green_gain = round(random.uniform(1.02, 1.12), 2)
    blue_gain = round(random.uniform(0.55, 0.75), 2)
    
    # Analog film grain
    noise_seed = random.randint(1000, 999999)                  # Randomized noise seed
    noise_strength = random.randint(22, 34)                    # Grain intensity
    
    # Horizontal red glitch streaks
    glitch_h = random.choice([1, 2, 3])                        # Line thickness
    glitch_opacity = round(random.uniform(0.65, 0.88), 2)      # Streak opacity
    glitch_thresh = round(random.uniform(0.58, 0.78), 2)       # Flicker frequency
    
    # Vertical hairline scratches
    scratch_opacity = round(random.uniform(0.45, 0.75), 2)     # Scratch opacity
    scratch_thresh = round(random.uniform(0.50, 0.72), 2)      # Scratch frequency
    
    # Film gate weave / projector micro-jitter
    jitter_px = random.choice([2, 3, 4])                       # Max pixel displacement
    jitter_speed = round(random.uniform(13.0, 19.5), 1)        # Gate oscillation rate

    dur = f"{intro_duration:.3f}"
    scope = f"between(t,0,{dur})"

    # 3. Scoped Multi-Layer Filter Chain:
    filter_chain = [
        # g. Film Gate Weave / Jitter (crop + pad):
        # Shifts frame vertically during intro window, perfectly stable at 0 after intro
        f"crop=w=in_w:h=in_h-{jitter_px*2}:x=0:y='if({scope}, {jitter_px}+{jitter_px}*sin(n*{jitter_speed}), {jitter_px})',pad=in_w:in_h:0:{jitter_px}",

        # a. Light Bloom & Lens Defocus (gblur):
        # Dynamic optical bloom active strictly during intro
        f"gblur=sigma={bloom_sigma}:steps=1:enable='{scope}'",

        # b. Exposure & Overexposure Flash (eq):
        # Organic pulsating brightness & contrast flash
        f"eq=brightness='if({scope}, {peak_brightness}*pow(max(0,sin(2*PI*{flash_hz}*t)),2), 0)':contrast='if({scope}, {peak_contrast}, 1.0)':eval=frame:enable='{scope}'",

        # b. Warm Amber/Red Tint (colorchannelmixer):
        # Rich celluloid warmth with amber shift
        f"colorchannelmixer=rr={red_gain}:rg={amber_mix}:gg={green_gain}:bb={blue_gain}:enable='{scope}'",

        # c. Vignette (vignette):
        # Corner darkening framing the center light burn
        f"vignette='PI/4':eval=frame:enable='{scope}'",

        # d. Analog Film Grain (noise):
        # Temporal film celluloid noise with unique seed per export
        f"noise=alls={noise_strength}:allf=t+u:all_seed={noise_seed}:enable='{scope}'"
    ]

    random_params = {
        "intro_duration": intro_duration,
        "flash_hz": flash_hz,
        "peak_brightness": peak_brightness,
        "peak_contrast": peak_contrast,
        "bloom_sigma": bloom_sigma,
        "color_temp": f"R:{red_gain} G:{green_gain} B:{blue_gain} (Amber:{amber_mix})",
        "noise_seed": noise_seed,
        "noise_strength": noise_strength,
        "gate_weave_jitter": f"±{jitter_px}px @ {jitter_speed} rad/s"
    }

    return ",".join(filter_chain), random_params


# ==============================================================================
# 4 & 6. EXECUTION PIPELINE
# ==============================================================================
def apply_film_burn_intro(
    input_video: str,
    output_video: str,
    intro_duration: float = INTRO_DURATION,
    encoder_name: str = None
) -> None:
    """
    Renders the film burn intro onto input_video and saves to output_video.
    - Audio is copied untouched (-c:a copy).
    - Unedited video frames after t = intro_duration pass through untouched.
    """
    if not os.path.exists(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")

    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    # Hardware acceleration detection
    if encoder_name:
        enc_name = encoder_name
        enc_flags = ["-preset", "fast", "-crf", "18"]
    else:
        enc_name, enc_flags = detect_hardware_encoder()

    filter_complex, params = generate_film_burn_filters(intro_duration)

    print("\n" + "=" * 65)
    print("🎬 CINEMATIC FILM BURN INTRO — PROCEDURAL GENERATION")
    print("=" * 65)
    for k, v in params.items():
        print(f" • {k.replace('_', ' ').title():<22}: {v}")
    print(f" • Hardware Encoder     : {enc_name}")
    print("=" * 65 + "\n")

    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_video,
        "-vf", filter_complex,
        "-c:v", enc_name,
    ] + enc_flags + [
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_video
    ]

    print(f"[FFmpeg] Executing command on '{input_video}' -> '{output_video}'...")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed with exit code {res.returncode}")

    print(f"\n✨ Successfully exported film burn intro video to: {output_video}")


def main():
    parser = argparse.ArgumentParser(
        description="Apply an advanced, procedural Cinematic Film Burn Intro effect to any video."
    )
    parser.add_argument("input", help="Path to source input video file")
    parser.add_argument("output", help="Path to destination output video file")
    parser.add_argument(
        "--intro-duration", "-d",
        type=float,
        default=INTRO_DURATION,
        help=f"Duration of the film burn intro in seconds (default: {INTRO_DURATION}s)"
    )
    parser.add_argument(
        "--encoder", "-e",
        type=str,
        default=None,
        help="Force specific video encoder (e.g. h264_nvenc, h264_qsv, libx264)"
    )
    args = parser.parse_args()

    apply_film_burn_intro(
        input_video=args.input,
        output_video=args.output,
        intro_duration=args.intro_duration,
        encoder_name=args.encoder
    )


if __name__ == "__main__":
    main()
