"""
audio_mixer.py — Voice + Music mixing and mastering pipeline.
Requires: pydub, ffmpeg
"""
import io
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.silence import detect_leading_silence


def _load(audio_bytes: bytes) -> AudioSegment:
    """Load audio bytes regardless of format (mp3, flac, wav, ogg)."""
    return AudioSegment.from_file(io.BytesIO(audio_bytes))


def _to_stereo_44k(seg: AudioSegment) -> AudioSegment:
    return seg.set_frame_rate(44100).set_channels(2).set_sample_width(2)


def _trim_silence(seg: AudioSegment, thresh_db: int = -50) -> AudioSegment:
    """Remove leading/trailing silence."""
    start = detect_leading_silence(seg, silence_threshold=thresh_db, chunk_size=10)
    end = len(seg) - detect_leading_silence(
        seg.reverse(), silence_threshold=thresh_db, chunk_size=10
    )
    trimmed = seg[start:end]
    return trimmed if len(trimmed) > 500 else seg  # guard against over-trim


def _loop_to_length(seg: AudioSegment, target_ms: int) -> AudioSegment:
    """Loop audio segment until it covers target_ms."""
    if len(seg) == 0:
        return seg
    repeats = (target_ms // len(seg)) + 2
    return (seg * repeats)[:target_ms]


def mix_voice_and_music(voice_bytes: bytes, music_bytes: bytes) -> bytes:
    """
    Mix ElevenLabs voice over Suno/MusicGen instrumental.

    Pipeline:
      1. Load + normalize to 44.1kHz stereo
      2. Trim leading silence from voice
      3. Duck music -8 dB (vocals stay dominant)
      4. Loop music to voice length + 3s tail
      5. Fade music in (200ms) / out (1.5s)
      6. Overlay voice at position 0
      7. Master: normalize → limit peaks → fade in/out 200ms
      8. Export MP3 192k

    Returns MP3 bytes.
    """
    print("[MIXER] Loading audio...")
    voice = _to_stereo_44k(_load(voice_bytes))
    music = _to_stereo_44k(_load(music_bytes))

    # Step 1: Trim silence from voice start/end
    voice = _trim_silence(voice, thresh_db=-45)
    print(f"[MIXER] Voice: {len(voice)/1000:.1f}s | Music raw: {len(music)/1000:.1f}s")

    # Step 2: Duck music
    music = music - 8

    # Step 3: Loop music to cover voice + 3s tail
    target_ms = len(voice) + 3000
    music = _loop_to_length(music, target_ms)

    # Step 4: Fade music
    music = music.fade_in(200).fade_out(1500)

    # Step 5: Overlay voice at beat 0
    mixed = music.overlay(voice, position=0)

    # Step 6: Master
    mixed = normalize(mixed)               # loudness normalization
    mixed = mixed + 1                      # slight boost post-normalize
    peak = mixed.max_dBFS
    if peak > -0.5:                        # prevent clipping
        mixed = mixed - (peak + 0.5)
    mixed = mixed.fade_in(200).fade_out(300)

    print(f"[MIXER] Mixed track: {len(mixed)/1000:.1f}s | Peak: {mixed.max_dBFS:.1f} dBFS")

    out = io.BytesIO()
    mixed.export(out, format="mp3", bitrate="192k")
    result = out.getvalue()
    print(f"[MIXER] Export complete: {len(result):,} bytes")
    return result
