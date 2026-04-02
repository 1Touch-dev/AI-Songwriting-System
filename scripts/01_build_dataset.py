"""
Step 1 & 2: Dataset Collection + Cleaning
==========================================
- Load Genius Lyrics dataset from HuggingFace
- Filter for TARGET_ARTISTS
- Select up to SONGS_PER_ARTIST songs per artist
- Optionally merge Billboard chart data
- Clean lyrics (remove bracketed tags, normalize whitespace)
- Save to cleaned_songs.jsonl

Run: python scripts/01_build_dataset.py
"""

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib.util
from utils.config import (
    CLEANED_SONGS_PATH,
    RAW_DIR,
    SONGS_PER_ARTIST,
    TARGET_ARTISTS,
)

def _load_fetcher():
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "05_fetch_artist.py"
    spec = importlib.util.spec_from_file_location("fetch_artist", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# ── Normalise artist names for matching ────────────────────────────────────

def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


NORMALISED_TARGETS = {normalise(a): a for a in TARGET_ARTISTS}


def match_artist(raw_name: str) -> str | None:
    """Return canonical artist name or None if not a target."""
    key = normalise(raw_name)
    # Exact match
    if key in NORMALISED_TARGETS:
        return NORMALISED_TARGETS[key]
    # Partial match (e.g. "Drake feat. Future" → Drake)
    for norm, canonical in NORMALISED_TARGETS.items():
        if norm in key or key in norm:
            return canonical
    return None


# ── Lyrics cleaning ─────────────────────────────────────────────────────────

def clean_lyrics(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Remove [Verse 1], [Chorus], etc. section headers
    text = re.sub(r"\[.*?\]", "", text)
    # Remove lines that are purely metadata artefacts
    text = re.sub(r"^\d+\s*Embed$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^.*?Lyrics$", "", text, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Load Genius dataset ─────────────────────────────────────────────────────

def load_genius_dataset() -> pd.DataFrame:
    """Stream the HuggingFace Genius dataset, filter for target artists."""
    print("Loading Genius Lyrics dataset from HuggingFace …")
    try:
        from datasets import load_dataset

        # Switch to a more complete dataset that includes titles, artists, and lyrics.
        ds = load_dataset(
            "smgriffin/modern-pop-lyrics",
            split="train",
            streaming=True,
            trust_remote_code=True,
        )

        rows = []
        seen: dict[str, set] = {a: set() for a in TARGET_ARTISTS}

        for record in tqdm(ds, desc="Scanning dataset"):
            raw_artist = record.get("artist", "") or ""
            canonical = match_artist(raw_artist)
            if canonical is None:
                continue
            if len(seen[canonical]) >= SONGS_PER_ARTIST:
                # Check if we're done with all artists
                if all(len(v) >= SONGS_PER_ARTIST for v in seen.values()):
                    break
                continue

            song = record.get("title", "") or record.get("song", "") or ""
            lyrics = record.get("lyrics", "") or ""
            lyrics = clean_lyrics(lyrics)
            if len(lyrics) < 200:  # skip very short / empty entries
                continue

            song_key = normalise(song)
            if song_key in seen[canonical]:
                continue
            seen[canonical].add(song_key)

            rows.append(
                {
                    "artist": canonical,
                    "song": song.strip(),
                    "lyrics": lyrics,
                    "genre": record.get("tag", record.get("genre", "")),
                    "year": record.get("year", None),
                    "chart_rank": None,
                }
            )

        df = pd.DataFrame(rows)
        print(f"  Collected {len(df)} songs across {df['artist'].nunique()} artists.")
        return df

    except Exception as exc:
        print(f"[ERROR] Could not load HuggingFace dataset: {exc}")
        print("  Attempting to load from local cache …")
        return _load_from_cache()


def _load_from_cache() -> pd.DataFrame:
    """Fallback: look for any pre-downloaded CSV/JSONL in data/raw/."""
    for pattern in ("*.jsonl", "*.json", "*.csv"):
        files = list(RAW_DIR.glob(pattern))
        if files:
            f = files[0]
            print(f"  Found local file: {f}")
            if f.suffix == ".csv":
                return pd.read_csv(f)
            else:
                return pd.read_json(f, lines=True)
    return pd.DataFrame(columns=["artist", "song", "lyrics", "genre", "year", "chart_rank"])


# ── Billboard merge (optional) ──────────────────────────────────────────────

def load_billboard() -> pd.DataFrame | None:
    """Try to load a Billboard CSV from data/raw/ (user must supply it)."""
    candidates = list(RAW_DIR.glob("*billboard*")) + list(RAW_DIR.glob("*hot*100*"))
    if not candidates:
        print("  No Billboard CSV found in data/raw/ – skipping chart_rank merge.")
        return None
    df = pd.read_csv(candidates[0])
    print(f"  Loaded Billboard data: {len(df)} rows")
    return df


def merge_billboard(songs_df: pd.DataFrame, bb_df: pd.DataFrame) -> pd.DataFrame:
    """Merge chart_rank from Billboard into the songs DataFrame."""
    # Normalise for matching
    bb_df = bb_df.copy()
    bb_df["artist_norm"] = bb_df.get("artist", bb_df.get("Artist", "")).apply(normalise)
    bb_df["song_norm"] = bb_df.get("song", bb_df.get("Song", bb_df.get("title", ""))).apply(normalise)
    # Keep best (lowest) rank per song
    if "rank" in bb_df.columns:
        rank_col = "rank"
    elif "Peak Position" in bb_df.columns:
        rank_col = "Peak Position"
    else:
        rank_col = bb_df.columns[-1]

    best_rank = bb_df.groupby(["artist_norm", "song_norm"])[rank_col].min().reset_index()
    best_rank.rename(columns={rank_col: "chart_rank_bb"}, inplace=True)

    songs_df["artist_norm"] = songs_df["artist"].apply(normalise)
    songs_df["song_norm"] = songs_df["song"].apply(normalise)
    songs_df = songs_df.merge(best_rank, on=["artist_norm", "song_norm"], how="left")
    songs_df["chart_rank"] = songs_df["chart_rank_bb"].combine_first(songs_df["chart_rank"])
    songs_df.drop(columns=["artist_norm", "song_norm", "chart_rank_bb"], inplace=True)
    return songs_df


# ── Apify fallback ──────────────────────────────────────────────────────────

def scrape_missing_via_apify(songs_df: pd.DataFrame) -> pd.DataFrame:
    """
    For any target artist with fewer than 10 songs, attempt to fill gaps
    via the Apify Genius Scraper.  Only runs if APIFY_API_TOKEN is set.
    """
    token = os.getenv("APIFY_API_TOKEN", "")
    if not token:
        return songs_df

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("  apify_client not installed – skipping Apify fallback.")
        return songs_df

    coverage = songs_df.groupby("artist").size()
    missing_artists = [a for a in TARGET_ARTISTS if coverage.get(a, 0) < 10]

    if not missing_artists:
        return songs_df

    print(f"  Using Apify to fill gaps for {len(missing_artists)} artists …")
    client = ApifyClient(token)
    new_rows = []

    for artist in missing_artists[:5]:  # limit to 5 to control cost
        have = coverage.get(artist, 0)
        need = SONGS_PER_ARTIST - have
        print(f"    Scraping up to {need} songs for {artist} …")
        try:
            run = client.actor("automation-lab/genius-scraper").call(
                run_input={
                    "searchQueries": [artist],
                    "maxItems": need,
                }
            )
            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                lyrics = clean_lyrics(item.get("lyrics", ""))
                if len(lyrics) < 200:
                    continue
                new_rows.append(
                    {
                        "artist": artist,
                        "song": item.get("title", ""),
                        "lyrics": lyrics,
                        "genre": item.get("genre", ""),
                        "year": item.get("year", None),
                        "chart_rank": None,
                    }
                )
        except Exception as exc:
            print(f"    [WARN] Apify scrape failed for {artist}: {exc}")

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        songs_df = pd.concat([songs_df, new_df], ignore_index=True)
        songs_df.drop_duplicates(
            subset=["artist", "song"], keep="first", inplace=True
        )
    return songs_df


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # 1. Load Genius
    df = load_genius_dataset()

    # 2. Merge Billboard (optional)
    bb_df = load_billboard()
    if bb_df is not None:
        df = merge_billboard(df, bb_df)

    # 3. Apify fallback for sparse artists
    df = scrape_missing_via_apify(df)

    # 4. Final dedup + enforce SONGS_PER_ARTIST cap
    df.drop_duplicates(subset=["artist", "song"], keep="first", inplace=True)
    df = (
        df.groupby("artist", group_keys=False)
        .apply(lambda g: g.head(SONGS_PER_ARTIST))
        .reset_index(drop=True)
    )

    # 5. Summary
    print("\nCoverage summary:")
    summary = df.groupby("artist").size().sort_values(ascending=False)
    print(summary.to_string())
    print(f"\nTotal songs: {len(df)}  |  Artists: {df['artist'].nunique()}")

    # 6. Save
    CLEANED_SONGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLEANED_SONGS_PATH, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
    print(f"\nSaved → {CLEANED_SONGS_PATH}")

def ingest_dynamic_artist(artist_name: str):
    """
    Hardened Ingestion Hook for UI.
    1. Fetch from Genius (Hardened)
    2. Clean and append to cleaned_songs.jsonl (Idempotent)
    """
    print(f"\n[DYNAMIC] Hardened Ingest for: '{artist_name}'")
    
    # 1. Fetch
    fetcher = _load_fetcher()
    # Use max_songs consistent with pipeline (20 for speed)
    raw_path = fetcher.fetch_artist_songs(artist_name, max_songs=20)
    
    if not raw_path or not raw_path.exists():
        print(f"[DYNAMIC] Ingestion FAILED for '{artist_name}'")
        return False

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 2. Check for existing songs to avoid duplicates
    existing_keys = set()
    if CLEANED_SONGS_PATH.exists():
        with open(CLEANED_SONGS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    existing_keys.add(f"{rec['artist'].lower()}|||{rec['song'].lower()}")

    new_rows = []
    for item in raw_data:
        key = f"{item['artist'].lower()}|||{item['song'].lower()}"
        if key not in existing_keys:
            new_rows.append({
                "artist": item["artist"],
                "song": item["song"],
                "lyrics": item["lyrics"],
                "genre": item.get("genre", "unknown"),
                "year": item.get("year", None),
                "chart_rank": None,
            })
    
    if not new_rows:
        print(f"[DYNAMIC] All {len(raw_data)} songs already exist in dataset. Skipping append.")
        return True

    # 3. Append to cleaned_songs.jsonl
    CLEANED_SONGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLEANED_SONGS_PATH, "a", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    print(f"[DYNAMIC] SUCCESS: Appended {len(new_rows)} new songs for '{artist_name}'")
    return True


if __name__ == "__main__":
    main()
