import os
import time
import requests
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()

class MusicGenerator:
    """
    Suno AI Music Generation wrapper.
    Uses unofficial API architecture (e.g., suno-api or similar proxy).
    """
    
    def __init__(self, api_url: Optional[str] = None):
        # Default to a common community endpoint if not provided
        self.api_url = api_url or os.getenv("SUNO_API_URL", "http://localhost:3000")
        self.enabled = bool(os.getenv("SUNO_ENABLED", "False").lower() == "true")

    def generate_music(self, lyrics: str, style_tags: str, title: str = "AI Generated Song") -> Optional[List[Dict]]:
        """
        Trigger Suno generation.
        Returns a list of task objects (usually 2 versions per request).
        """
        if not self.enabled:
            print("[MUSIC] Suno generation is DISABLED in .env.")
            return None

        endpoint = f"{self.api_url}/api/custom_generate"
        payload = {
            "prompt": lyrics,
            "tags": style_tags,
            "title": title,
            "make_instrumental": False,
            "wait_audio": False # Using polling for better async handling
        }

        try:
            print(f"[MUSIC] Triggering Suno generation for: '{title}'...")
            response = requests.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # The API usually returns a list of clips/tasks
            if isinstance(data, list):
                return data
            return [data]
        except Exception as e:
            print(f"[MUSIC] Request failed: {e}")
            return None

    def poll_status(self, clip_ids: List[str], timeout: int = 120) -> List[Dict]:
        """Poll the API until generation is complete or timeout reached."""
        if not self.enabled: return []
        
        endpoint = f"{self.api_url}/api/get"
        start_time = time.time()
        
        print(f"[MUSIC] Polling status for clips: {clip_ids}...")
        while time.time() - start_time < timeout:
            try:
                params = {"ids": ",".join(clip_ids)}
                response = requests.get(endpoint, params=params)
                data = response.json()
                
                # Check if all targeted clips are complete/failed
                all_done = True
                for clip in data:
                    status = clip.get("status")
                    if status not in ["streaming", "complete", "failed"]:
                        all_done = False
                        break
                
                if all_done:
                    return data
                    
                time.sleep(5) # Poll every 5 seconds
            except Exception as e:
                print(f"[MUSIC] Polling error: {e}")
                time.sleep(5)
                
        print("[MUSIC] Polling timed out.")
        return []

    def run_full_generation(self, lyrics: str, style_tags: str, title: str) -> List[str]:
        """Helper to run the full flow and return a list of audio URLs."""
        clips = self.generate_music(lyrics, style_tags, title)
        if not clips:
            return []
            
        clip_ids = [c["id"] for c in clips if "id" in c]
        if not clip_ids:
            return []
            
        # Wait for completion
        results = self.poll_status(clip_ids)
        
        # Extract audio URLs
        urls = []
        for r in results:
            url = r.get("audio_url")
            if url:
                urls.append(url)
                
        return urls
