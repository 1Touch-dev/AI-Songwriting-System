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

    def run_full_generation(self, lyrics: str, style_tags: str, title: str, attempts: int = 3) -> List[str]:
        """
        Trigger Suno generation via Apify and return active audio URLs.
        Includes a reliability layer with retries and timeout handling.
        """
        if not self.enabled or not self.client:
            return []

        # tentortoise/suno-ai-generator input schema
        run_input = {
            "prompt": lyrics,
            "tags": style_tags,
            "title": title,
            "make_instrumental": False,
            "mv": "chirp-v3-0"
        }

        for i in range(attempts):
            try:
                print(f"[MUSIC] Attempt {i+1}/{attempts}: Triggering Apify Suno Actor for: '{title}'...")
                # Run the Actor and wait for it to finish (max 300s timeout)
                run = self.client.actor("tentortoise/suno-ai-generator").call(
                    run_input=run_input,
                    timeout_secs=300 
                )
                
                # Fetch results from the run's dataset
                urls = []
                for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                    # The actor usually returns objects with 'audio_url' or 'audio_url_1'
                    audio_url = item.get("audio_url") or item.get("audio_url_1") or item.get("audio_url_2")
                    if audio_url:
                        urls.append(audio_url)
                
                    # Fallback check
                    if not urls and "result" in item:
                       urls.append(item["result"])

                if urls:
                    return sorted(list(set(urls))) # Return unique URLs
                
                print(f"[MUSIC] Attempt {i+1} returned no URLs. Retrying...")
                
            except Exception as e:
                print(f"[MUSIC] Attempt {i+1} failed: {e}")
                if i < attempts - 1:
                    time.sleep(5 * (i + 1)) # Exponential backoff
                else:
                    break

        print("[MUSIC] All generation attempts exhausted.")
        return []
