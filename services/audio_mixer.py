"""
audio_mixer.py — Basic audio mixing via FFmpeg.

Mixes a vocal track (TTS MP3) with an instrumental (WAV/MP3) using
FFmpeg's amix filter. Returns mixed bytes or None if FFmpeg unavailable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def mix_vocal_with_instrumental(
    vocal_bytes: bytes,
    instrumental_path: str,
    vocal_vol: float = 1.0,
    inst_vol: float = 0.85,
) -> Optional[bytes]:
    """
    Mix vocal (bytes) with instrumental file on disk.

    Pipeline:
      - Normalize both inputs independently (loudnorm)
      - Vocal: +2 dB boost for presence
      - Instrumental: -3 dB duck to let vocals sit on top
      - amix with dropout_transition for clean fade behaviour
      - Output: 192kbps MP3 (demo quality)
    """
    if not is_ffmpeg_available():
        print("[MIXER] FFmpeg not found — mixing skipped.", flush=True)
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            vocal_path = os.path.join(tmp, "vocal.mp3")
            out_path   = os.path.join(tmp, "mixed.mp3")
            Path(vocal_path).write_bytes(vocal_bytes)

            # vocal_vol=1.0 → +2 dB (1.259); inst_vol=0.85 → -3 dB (0.708)
            v_db = vocal_vol * 1.259   # +2 dB on top of caller's multiplier
            i_db = inst_vol  * 0.708   # -3 dB on top of caller's multiplier

            filter_complex = (
                # Normalize vocal loudness
                f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,volume={v_db:.3f}[v];"
                # Normalize instrumental loudness, then duck it
                f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,volume={i_db:.3f}[i];"
                # Mix — longest duration, smooth 2s fade on dropout
                "[v][i]amix=inputs=2:duration=longest:dropout_transition=2[out]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", vocal_path,
                "-i", instrumental_path,
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-codec:a", "libmp3lame",
                "-b:a", "192k",
                out_path,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                err = result.stderr[-400:].decode(errors='replace')
                print(f"[MIXER] FFmpeg failed: {err}", flush=True)
                return None

            mixed = Path(out_path).read_bytes()
            print(f"[MIXER] Mix complete: {len(mixed):,} bytes", flush=True)
            return mixed

    except subprocess.TimeoutExpired:
        print("[MIXER] FFmpeg timed out.", flush=True)
        return None
    except Exception as e:
        print(f"[MIXER] Exception: {e}", flush=True)
        return None


def mix_vocal_with_instrumental_bytes(
    vocal_bytes: bytes,
    instrumental_bytes: bytes,
    ext: str = ".wav",
    vocal_vol: float = 1.0,
    inst_vol: float = 0.85,
) -> Optional[bytes]:
    """
    Mix both vocal and instrumental from bytes (no pre-existing file needed).
    """
    if not is_ffmpeg_available():
        print("[MIXER] FFmpeg not found — mixing skipped.", flush=True)
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            inst_path  = os.path.join(tmp, f"inst{ext}")
            Path(inst_path).write_bytes(instrumental_bytes)
            return mix_vocal_with_instrumental(vocal_bytes, inst_path, vocal_vol, inst_vol)
    except Exception as e:
        print(f"[MIXER] Exception in bytes mix: {e}", flush=True)
        return None
