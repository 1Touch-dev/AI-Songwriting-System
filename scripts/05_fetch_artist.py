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
    if not name: return ""
    name = name.strip().strip('"').strip("'")
    name = re.sub(r"[^a-zA-Z0-9\s]", " ", name)
    name = " ".join(name.split())
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

    raw_artist = artist_input
    print(f"[INGEST] Starting hardened fetch: '{raw_artist}'...")
    
    # Primary Method: Apify
    song_data = fetch_via_apify(raw_artist, max_songs=max_songs)
    
    # Fallback to lyricsgenius ONLY for metadata if Apify failed
    if not song_data:
        print("[INGEST] Apify found no songs. Falling back to lyricsgenius (risky)...")
        import lyricsgenius
        genius = lyricsgenius.Genius(GENIUS_TOKEN)
        genius.verbose = False
        res = genius.search_artist(raw_artist, max_songs=3)
        if res:
            for s in res.songs:
                cleaned = clean_lyrics_text(s.lyrics)
                if len(cleaned) > 200:
                    song_data.append({"artist": res.name, "song": s.title, "lyrics": cleaned, "url": s.url})

    if len(song_data) < 3:
        print(f"[INGEST] FAILURE: Only {len(song_data)} songs found. Need 3.")
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
