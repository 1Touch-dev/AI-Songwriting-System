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

        actor_id = "tentortoise/suno-ai-generator"
        run_input = {
            "prompt": lyrics,
            "tags": style_tags,
            "title": title,
            "make_instrumental": False,
            "mv": "chirp-v3-0"
        }

        music_url = None
        for attempt in range(attempts):
            try:
                print(f"[SUNO] Attempt {attempt+1}/{attempts}: Triggering Apify Suno Actor for: '{title}'...")
                # Run the Actor and wait for it to finish (max 300s timeout)
                run = self.client.actor(actor_id).call(
                    run_input=run_input,
                    timeout_secs=300 
                )
                
                # Fetch results from the run's dataset
                urls = []
                for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                    # STRICT URL EXTRACTION
                    if "audio_url" in item:
                        urls.append(item["audio_url"])
                
                if urls:
                    music_url = urls[0]
                    print(f"[SUNO] Success! URL: {music_url}")
                    return music_url
                
                print(f"[SUNO] Attempt {attempt+1} returned no valid URLs. Retrying...")
                
            except Exception as e:
                print(f"[SUNO] Attempt {attempt+1} failed: {e}")
                if attempt < attempts - 1:
                    time.sleep(2 * (attempt + 1)) # Exponential backoff
                else:
                    break

        print("[SUNO] All generation attempts exhausted.")
        return None
