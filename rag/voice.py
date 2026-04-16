"""
voice.py — ElevenLabs vocal synthesis.

Generates a vocal MP3 from song lyrics.
Retries automatically on transient errors (network, 5xx, timeouts).
Returns None only after all retries are exhausted or on hard failures
(missing key, quota exceeded, voice not found).
"""
import os
import re
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Voice ID — "George" (ElevenLabs built-in, always available)
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MAX_CHARS        = 4500   # ElevenLabs free-tier safe limit
RETRY_ATTEMPTS   = 3
RETRY_DELAY_S    = 4      # seconds between retries


def clean_lyrics_for_tts(text: str) -> str:
    """Strip section headers and normalise whitespace for clean TTS input."""
    text = re.sub(r"\[.*?\]", "", text)          # [Verse 1], [Chorus] etc.
    text = re.sub(r"\n{3,}", "\n\n", text)       # collapse excess blank lines
    text = re.sub(r"[ \t]+", " ", text)          # normalise spaces
    return text.strip()


class VoiceGenerator:
    """Voice synthesis wrapper using ElevenLabs Multilingual V2.

    If the API key is missing at construction time, all calls return None
    but do NOT raise — the pipeline continues without voice audio.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        self.client  = None
        self._import_error: Optional[str] = None

        if not self.api_key:
            print("[VOICE] ELEVENLABS_API_KEY not set — voice generation disabled.", flush=True)
            return

        try:
            from elevenlabs import ElevenLabs
            self.client = ElevenLabs(api_key=self.api_key)
            print("[VOICE] ElevenLabs client initialised.", flush=True)
        except ImportError as e:
            self._import_error = str(e)
            print(f"[VOICE] elevenlabs package not installed: {e}", flush=True)
        except Exception as e:
            self._import_error = str(e)
            print(f"[VOICE] Failed to initialise ElevenLabs client: {e}", flush=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_voice(
        self,
        lyrics: str,
        voice_id: str = DEFAULT_VOICE_ID,
    ) -> Optional[bytes]:
        """
        Convert lyrics to speech and return raw MP3 bytes.
        Returns None if voice is disabled or all retries fail.
        Never raises — all exceptions are caught internally.
        """
        if not self.client:
            reason = self._import_error or "API key not set"
            print(f"[VOICE] Skipping generation: {reason}", flush=True)
            return None

        cleaned = clean_lyrics_for_tts(lyrics)
        if not cleaned:
            print("[VOICE] Empty lyrics after cleaning — skipping.", flush=True)
            return None

        # Truncate if over limit (split at sentence boundary where possible)
        if len(cleaned) > MAX_CHARS:
            cleaned = cleaned[:MAX_CHARS].rsplit("\n", 1)[0]
            print(f"[VOICE] Lyrics truncated to {len(cleaned)} chars.", flush=True)

        # Replace bare newlines with a period so TTS reads naturally
        tts_text = cleaned.replace("\n", ". ").strip()

        print(f"[VOICE] Generating speech ({len(tts_text)} chars, voice={voice_id})...", flush=True)

        last_error: str = "unknown"

        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                audio_bytes = self._call_elevenlabs(tts_text, voice_id)

                if not audio_bytes or len(audio_bytes) < 1000:
                    raise ValueError(
                        f"Audio too small ({len(audio_bytes) if audio_bytes else 0} bytes)"
                    )

                print(f"[VOICE] Success on attempt {attempt}: {len(audio_bytes):,} bytes", flush=True)
                return audio_bytes

            except Exception as e:
                last_error = self._classify_error(e)
                print(f"[VOICE] Attempt {attempt}/{RETRY_ATTEMPTS} failed: {last_error}", flush=True)

                # Hard failures — retrying won't help
                if any(kw in last_error.lower() for kw in (
                    "quota", "limit", "unauthorized", "invalid_api_key",
                    "voice not found", "api key", "401", "403",
                )):
                    print("[VOICE] Non-retryable error — aborting.", flush=True)
                    break

                if attempt < RETRY_ATTEMPTS:
                    delay = RETRY_DELAY_S * attempt   # 4s, 8s
                    print(f"[VOICE] Retrying in {delay}s...", flush=True)
                    time.sleep(delay)

        print(f"[VOICE] All attempts exhausted. Last error: {last_error}", flush=True)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_elevenlabs(self, text: str, voice_id: str) -> bytes:
        from elevenlabs import VoiceSettings
        from elevenlabs.core.request_options import RequestOptions

        audio_stream = self.client.text_to_speech.convert(
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
        return b"".join(audio_stream)

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Return a compact, human-readable string describing the error."""
        msg = str(exc)
        # ElevenLabs SDK wraps HTTP errors — extract the status code / body
        for attr in ("status_code", "status", "code"):
            code = getattr(exc, attr, None)
            if code:
                return f"HTTP {code}: {msg[:120]}"
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            return f"Timeout: {msg[:120]}"
        if "connection" in msg.lower():
            return f"Connection error: {msg[:120]}"
        return msg[:200]

    def save_voice(
        self,
        text: str,
        output_path: str,
        voice_id: str = DEFAULT_VOICE_ID,
    ) -> bool:
        """Convenience: synthesise and write to a file. Returns True on success."""
        from pathlib import Path
        audio_bytes = self.generate_voice(text, voice_id=voice_id)
        if audio_bytes:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(audio_bytes)
            return True
        return False
