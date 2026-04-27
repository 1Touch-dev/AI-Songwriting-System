"""
audio_validator.py — Audio file validation for uploads.

Validates:
- File format (mp3, wav, webm, ogg, m4a)
- File size (≤ 60MB)
- Audio duration (≤ 8 minutes)

Returns metadata or raises HTTPException.
"""
from __future__ import annotations

import io
import subprocess
import json
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

SUPPORTED_FORMATS = {".mp3", ".wav", ".webm", ".ogg", ".m4a"}
MAX_FILE_SIZE_MB = 60
MAX_DURATION_SECONDS = 8 * 60  # 8 minutes


def validate_audio_file(
    file_bytes: bytes,
    filename: str,
    max_size_mb: int = MAX_FILE_SIZE_MB,
    max_duration_sec: int = MAX_DURATION_SECONDS,
) -> dict:
    """
    Validate audio file and return metadata.
    
    Args:
        file_bytes: Raw audio file bytes
        filename: Original filename
        max_size_mb: Maximum file size in MB
        max_duration_sec: Maximum duration in seconds
    
    Returns:
        dict with keys: duration (float), format (str), size_mb (float)
    
    Raises:
        HTTPException: If validation fails
    """
    ext = Path(filename).suffix.lower()
    
    # Validate format
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Use mp3, wav, webm, ogg, or m4a."
        )
    
    # Validate size
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > max_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f}MB (max {max_size_mb}MB)"
        )
    
    # Get duration using ffprobe
    try:
        duration = _get_audio_duration(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse audio file: {str(e)}"
        )
    
    # Validate duration
    if duration > max_duration_sec:
        minutes = duration / 60
        max_minutes = max_duration_sec / 60
        raise HTTPException(
            status_code=400,
            detail=f"Audio too long: {minutes:.1f} minutes (max {max_minutes:.0f} minutes)"
        )
    
    return {
        "duration": round(duration, 2),
        "format": ext.lstrip("."),
        "size_mb": round(size_mb, 2),
    }


def _get_audio_duration(file_bytes: bytes) -> float:
    """
    Get audio duration in seconds using ffprobe.
    
    Args:
        file_bytes: Raw audio file bytes
    
    Returns:
        Duration in seconds (float)
    
    Raises:
        RuntimeError: If ffprobe fails
    """
    import tempfile
    
    # Write to temporary file (ffprobe needs seekable input for some formats)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp_file:
        tmp_path = tmp_file.name
        tmp_file.write(file_bytes)
    
    try:
        # Use ffprobe to get duration
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                tmp_path,
            ],
            capture_output=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr.decode()[:200]}")
        
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("Audio parsing timed out")
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {e}")
    finally:
        # Clean up temporary file
        try:
            import os
            os.unlink(tmp_path)
        except Exception:
            pass
