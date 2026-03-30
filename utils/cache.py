"""
Embedding Cache
===============
Stores chunk_id → embedding vector in a local pickle file so that
re-running scripts/03_build_index.py does not re-embed unchanged chunks.

The cache key is a SHA-256 hash of (chunk_id + text) so any edit to
the text automatically invalidates its cached vector.

Usage:
    from utils.cache import EmbeddingCache
    cache = EmbeddingCache()
    vec = cache.get(chunk_id, text)   # None if not cached
    cache.set(chunk_id, text, vector)
    cache.save()
"""

import hashlib
import pickle
import sys
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.config import EMBED_CACHE_PATH


def _cache_key(chunk_id: str, text: str) -> str:
    payload = f"{chunk_id}|||{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """File-backed dict mapping cache_key → float32 vector."""

    def __init__(self, path: Path = EMBED_CACHE_PATH):
        self._path = path
        self._store: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    self._store = pickle.load(f)
            except Exception:
                self._store = {}

    def get(self, chunk_id: str, text: str) -> Optional[np.ndarray]:
        key = _cache_key(chunk_id, text)
        vec = self._store.get(key)
        if vec is None:
            return None
        return np.array(vec, dtype=np.float32)

    def set(self, chunk_id: str, text: str, vector: np.ndarray) -> None:
        key = _cache_key(chunk_id, text)
        self._store[key] = vector.tolist()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(self._store, f)

    def __len__(self) -> int:
        return len(self._store)
