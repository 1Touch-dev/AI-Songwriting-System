"""
audio_mixer.py — Vocal + instrumental mixer via FFmpeg.

Strategy:
  - Mix duration = vocal length (not instrumental length).
    The vocal defines the song — no 2-minute instrumental tail after it ends.
  - Instrumental trimmed to vocal duration, then a 3-second fade-out applied.
  - Simple volume scaling (no loudnorm — avoids latency/timing issues):
      vocal     × 1.0  (clean TTS voice at its natural level)
      instrumental × 0.55  (~−5 dB duck so voice sits clearly on top)
  - Output: 192 kbps MP3
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


def _get_duration(path: str) -> float:
    """Return audio duration in seconds via ffprobe, or 0.0 on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def mix_vocal_with_instrumental(
    vocal_bytes: bytes,
    instrumental_path: str,
    vocal_vol: float = 1.0,
    inst_vol: float = 0.55,
) -> Optional[bytes]:
    """
    Mix vocal (bytes) with instrumental file on disk.

    Output length = vocal length + 3s fade-out.
    Both tracks play simultaneously from t=0.
    """
    if not is_ffmpeg_available():
        print("[MIXER] FFmpeg not found — mixing skipped.", flush=True)
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            vocal_path = os.path.join(tmp, "vocal.mp3")
            out_path   = os.path.join(tmp, "mixed.mp3")
            Path(vocal_path).write_bytes(vocal_bytes)

            vocal_dur = _get_duration(vocal_path)
            if vocal_dur <= 0:
                print("[MIXER] Could not determine vocal duration.", flush=True)
                return None

            fade_start = max(0.0, vocal_dur - 3.0)

            # Both inputs volume-adjusted, then mixed simultaneously.
            # Instrumental trimmed to vocal length before mix.
            # 3-second fade-out applied to the final output.
            filter_complex = (
                f"[0:a]volume={vocal_vol:.3f}[v];"
                f"[1:a]atrim=duration={vocal_dur:.3f},volume={inst_vol:.3f}[i];"
                f"[v][i]amix=inputs=2:duration=first[mixed];"
                f"[mixed]afade=t=out:st={fade_start:.3f}:d=3[out]"
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
                err = result.stderr[-600:].decode(errors='replace')
                print(f"[MIXER] FFmpeg failed: {err}", flush=True)
                return None

            mixed = Path(out_path).read_bytes()
            print(
                f"[MIXER] Mix complete: {len(mixed):,} bytes, "
                f"vocal={vocal_dur:.1f}s fade@{fade_start:.1f}s",
                flush=True,
            )
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
    inst_vol: float = 0.55,
) -> Optional[bytes]:
    """Mix both inputs from bytes (no pre-existing file needed)."""
    if not is_ffmpeg_available():
        print("[MIXER] FFmpeg not found — mixing skipped.", flush=True)
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            inst_path = os.path.join(tmp, f"inst{ext}")
            Path(inst_path).write_bytes(instrumental_bytes)
            return mix_vocal_with_instrumental(vocal_bytes, inst_path, vocal_vol, inst_vol)
    except Exception as e:
        print(f"[MIXER] Exception in bytes mix: {e}", flush=True)
        return None
