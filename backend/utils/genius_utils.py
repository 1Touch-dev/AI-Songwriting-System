import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Map to GENIUS_ACCESS_TOKEN if GENIUS_API_KEY is not set (Production safety)
GENIUS_API_KEY = os.getenv("GENIUS_API_KEY") or os.getenv("GENIUS_ACCESS_TOKEN")

def search_genius_artists(query):
    """
    Search Genius for artists matching the query for autocomplete suggestions.
    """
    if not query or len(query) < 3:
        return []

    url = "https://api.genius.com/search"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}
    params = {"q": query}

    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()

        artists = set()
        results = []

        if "response" in data and "hits" in data["response"]:
            for hit in data["response"]["hits"]:
                artist_name = hit["result"]["primary_artist"]["name"]
                if artist_name not in artists:
                    artists.add(artist_name)
                    results.append(artist_name)

        return results[:8]

    except Exception as e:
        print("Autocomplete error:", e)
        return []
