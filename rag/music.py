import os
import time
from typing import Optional, List, Dict
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

class MusicGenerator:
    """
    Suno AI Music Generation wrapper using Apify.
    Uses the tentortoise/suno-ai-generator actor for cost-effective production.
    """
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN")
        self.enabled = bool(self.api_token is not None)
        if self.enabled:
            self.client = ApifyClient(self.api_token)
        else:
            self.client = None
            print("[MUSIC] Apify token missing. Suno generation is DISABLED.")

    def run_full_generation(self, lyrics: str, style_tags: str, title: str, attempts: int = 3) -> Optional[str]:
        """
        Trigger Suno generation via Apify and return the first valid audio URL.
        Includes a reliability layer with retries and timeout handling.
        """
        if not self.enabled or not self.client:
            return None

        actor = "tentortoise/suno-ai-generator"
        payload = {
            "prompt": lyrics,
            "tags": style_tags,
            "title": title,
            "make_instrumental": False,
            "mv": "chirp-v3-0"
        }

        for i in range(3):
            try:
                print(f"[SUNO] Attempt {i+1}/3: Triggering Suno Actor...")
                run = self.client.actor(actor).call(run_input=payload)
                
                # Extract ONLY audio_url
                for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                    if "audio_url" in item:
                        return item["audio_url"]
                break
            except Exception as e:
                print(f"[SUNO] Attempt {i+1} failed: {e}")
                time.sleep(2 * (i+1))

        return None

        print("[SUNO] All generation attempts exhausted.")
        return None
