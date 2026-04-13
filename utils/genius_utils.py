import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")

def search_genius_artists(query: str, limit: int = 5) -> List[Dict]:
    """
    Search Genius for artists matching the query.
    Returns a list of unique artist dictionaries with name and id.
    """
    if not query or len(query) < 2:
        return []
    
    if not GENIUS_ACCESS_TOKEN:
        print("[GENIUS] Access token missing.")
        return []

    url = f"https://api.genius.com/search?q={query}"
    headers = {"Authorization": f"Bearer {GENIUS_ACCESS_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("response", {}).get("hits", [])
        artists = []
        seen_names = set()
        
        for hit in hits:
            # The search returns songs, but each song has a primary_artist
            artist_data = hit.get("result", {}).get("primary_artist")
            if artist_data:
                name = artist_data.get("name")
                # Filter out generic artists or duplicates
                if name and name not in seen_names:
                    artists.append({
                        "name": name,
                        "id": artist_data.get("id"),
                        "image_url": artist_data.get("image_url")
                    })
                    seen_names.add(name)
            
            if len(artists) >= limit:
                break
                
        return artists
    except Exception as e:
        print(f"[GENIUS] Artist search failed: {e}")
        return []
