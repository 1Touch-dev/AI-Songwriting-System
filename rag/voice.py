"""
voice.py — Vocal synthesis with automatic fallback chain.

Primary  : ElevenLabs Multilingual V2 (best quality)
Fallback : OpenAI TTS (tts-1-hd) — uses the existing OPENAI_API_KEY

If ElevenLabs hits its quota or returns an auth error the request is
immediately re-routed to OpenAI TTS — voice never silently fails.
Returns None only when BOTH providers are unavailable.
"""
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

DEFAULT_VOICE_ID    = "JBFqnCBsd6RMkjVDRZzb"   # ElevenLabs "George"
MAX_CHARS           = 4500                        # ElevenLabs safe limit
OPENAI_MAX_CHARS    = 4096                        # OpenAI TTS limit per request
RETRY_ATTEMPTS      = 3
RETRY_DELAY_S       = 4

# ElevenLabs errors that should skip retries and go straight to OpenAI fallback
HARD_FAIL_KEYWORDS = (
    "quota", "quota_exceeded", "limit",
    "unauthorized", "invalid_api_key",
    "voice not found", "api key",
    "401", "403",
)


def clean_lyrics_for_tts(text: str) -> str:
    """Strip section headers and normalise whitespace for TTS input."""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _to_tts_text(lyrics: str, max_chars: int) -> str:
    """Clean lyrics and convert to a single TTS string."""
    cleaned = clean_lyrics_for_tts(lyrics)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit("\n", 1)[0]
        print(f"[VOICE] Lyrics truncated to {len(cleaned)} chars.", flush=True)
    return cleaned.replace("\n", ". ").strip()


class VoiceGenerator:
    """
    Voice synthesis with ElevenLabs → OpenAI TTS fallback.

    Construction never raises — if a provider is unavailable the generator
    falls through to the next one.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._eleven_key   = (api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        self._openai_key   = os.getenv("OPENAI_API_KEY", "").strip()
        self._eleven_client = None
        self._openai_client = None
        self._import_error: Optional[str] = None

        # --- ElevenLabs ---
        if self._eleven_key:
            try:
                from elevenlabs import ElevenLabs
                self._eleven_client = ElevenLabs(api_key=self._eleven_key)
                print("[VOICE] ElevenLabs client initialised.", flush=True)
            except ImportError as e:
                self._import_error = f"elevenlabs not installed: {e}"
                print(f"[VOICE] {self._import_error}", flush=True)
            except Exception as e:
                self._import_error = str(e)
                print(f"[VOICE] ElevenLabs init failed: {e}", flush=True)
        else:
            print("[VOICE] ELEVENLABS_API_KEY not set — will use OpenAI TTS.", flush=True)

        # --- OpenAI TTS ---
        if self._openai_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self._openai_key)
                print("[VOICE] OpenAI TTS client ready (fallback).", flush=True)
            except Exception as e:
                print(f"[VOICE] OpenAI TTS init failed: {e}", flush=True)

        # Backwards-compat alias used by api/main.py
        self.api_key = self._eleven_key
        self.client  = self._eleven_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_voice(
        self,
        lyrics: str,
        voice_id: str = DEFAULT_VOICE_ID,
    ) -> Optional[bytes]:
        """
        Synthesise vocals from lyrics.

        Tries ElevenLabs first; falls back to OpenAI TTS automatically on
        quota exhaustion, auth errors, or if ElevenLabs is not configured.
        Returns None only if both providers are unavailable / fail.
        Never raises.
        """
        # --- Try ElevenLabs ---
        if self._eleven_client:
            audio, hard_fail = self._try_elevenlabs(lyrics, voice_id)
            if audio:
                return audio
            if not hard_fail:
                # Soft failure (network etc.) — still attempt OpenAI fallback
                print("[VOICE] ElevenLabs soft-fail → trying OpenAI TTS.", flush=True)
            else:
                print("[VOICE] ElevenLabs hard-fail (quota/auth) → OpenAI TTS fallback.", flush=True)
        else:
            print("[VOICE] ElevenLabs unavailable → using OpenAI TTS directly.", flush=True)

        # --- Fallback to OpenAI TTS ---
        if self._openai_client:
            return self._try_openai_tts(lyrics)

        print("[VOICE] No voice provider available — voice generation skipped.", flush=True)
        return None

    # ------------------------------------------------------------------
    # ElevenLabs
    # ------------------------------------------------------------------

    def _try_elevenlabs(
        self, lyrics: str, voice_id: str
    ) -> tuple[Optional[bytes], bool]:
        """
        Returns (audio_bytes, hard_fail).
        hard_fail=True means quota/auth — caller should go straight to fallback.
        """
        tts_text   = _to_tts_text(lyrics, MAX_CHARS)
        last_error = "unknown"

        print(f"[VOICE] ElevenLabs: {len(tts_text)} chars, voice={voice_id}", flush=True)

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                audio_bytes = self._call_elevenlabs(tts_text, voice_id)

                if not audio_bytes or len(audio_bytes) < 1000:
                    raise ValueError(
                        f"Audio too small ({len(audio_bytes) if audio_bytes else 0} bytes)"
                    )

                print(f"[VOICE] ElevenLabs success ({len(audio_bytes):,} bytes)", flush=True)
                return audio_bytes, False

            except Exception as e:
                last_error = _classify_error(e)
                print(f"[VOICE] ElevenLabs attempt {attempt}/{RETRY_ATTEMPTS}: {last_error}", flush=True)

                if any(kw in last_error.lower() for kw in HARD_FAIL_KEYWORDS):
                    print("[VOICE] Hard failure — skipping ElevenLabs retries.", flush=True)
                    return None, True   # signal hard-fail to caller

                if attempt < RETRY_ATTEMPTS:
                    time.sleep(RETRY_DELAY_S * attempt)

        print(f"[VOICE] ElevenLabs exhausted. Last: {last_error}", flush=True)
        return None, False

    def _call_elevenlabs(self, text: str, voice_id: str) -> bytes:
        from elevenlabs import VoiceSettings
        from elevenlabs.core.request_options import RequestOptions

        stream = self._eleven_client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
            voice_settings=VoiceSettings(
                stability=0.45,
                similarity_boost=0.80,
                style=0.55,
                use_speaker_boost=True,
            ),
            request_options=RequestOptions(timeout_in_seconds=120),
        )
        return b"".join(stream)

    # ------------------------------------------------------------------
    # OpenAI TTS fallback
    # ------------------------------------------------------------------

    def _try_openai_tts(self, lyrics: str) -> Optional[bytes]:
        """Use OpenAI's tts-1-hd model as a high-quality fallback."""
        tts_text = _to_tts_text(lyrics, OPENAI_MAX_CHARS)
        print(f"[VOICE] OpenAI TTS: {len(tts_text)} chars...", flush=True)

        for attempt in range(1, 3):
            try:
                response = self._openai_client.audio.speech.create(
                    model="tts-1-hd",
                    voice="onyx",       # deep vocal quality — best for songs
                    input=tts_text,
                    response_format="mp3",
                    speed=0.95,
                )
                audio_bytes = response.read()

                if len(audio_bytes) < 1000:
                    raise ValueError(f"Audio too small ({len(audio_bytes)} bytes)")

                print(f"[VOICE] OpenAI TTS success ({len(audio_bytes):,} bytes)", flush=True)
                return audio_bytes

            except Exception as e:
                err = _classify_error(e)
                print(f"[VOICE] OpenAI TTS attempt {attempt}/2 failed: {err}", flush=True)
                if any(kw in err.lower() for kw in ("401", "invalid_api_key", "unauthorized")):
                    print("[VOICE] OpenAI auth error — aborting.", flush=True)
                    break
                if attempt < 2:
                    time.sleep(5)

        print("[VOICE] OpenAI TTS exhausted.", flush=True)
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def save_voice(
        self, text: str, output_path: str, voice_id: str = DEFAULT_VOICE_ID
    ) -> bool:
        from pathlib import Path
        audio_bytes = self.generate_voice(text, voice_id=voice_id)
        if audio_bytes:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(audio_bytes)
            return True
        return False


def _classify_error(exc: Exception) -> str:
    msg = str(exc)
    for attr in ("status_code", "status", "code"):
        code = getattr(exc, attr, None)
        if code:
            return f"HTTP {code}: {msg[:180]}"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return f"Timeout: {msg[:120]}"
    if "connection" in msg.lower():
        return f"Connection error: {msg[:120]}"
    return msg[:220]
