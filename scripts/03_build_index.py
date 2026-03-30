"""
Step 4 & 5: Chunking → Embeddings → FAISS Index
================================================
- Chunk each song into verse/chorus sections (preserving metadata)
- Embed each chunk with OpenAI text-embedding-3-small
- Store vectors in a FAISS IndexFlatIP index
- Store metadata alongside in chunks.jsonl + faiss_meta.jsonl

Run: python scripts/03_build_index.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import (
    CHUNKS_PATH,
    EMBEDDING_MODEL,
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
    LABELED_SONGS_PATH,
)

import openai
import faiss

from utils.cache import EmbeddingCache

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Section headers the LLM puts in structure strings ──────────────────────
SECTION_PATTERN = re.compile(
    r"(verse\s*\d*|pre[-\s]?chorus|chorus|hook|bridge|outro|intro|refrain|breakdown)",
    re.IGNORECASE,
)

# ── Chunking ────────────────────────────────────────────────────────────────

def split_into_sections(lyrics: str) -> list[dict]:
    """
    Split lyrics into sections by blank-line boundaries.
    Each paragraph is treated as one chunk (verse / chorus / etc.).
    Returns list of {"label": str, "text": str}
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", lyrics) if p.strip()]
    sections = []
    section_counts: dict[str, int] = {}

    for para in paragraphs:
        if len(para) < 20:
            continue  # skip tiny stubs
        # Default label based on position
        label = "section"
        lines = para.split("\n")
        first = lines[0].lower()
        if "chorus" in first or "hook" in first:
            label = "chorus"
        elif "verse" in first:
            label = "verse"
        elif "bridge" in first:
            label = "bridge"
        elif "outro" in first:
            label = "outro"
        elif "intro" in first:
            label = "intro"
        elif len(lines) <= 4:
            label = "chorus"  # short paragraphs are usually hooks
        else:
            label = "verse"

        section_counts[label] = section_counts.get(label, 0) + 1
        sections.append({"label": f"{label}_{section_counts[label]}", "text": para})

    # If no split found, treat whole lyrics as one chunk
    if not sections:
        sections = [{"label": "full", "text": lyrics.strip()}]

    return sections


def build_chunks(songs: list[dict]) -> list[dict]:
    """Convert songs to chunk records."""
    chunks = []
    for song in songs:
        sections = split_into_sections(song["lyrics"])
        for sec in sections:
            chunks.append(
                {
                    "chunk_id": f"{song['artist']}|||{song['song']}|||{sec['label']}",
                    "artist": song["artist"],
                    "song": song["song"],
                    "section": sec["label"],
                    "text": sec["text"],
                    "structure": song.get("structure", ""),
                    "theme": song.get("theme", ""),
                    "genre": song.get("genre", ""),
                    "year": song.get("year", None),
                    "chart_rank": song.get("chart_rank", None),
                }
            )
    return chunks


# ── Embeddings ───────────────────────────────────────────────────────────────

EMBED_BATCH = 100  # OpenAI allows up to 2048 per call; we use 100 to be safe


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via OpenAI. Returns list of float vectors."""
    for attempt in range(4):
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except openai.RateLimitError:
            wait = 2 ** (attempt + 2)
            print(f"\n  [RateLimit] waiting {wait}s …")
            time.sleep(wait)
        except Exception as exc:
            print(f"\n  [ERROR] embedding failed: {exc}")
            raise
    raise RuntimeError("Embedding failed after retries")


def embed_all_chunks(chunks: list[dict]) -> np.ndarray:
    """Return (N, D) float32 array of embeddings for all chunks.

    Uses EmbeddingCache so unchanged chunks are never re-embedded.
    Cache is saved to disk after every batch for crash-safety.
    """
    cache = EmbeddingCache()
    cache_hits = 0

    # Split into cached vs. uncached
    uncached_indices: list[int] = []
    all_vecs: list[np.ndarray | None] = [None] * len(chunks)

    for i, chunk in enumerate(chunks):
        cached_vec = cache.get(chunk["chunk_id"], chunk["text"])
        if cached_vec is not None:
            all_vecs[i] = cached_vec
            cache_hits += 1
        else:
            uncached_indices.append(i)

    if cache_hits:
        print(f"  Cache hits: {cache_hits}/{len(chunks)} chunks skipped.")

    # Embed uncached chunks in batches
    for batch_start in tqdm(range(0, len(uncached_indices), EMBED_BATCH), desc="Embedding"):
        batch_idx = uncached_indices[batch_start : batch_start + EMBED_BATCH]
        batch_texts = [chunks[i]["text"] for i in batch_idx]
        vecs = embed_texts(batch_texts)
        for i, vec in zip(batch_idx, vecs):
            arr = np.array(vec, dtype=np.float32)
            all_vecs[i] = arr
            cache.set(chunks[i]["chunk_id"], chunks[i]["text"], arr)
        cache.save()
        time.sleep(0.05)

    return np.array(all_vecs, dtype=np.float32)


# ── FAISS index ──────────────────────────────────────────────────────────────

def build_faiss_index(vectors: np.ndarray) -> faiss.Index:
    """Build a normalised inner-product (cosine) FAISS index."""
    faiss.normalize_L2(vectors)
    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not LABELED_SONGS_PATH.exists():
        print(f"[ERROR] {LABELED_SONGS_PATH} not found. Run 02_label_songs.py first.")
        sys.exit(1)

    # Load labeled songs
    songs = []
    with open(LABELED_SONGS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                songs.append(json.loads(line))
    print(f"Loaded {len(songs)} labeled songs.")

    # Chunk
    print("Chunking lyrics …")
    chunks = build_chunks(songs)
    print(f"  → {len(chunks)} chunks")

    # Save chunks
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  Saved chunks → {CHUNKS_PATH}")

    # Embed
    print("Embedding chunks …")
    vectors = embed_all_chunks(chunks)
    print(f"  → vectors shape: {vectors.shape}")

    # Build FAISS index
    print("Building FAISS index …")
    index = build_faiss_index(vectors)
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    print(f"  Saved FAISS index → {FAISS_INDEX_PATH}")

    # Save metadata (parallel to index rows)
    with open(FAISS_META_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            # Exclude the full text from meta to keep file lean; store it in chunks.jsonl
            meta = {k: v for k, v in c.items() if k != "text"}
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    print(f"  Saved FAISS metadata → {FAISS_META_PATH}")

    print("\nIndex build complete.")


if __name__ == "__main__":
    main()
