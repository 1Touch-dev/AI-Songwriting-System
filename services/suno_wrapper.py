"""
suno_wrapper.py — Clean service wrapper around MusicGenerator.

Provides convenience methods for the remix/audio pipeline
that the API layer can call without importing rag internals.
"""
from __future__ import annotations

from typing import Optional

from rag.music import MusicGenerator

_generator: Optional[MusicGenerator] = None


def _get_generator() -> MusicGenerator:
    global _generator
    if _generator is None:
        _generator = MusicGenerator()
    return _generator


def generate_audio(
    lyrics: str,
    style_tags: str = "",
    title: str = "Untitled",
) -> Optional[bytes]:
    """
    Generate a full song (vocals + music) via Suno AI.
    Falls back to HuggingFace MusicGen if Suno fails.

    Returns MP3 bytes or None if all providers fail.
    """
    gen = _get_generator()
    return gen.run_full_generation(lyrics, style_tags, title)


def generate_remix_audio(
    locked_chorus: str,
    new_verses: str,
    style_tags: str = "",
    title: str = "Remix",
) -> Optional[bytes]:
    """
    Generate audio for a remixed song.
    Combines locked chorus + new verses into full lyrics, then generates.
    """
    full_lyrics = f"{new_verses}\n\n{locked_chorus}"
    return generate_audio(full_lyrics, style_tags=style_tags, title=title)


def generate_preview(
    lyrics: str,
    style_tags: str = "",
) -> Optional[bytes]:
    """
    Generate a short preview clip — first 30-60 seconds.
    Uses HuggingFace MusicGen (faster, instrumental only).
    """
    gen = _get_generator()
    if gen.hf_key:
        return gen._hf_generate(style_tags or lyrics[:100], "Preview", attempts=2)
    return generate_audio(lyrics, style_tags=style_tags, title="Preview")
