"""
Step 3: LLM Labeling
====================
For each song extract:
  - structure  (e.g. "Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Outro")
  - theme      (e.g. "heartbreak, introspection")

Uses OpenAI with temperature=0 for deterministic outputs.
Saves to labeled_songs.jsonl (cleaned_songs + added fields).

Run: python scripts/02_label_songs.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import CLEANED_SONGS_PATH, LABELED_SONGS_PATH, LABELING_MODEL

# ── OpenAI client ────────────────────────────────────────────────────────────

import openai

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Labeling prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a music analyst. Given song lyrics, extract two things:
1. structure: the song sections in order (e.g. "Verse 1 → Pre-Chorus → Chorus → Verse 2 → Chorus → Bridge → Outro")
2. theme: 2–4 keywords describing the main themes/emotions (e.g. "heartbreak, self-confidence, party, nostalgia")

Respond ONLY with valid JSON in this exact format:
{"structure": "...", "theme": "..."}

Do NOT include any explanation or markdown."""

def label_song(lyrics: str) -> dict:
    """Call OpenAI to extract structure and theme from lyrics."""
    # Trim to keep cost low (first ~800 tokens is enough for structure/theme)
    excerpt = lyrics[:3000]

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=LABELING_MODEL,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Lyrics:\n{excerpt}"},
                ],
                max_tokens=120,
            )
            raw = response.choices[0].message.content.strip()
            # Strip accidental markdown code fences
            raw = raw.strip("`").strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            result = json.loads(raw)
            return {
                "structure": result.get("structure", ""),
                "theme": result.get("theme", ""),
            }
        except json.JSONDecodeError:
            return {"structure": "", "theme": ""}
        except openai.RateLimitError:
            wait = 2 ** (attempt + 2)
            print(f"\n  [RateLimit] waiting {wait}s …")
            time.sleep(wait)
        except Exception as exc:
            print(f"\n  [WARN] labeling error: {exc}")
            return {"structure": "", "theme": ""}

    return {"structure": "", "theme": ""}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not CLEANED_SONGS_PATH.exists():
        print(f"[ERROR] {CLEANED_SONGS_PATH} not found. Run 01_build_dataset.py first.")
        sys.exit(1)

    # Load already-labeled songs to allow resuming
    labeled: dict[str, dict] = {}
    if LABELED_SONGS_PATH.exists():
        with open(LABELED_SONGS_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    key = f"{rec['artist']}|||{rec['song']}"
                    labeled[key] = rec

    # Load all cleaned songs
    songs = []
    with open(CLEANED_SONGS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                songs.append(json.loads(line))

    print(f"Total songs: {len(songs)}  |  Already labeled: {len(labeled)}")

    outfile = open(LABELED_SONGS_PATH, "w", encoding="utf-8")

    # Write already-labeled ones first
    for rec in labeled.values():
        outfile.write(json.dumps(rec, ensure_ascii=False) + "\n")

    new_count = 0
    for song in tqdm(songs, desc="Labeling"):
        key = f"{song['artist']}|||{song['song']}"
        if key in labeled:
            continue  # already done

        labels = label_song(song["lyrics"])
        song["structure"] = labels["structure"]
        song["theme"] = labels["theme"]
        outfile.write(json.dumps(song, ensure_ascii=False) + "\n")
        outfile.flush()
        new_count += 1

        # Small delay to stay within rate limits
        time.sleep(0.1)

    outfile.close()
    print(f"\nLabeled {new_count} new songs.  Saved → {LABELED_SONGS_PATH}")


if __name__ == "__main__":
    main()
