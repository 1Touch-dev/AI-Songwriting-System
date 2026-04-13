"""
Hardened Artist Lyrics Ingestion via Apify + Genius API
======================================================
Robustly fetches artist songs using Apify Genius Scraper.
Bypasses Cloudflare blocks on server environments.
"""

import os
import json
import argparse
import re
import time
import requests
from pathlib import Path
from typing import Optional, List, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GENIUS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")

# --- UTILS ---

def normalize_artist_name(name: str) -> str:
    """Robust normalization: lowercase, strip, remove special chars, handle quotes."""
    if not name: return ""
    # Strip quotes and whitespace
    name = name.strip().strip('"').strip("'")
    # Lowercase for consistency
    name = name.lower()
    # Remove everything except alphanumeric and spaces
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    # Collapse multiple spaces
    name = " ".join(name.split())
    return name

def get_canonical_artist(name: str) -> Optional[str]:
    """Search Genius to find the most likely canonical artist name."""
    if not GENIUS_TOKEN:
        return name # Fallback to input
    
    try:
        url = "https://api.genius.com/search"
        headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
        params = {"q": name}
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        # Look for the first result that is actually a song with correct metadata
        hits = data.get("response", {}).get("hits", [])
        if not hits:
            print(f"[INGEST] No Genius hits for '{name}'.")
            return name
        
        # Extract the primary artist from the first result
        # We prioritize exact names in the primary_artist field
        best_match = hits[0]["result"]["primary_artist"]["name"]
        print(f"[INGEST] Search resolution: '{name}' -> '{best_match}'")
        return best_match
    except Exception as e:
        print(f"[INGEST] Search resolution failed for '{name}': {e}")
        return name

def clean_lyrics_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"^\d+\s*Embed$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^.*?Lyrics$", "", text, flags=re.MULTILINE)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)

# --- APIFY SCRAPING ---

def fetch_via_apify(artist_name: str, max_songs: int = 15) -> List[dict]:
    """Use Apify Genius Scraper for reliable, Cloudflare-safe lyrics extraction."""
    if not APIFY_TOKEN:
        print("[INGEST] APIFY_API_TOKEN missing. Skipping Apify.")
        return []

    try:
        from apify_client import ApifyClient
        client = ApifyClient(APIFY_TOKEN)
        
        print(f"[INGEST] Engaging Apify Genius Scraper for: '{artist_name}'...")
        run_input = {
            "searchQueries": [artist_name],
            "maxItems": max_songs,
            "onlyLyrics": True
        }
        
        # Call the actor
        run = client.actor("automation-lab/genius-scraper").call(run_input=run_input)
        
        songs = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            lyrics = clean_lyrics_text(item.get("lyrics", ""))
            if len(lyrics) > 200:
                songs.append({
                    "artist": item.get("artistName", artist_name),
                    "song": item.get("title", ""),
                    "lyrics": lyrics,
                    "url": item.get("url", "")
                })
                print(f"  [INGEST] Scraped via Apify: {item.get('title')}")
                
        return songs
    except Exception as e:
        print(f"[INGEST] Apify fetch failed: {e}")
        return []

# --- CORE FETCHING ---

def fetch_artist_songs(artist_input: str, max_songs: int = 20) -> Optional[Path]:
    """
    Final Hardened Ingester: Multi-strategy (Genius Metadata -> Apify Scraping).
    """
    if not GENIUS_TOKEN or not APIFY_TOKEN:
        print("[ERROR] GENIUS_ACCESS_TOKEN or APIFY_API_TOKEN missing.")
        return None

    print(f"[INGEST] Starting hardened fetch process for: '{artist_input}'...")
    
    # 1. Resolve Canonical Name
    canonical_artist = get_canonical_artist(artist_input)
    search_queries = list(set([artist_input, canonical_artist, normalize_artist_name(artist_input)]))
    
    song_data = []
    
    # 2. Strategy A: Multi-query Apify Fetch (Retry Logic)
    for query in search_queries:
        if not query: continue
        print(f"[INGEST] Attempting Apify fetch with query: '{query}'")
        data = fetch_via_apify(query, max_songs=max_songs)
        if data:
            song_data = data
            break
    
    # 3. Strategy B: Lyricsgenius Fallback (Last Resort)
    if not song_data:
        print("[INGEST] Apify strategy failed for all queries. Falling back to lyricsgenius...")
        try:
            import lyricsgenius
            genius = lyricsgenius.Genius(GENIUS_TOKEN)
            genius.verbose = False
            # Try once with canonical, once with raw
            for query in [canonical_artist, artist_input]:
                res = genius.search_artist(query, max_songs=3)
                if res and res.songs:
                    for s in res.songs:
                        cleaned = clean_lyrics_text(s.lyrics)
                        if len(cleaned) > 200:
                            song_data.append({
                                "artist": res.name, 
                                "song": s.title, 
                                "lyrics": cleaned, 
                                "url": s.url
                            })
                    if song_data: break
        except Exception as e:
            print(f"[INGEST] Lyricsgenius fallback failed: {e}")

    if len(song_data) < 3:
        print(f"[INGEST] FAILURE: Only {len(song_data)} songs found. Minimal threshold (3) not met.")
        return None

    # Determine canonical artist name
    artist_name = song_data[0]["artist"]
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", artist_name.lower()).strip("_")
    output_path = output_dir / f"{safe_name}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(song_data, f, indent=4, ensure_ascii=False)

    print(f"[INGEST] SUCCESS: Ingested {len(song_data)} songs for '{artist_name}'")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hardened Artist Fetcher")
    parser.add_argument("--artist", type=str, required=True)
    parser.add_argument("--max", type=int, default=20)
    args = parser.parse_args()
    
    fetch_artist_songs(args.artist, args.max)
