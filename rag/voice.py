import os
import re
from pathlib import Path
from typing import Optional
from elevenlabs.client import ElevenLabs, VoiceSettings
from dotenv import load_dotenv

load_dotenv()

def clean_lyrics_for_tts(text: str) -> str:
    # Remove section labels like [Verse], [Chorus]
    text = re.sub(r"\[.*?\]", "", text)
    # Remove extra empty lines
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()

def format_for_voice_delivery(text: str) -> str:
    lines = text.split("\n")
    processed = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Add pause after each line using ElevenLabs SSML
        processed.append(line + " <break time='0.6s'/>")
    return "\n".join(processed)

def enhance_chorus(text: str) -> str:
    # We identify chorus sections using [Chorus] before cleaning
    # or handle it differently if already cleaned.
    # The user instruction says clean then enhance, but clean removes [Chorus].
    # Let's adjust logic: enhance FIRST, then clean tags.
    parts = text.split("[Chorus]")
    if len(parts) < 2:
        return text

    enhanced = parts[0]
    for part in parts[1:]:
        lines = part.strip().split("\n")
        if len(lines) >= 2:
            # repeat first line for musical feel
            chorus = f"[Chorus]\n{lines[0]}\n{lines[0]}\n" + "\n".join(lines[1:])
        else:
            chorus = f"[Chorus]\n" + part
        enhanced += chorus
    return enhanced

class VoiceGenerator:
    """Voice generation wrapper using ElevenLabs Multilingual V2."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if self.api_key:
            self.client = ElevenLabs(api_key=self.api_key)
        else:
            self.client = None
            print("[VOICE] WARNING: ELEVENLABS_API_KEY not found. Voice generation will be disabled.")

    def generate_voice(self, lyrics: str, voice_id: str = "JBFqnCBsd6RMkjVDRZzb") -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs and return audio bytes.
        Upgraded to Music Demo style with SSML and emotional delivery.
        """
        if not self.client:
            return None
            
        try:
            # 1. Transform text for musical feel
            enhanced = enhance_chorus(lyrics)
            cleaned = clean_lyrics_for_tts(enhanced)
            final_text = format_for_voice_delivery(cleaned)

            # 2. Add tone guidance
            final_text = f"""
Speak in a smooth, emotional, melodic tone.
Pause naturally like a singer between lines.

{final_text}
"""
            print(f"[VOICE] Generating music-demo speech...")
            
            audio = self.client.text_to_speech.convert(
                text=final_text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                enable_ssml_parsing=True,
                voice_settings=VoiceSettings(
                    stability=0.4,
                    similarity_boost=0.8,
                    style=0.6,
                    use_speaker_boost=True
                )
            )

            audio_bytes = b"".join(audio)
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
