import os
from pathlib import Path
from typing import Optional
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

load_dotenv()

class VoiceGenerator:
    """Voice generation wrapper using ElevenLabs Multilingual V2."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if self.api_key:
            self.client = ElevenLabs(api_key=self.api_key)
        else:
            self.client = None
            print("[VOICE] WARNING: ELEVENLABS_API_KEY not found. Voice generation will be disabled.")

    def generate_voice(self, text: str, voice_id: str = "JBFqnCBsd6RMkjVDRZzb") -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs and return audio bytes.
        Default voice: 'Charlie' (warm, versatile).
        """
        if not self.client:
            return None
            
        try:
            print(f"[VOICE] Generating speech for text: '{text[:50]}...'")
            audio = self.client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            )
            
            # Convert generator to bytes
            audio_bytes = b"".join(chunk for chunk in audio)
            return audio_bytes
        except Exception as e:
            print(f"[VOICE] Generation failed: {e}")
            return None

    def save_voice(self, text: str, output_path: str, voice_id: str = "JBFqnCBsd6RMkjVDRZzb") -> bool:
        """Helper to save voice directly to a file."""
        audio_bytes = self.generate_voice(text, voice_id=voice_id)
        if audio_bytes:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            return True
        return False
