"""
RAG Retriever  (v3 — hybrid BM25 + vector + diagnostics)
=========================================================
New in this version:
  - Hybrid retrieval: combines FAISS cosine similarity (vector score)
    with BM25 keyword score.  Final score = VECTOR_WEIGHT * v + BM25_WEIGHT * b.
    BM25 index is built in-memory at init from the loaded chunks.
  - Optional LLM re-ranking: retrieves RERANK_CANDIDATE_N chunks, asks
    GPT to score relevance, keeps the best TOP_K.  Off by default.
  - explain_retrieval(query, artists): returns a dict describing exactly
    why each chunk was selected, what path was taken (artist/genre/corpus),
    and per-chunk breakdown of vector vs keyword scores.
  - Each returned chunk carries:
      score         float   hybrid score
      vector_score  float   FAISS cosine component
      keyword_score float   BM25 component
      retrieval_path str    "artist" | "genre" | "full_corpus"
      fallback      str|None

Usage:
    from rag.retriever import Retriever
    r = Retriever()
    chunks = r.retrieve("heartbreak", artists=["Drake", "SZA"], top_k=8)
    diag   = r.explain_retrieval("heartbreak", artists=["Drake"])
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
import openai
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import (
    ARTIST_GENRE_MAP,
    BM25_B,
    BM25_K1,
    BM25_WEIGHT,
    CHUNKS_PATH,
    EMBEDDING_MODEL,
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
    FALLBACK_TOP_K,
    MIN_CHUNKS_THRESHOLD,
    RERANK_CANDIDATE_N,
    RERANK_ENABLED,
    RERANK_MODEL,
    TOP_K,
    VECTOR_WEIGHT,
)

from utils.cache_utils import embedding_cache
import concurrent.futures

_oai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _tokenise(text: str) -> list[str]:
    """Lowercase alpha tokens, length > 1."""
    return re.findall(r"[a-z]{2,}", text.lower())


# ── BM25 index ────────────────────────────────────────────────────────────

class BM25Index:
    """Lightweight in-memory BM25 index over a list of text documents."""

    def __init__(self, docs: list[str], k1: float = BM25_K1, b: float = BM25_B):
        self.k1 = k1
        self.b = b
        self.n = len(docs)

        # Per-document term frequencies
        self._tf: list[dict[str, int]] = []
        # Document lengths
        self._dl: list[int] = []
        # Document-frequency per term
        self._df: dict[str, int] = defaultdict(int)

        for doc in docs:
            tokens = _tokenise(doc)
            tf: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self._tf.append(dict(tf))
            self._dl.append(len(tokens))
            for t in set(tokens):
                self._df[t] += 1

        self._avgdl = sum(self._dl) / self.n if self.n else 1.0

    def score(self, doc_idx: int, query_tokens: list[str]) -> float:
        """Return BM25 score for a single document against query tokens."""
        tf = self._tf[doc_idx]
        dl = self._dl[doc_idx]
        score = 0.0
        for t in query_tokens:
            if t not in tf:
                continue
            df = self._df.get(t, 0)
            idf = math.log((self.n - df + 0.5) / (df + 0.5) + 1.0)
            tf_norm = (tf[t] * (self.k1 + 1)) / (
                tf[t] + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            )
            score += idf * tf_norm
        return score

    def scores_for_subset(
        self, query_tokens: list[str], indices: list[int]
    ) -> dict[int, float]:
        """Return {idx: bm25_score} for each index in `indices`."""
        raw = {i: self.score(i, query_tokens) for i in indices}
        # Normalise to [0, 1] against the max in this subset
        max_s = max(raw.values()) if raw else 1.0
        if max_s == 0:
            return {i: 0.0 for i in indices}
        return {i: v / max_s for i, v in raw.items()}


# ── Main Retriever ────────────────────────────────────────────────────────

class Retriever:
    """
    Hybrid FAISS + BM25 retriever with metadata-first filtering,
    genre fallback, optional LLM re-ranking, and retrieval diagnostics.
    """

    def __init__(
        self,
        top_k: int = TOP_K,
        bm25_weight: float = BM25_WEIGHT,
        vector_weight: float = VECTOR_WEIGHT,
        rerank_enabled: bool = RERANK_ENABLED,
        rerank_candidate_n: int = RERANK_CANDIDATE_N,
    ):
        self.top_k = top_k
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rerank_enabled = rerank_enabled
        self.rerank_candidate_n = rerank_candidate_n

        self.reload()

        # Warm the OpenAI client to avoid thread-safety issues with lazy imports
        try:
            _ = _oai_client.embeddings
        except:
            pass

    def reload(self):
        """
        Reload the FAISS index, metadata, and BM25 indices from disk.
        Useful after dynamic artist ingestion to update the in-memory state.
        """
        if not FAISS_INDEX_PATH.exists():
            raise FileNotFoundError(
                f"FAISS index not found at {FAISS_INDEX_PATH}. "
                "Run scripts/03_build_index.py first."
            )

        # ── FAISS index ───────────────────────────────────────────────────
        self.index: faiss.Index = faiss.read_index(str(FAISS_INDEX_PATH))

        # ── Metadata + chunks ─────────────────────────────────────────────
        self.meta: list[dict] = []
        with open(FAISS_META_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.meta.append(json.loads(line))

        self.chunks: list[dict] = []
        with open(CHUNKS_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    self.chunks.append(json.loads(line))

        assert len(self.meta) == len(self.chunks), (
            f"Metadata ({len(self.meta)}) / chunks ({len(self.chunks)}) count mismatch — rebuild index."
        )

        # ── Reconstruct vectors for sub-index construction ────────────────
        n, dim = self.index.ntotal, self.index.d
        self._vectors = np.zeros((n, dim), dtype=np.float32)
        self.index.reconstruct_n(0, n, self._vectors)

        # ── BM25 index over chunk texts ───────────────────────────────────
        self._bm25 = BM25Index([c["text"] for c in self.chunks])

        # ── Inverted indices for O(1) artist/genre lookups ────────────────
        self._artist_idx: dict[str, list[int]] = defaultdict(list)
        self._genre_idx: dict[str, list[int]] = defaultdict(list)
        for i, chunk in enumerate(self.chunks):
            self._artist_idx[_normalise_name(chunk["artist"])].append(i)
            # Use artist_genre_map as fallback
            genre = (chunk.get("genre") or "").lower().strip()
            if not genre:
                genre = ARTIST_GENRE_MAP.get(chunk["artist"], "unknown").lower()
            self._genre_idx[genre].append(i)

        self._artist_to_genre: dict[str, str] = {
            _normalise_name(a): g for a, g in ARTIST_GENRE_MAP.items()
        }

    # ── Embedding ──────────────────────────────────────────────────────────

    def _embed(self, text: str) -> np.ndarray:
        """Return a normalised (1, D) float32 embedding (with caching)."""
        cached = embedding_cache.get(text)
        if cached is not None:
            return np.array(cached, dtype=np.float32).reshape(1, -1)

        for attempt in range(3):
            try:
                resp = _oai_client.embeddings.create(
                    model=EMBEDDING_MODEL, input=[text]
                )
                raw_vec = resp.data[0].embedding
                vec = np.array(raw_vec, dtype=np.float32).reshape(1, -1)
                faiss.normalize_L2(vec)
                
                # Cache the list format
                embedding_cache.set(text, raw_vec)
                return vec
            except openai.RateLimitError:
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("Embedding failed after retries")

    # ── Hybrid search ──────────────────────────────────────────────────────

    def _hybrid_search(
        self,
        query_vec: np.ndarray,
        query_tokens: list[str],
        candidate_indices: list[int],
        top_k: int,
    ) -> list[tuple[float, float, float, int]]:
        """
        Search a subset of chunks using hybrid scoring.

        Returns list of (hybrid_score, vector_score, keyword_score, orig_idx)
        sorted by hybrid_score descending.
        """
        if not candidate_indices:
            return []

        # ── Vector scores via FAISS sub-index ─────────────────────────────
        def _get_vector_scores():
            sub_vecs = self._vectors[candidate_indices]
            sub_index = faiss.IndexFlatIP(sub_vecs.shape[1])
            sub_index.add(sub_vecs)
            k = min(len(candidate_indices), max(top_k, RERANK_CANDIDATE_N))
            raw_scores, local_ids = sub_index.search(query_vec, k)
            v_map = {}
            for score, lid in zip(raw_scores[0], local_ids[0]):
                if lid >= 0:
                    orig = candidate_indices[lid]
                    v_map[orig] = float(max(0.0, score))  # clamp negatives
            return v_map

        # ── BM25 keyword scores ────────────────────────────────────────────
        def _get_kw_scores(subset_indices=None):
            # If subset_indices provided, only score those. 
            # In purely parallel mode, we might score ALL candidate_indices.
            # But BM25 is fast, let's just score the candidate_indices filter directly.
            target = subset_indices if subset_indices is not None else candidate_indices
            return self._bm25.scores_for_subset(query_tokens, target)

        # Execute BM25 and Vector in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            v_future = executor.submit(_get_vector_scores)
            k_future = executor.submit(_get_kw_scores)
            vec_map = v_future.result()
            kw_map = k_future.result()

        # ── Normalization ──────────────────────────────────────────────────
        def _normalize(score_dict: dict[int, float]) -> dict[int, float]:
            if not score_dict: return {}
            vals = list(score_dict.values())
            min_s = min(vals)
            max_s = max(vals)
            diff = max_s - min_s
            if diff < 1e-8:
                return {k: 1.0 for k in score_dict} # all equal -> all 1.0
            return {k: (s - min_s) / diff for k, s in score_dict.items()}

        vec_norm = _normalize(vec_map)
        kw_norm = _normalize(kw_map)

        # ── Combine ────────────────────────────────────────────────────────
        results: list[tuple[float, float, float, int]] = []
        for orig_idx, vs in vec_map.items():
            vn = vec_norm.get(orig_idx, 0.0)
            kn = kw_norm.get(orig_idx, 0.0)
            # Normalize by total weights to ensure score is in [0, 1] range
            w_total = self.vector_weight + self.bm25_weight
            hybrid = (self.vector_weight * vn + self.bm25_weight * kn) / w_total if w_total > 0 else 0.0
            hybrid = min(max(hybrid, 0.0), 1.0)
            results.append((hybrid, vs, kn, orig_idx))

        results.sort(key=lambda x: x[0], reverse=True)
        return results

    # ── LLM re-ranking ─────────────────────────────────────────────────────

    def _llm_rerank(
        self,
        query: str,
        candidates: list[tuple[float, float, float, int]],
        top_k: int,
    ) -> list[tuple[float, float, float, int]]:
        """
        Ask GPT to score each candidate chunk's relevance to the query,
        then re-sort and return top_k.  Called only when RERANK_ENABLED=True.
        """
        if len(candidates) <= top_k:
            return candidates

        chunks_text = "\n\n".join(
            f"[{i+1}] {self.chunks[orig]['artist']} / {self.chunks[orig]['song']}:\n"
            f"{self.chunks[orig]['text'][:300]}"
            for i, (_, _, _, orig) in enumerate(candidates[:self.rerank_candidate_n])
        )

        prompt = (
            f"Query: \"{query}\"\n\n"
            f"Rate each lyric chunk based on: 1) Stylistic similarity, 2) Lyrical tone, and 3) Emotional match to the query.\n"
            f"Prioritize artist-authentic chunks that feel like they belong in a professional song.\n"
            f"Score on a scale of 1-10.\n"
            f"Respond ONLY with a JSON array of integers, one per chunk, in order.\n"
            f"Example: [7, 4, 9, 2, 6]\n\n"
            f"Chunks:\n{chunks_text}"
        )

        try:
            resp = _oai_client.chat.completions.create(
                model=RERANK_MODEL,
                temperature=0,
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content.strip()
            scores = json.loads(re.search(r"\[.*?\]", raw, re.S).group())
        except Exception:
            return candidates[:top_k]  # fall back silently

        reranked: list[tuple[float, float, float, int]] = []
        for i, (hybrid, vs, ks, orig) in enumerate(candidates[:self.rerank_candidate_n]):
            llm_s = float(scores[i]) / 10.0 if i < len(scores) else 0.5
            new_hybrid = 0.6 * hybrid + 0.4 * llm_s
            reranked.append((new_hybrid, vs, ks, orig))

        reranked.sort(key=lambda x: x[0], reverse=True)
        return reranked[:top_k]

    # ── Candidate helpers ──────────────────────────────────────────────────

    def _artist_candidates(self, artists: list[str]) -> list[int]:
        out = []
        for a in artists:
            out.extend(self._artist_idx.get(_normalise_name(a), []))
        return out

    def _genre_candidates(self, artists: list[str]) -> list[int]:
        genres: set[str] = set()
        for a in artists:
            g = self._artist_to_genre.get(_normalise_name(a), "")
            if g:
                genres.add(g)
        out = []
        for g in genres:
            out.extend(self._genre_idx.get(g, []))
        return out

    # ── Format output ──────────────────────────────────────────────────────

    def _format(
        self,
        results: list[tuple[float, float, float, int]],
        top_k: int,
        retrieval_path: str = "artist",
        fallback_used: Optional[str] = None,
    ) -> list[dict]:
        out = []
        for hybrid, vs, ks, idx in results[:top_k]:
            chunk = dict(self.chunks[idx])
            chunk["score"] = round(hybrid, 4)
            chunk["vector_score"] = round(vs, 4)
            chunk["keyword_score"] = round(ks, 4)
            chunk["retrieval_path"] = retrieval_path
            if fallback_used:
                chunk["fallback"] = fallback_used
            out.append(chunk)
        return out

    # ── Public: retrieve ───────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        artists: Optional[list[str]] = None,
        top_k: Optional[int] = None,
        vector_weight: Optional[float] = None,
        bm25_weight: Optional[float] = None,
    ) -> list[dict]:
        """
        Retrieve top_k chunks using hybrid scoring.
        """
        top_k = top_k or self.top_k
        query_vec = self._embed(query)
        query_tokens = _tokenise(query)
        
        orig_vw, orig_bw = self.vector_weight, self.bm25_weight
        if vector_weight is not None: self.vector_weight = vector_weight
        if bm25_weight is not None: self.bm25_weight = bm25_weight

        fallback_used: Optional[str] = None
        retrieval_path = "full_corpus"
        candidate_n = self.rerank_candidate_n if self.rerank_enabled else top_k

        if artists:
            # ── Path 1: artist ────────────────────────────────────────────
            if len(artists) > 1:
                # Artist Balancing
                results = []
                per_artist_n = max(1, candidate_n // len(artists))
                for a in artists:
                    cands = self._artist_candidates([a])
                    a_results = self._hybrid_search(query_vec, query_tokens, cands, per_artist_n)
                    results.extend(a_results)
                # Re-sort combined
                results.sort(key=lambda x: x[0], reverse=True)
            else:
                artist_cands = self._artist_candidates(artists)
                results = self._hybrid_search(query_vec, query_tokens, artist_cands, candidate_n)

            if len(results) >= MIN_CHUNKS_THRESHOLD:
                retrieval_path = "artist"
            else:
                # ── Path 2: genre fallback ────────────────────────────────
                artist_set = {orig for _, _, _, orig in results}
                genre_cands = [i for i in self._genre_candidates(artists)
                               if i not in artist_set]
                genre_results = self._hybrid_search(
                    query_vec, query_tokens, genre_cands, FALLBACK_TOP_K
                )
                combined = results + genre_results
                combined.sort(key=lambda x: x[0], reverse=True)

                if len(combined) >= MIN_CHUNKS_THRESHOLD:
                    results = combined
                    retrieval_path = "genre"
                    fallback_used = "genre"
                else:
                    # ── Path 3: full corpus ───────────────────────────────
                    all_cands = list(range(len(self.chunks)))
                    results = self._hybrid_search(
                        query_vec, query_tokens, all_cands, FALLBACK_TOP_K
                    )
                    retrieval_path = "full_corpus"
                    fallback_used = "full_corpus"
        else:
            all_cands = list(range(len(self.chunks)))
            results = self._hybrid_search(query_vec, query_tokens, all_cands, top_k)

        # ── Optional LLM re-ranking ────────────────────────────────────────
        if self.rerank_enabled and len(results) > top_k:
            results = self._llm_rerank(query, results, top_k)

        out = self._format(results, top_k, retrieval_path, fallback_used)
        
        # Restore original weights
        self.vector_weight = orig_vw
        self.bm25_weight = orig_bw
        
        return out

    # ── Public: explain_retrieval ──────────────────────────────────────────

    def explain_retrieval(
        self,
        query: str,
        artists: Optional[list[str]] = None,
        top_k: int = TOP_K,
    ) -> dict:
        """
        Return a diagnostic dict explaining why each chunk was selected.

        Schema
        ------
        {
          "query": str,
          "artists_requested": list[str],
          "retrieval_path": "artist" | "genre" | "full_corpus",
          "fallback_reason": str | None,
          "artist_corpus_sizes": {artist: int},
          "genre_corpus_sizes": {genre: int},
          "chunks": [
            {
              "rank": int,
              "artist": str,
              "song": str,
              "section": str,
              "score": float,
              "vector_score": float,
              "keyword_score": float,
              "retrieval_path": str,
              "why": str   human-readable explanation
            }
          ]
        }
        """
        chunks = self.retrieve(query=query, artists=artists, top_k=top_k)

        # Build corpus size info
        artist_sizes: dict[str, int] = {}
        if artists:
            for a in artists:
                key = _normalise_name(a)
                artist_sizes[a] = len(self._artist_idx.get(key, []))

        genre_sizes: dict[str, int] = {}
        if artists:
            for a in artists:
                g = self._artist_to_genre.get(_normalise_name(a), "")
                if g:
                    genre_sizes[g] = len(self._genre_idx.get(g, []))

        # Determine fallback reason
        fallback_reason: Optional[str] = None
        path = chunks[0]["retrieval_path"] if chunks else "full_corpus"
        if path == "genre":
            fallback_reason = (
                f"Artist(s) had fewer than {MIN_CHUNKS_THRESHOLD} matching chunks; "
                f"expanded to same-genre artists."
            )
        elif path == "full_corpus":
            fallback_reason = (
                "Neither artist-filtered nor genre-filtered search returned enough "
                "results; fell back to full corpus search."
            )

        # Annotate each chunk with a human-readable 'why'
        annotated: list[dict] = []
        for i, c in enumerate(chunks, 1):
            vs, ks = c.get("vector_score", 0), c.get("keyword_score", 0)
            if vs > ks:
                signal = f"semantic similarity (vector={vs:.3f}) > keyword match ({ks:.3f})"
            elif ks > vs:
                signal = f"keyword match ({ks:.3f}) > semantic similarity (vector={vs:.3f})"
            else:
                signal = f"equal vector/keyword scores ({vs:.3f})"

            annotated.append({
                "rank": i,
                "artist": c["artist"],
                "song": c["song"],
                "section": c.get("section", ""),
                "theme": c.get("theme", ""),
                "score": c["score"],
                "vector_score": vs,
                "keyword_score": ks,
                "retrieval_path": c.get("retrieval_path", path),
                "fallback": c.get("fallback"),
                "why": (
                    f"Selected via {c.get('retrieval_path', path)} path. "
                    f"Hybrid score {c['score']:.3f} driven by {signal}."
                ),
            })

        return {
            "query": query,
            "artists_requested": artists or [],
            "retrieval_path": path,
            "fallback_reason": fallback_reason,
            "rerank_enabled": self.rerank_enabled,
            "artist_corpus_sizes": artist_sizes,
            "genre_corpus_sizes": genre_sizes,
            "chunks": annotated,
        }

    # ── Utilities ─────────────────────────────────────────────────────────

    def retrieval_quality(self, chunks: list[dict]) -> float:
        """Mean hybrid score of retrieved chunks — proxy for retrieval confidence."""
        if not chunks:
            return 0.0
        score = sum(c.get("score", 0.0) for c in chunks) / len(chunks)
        return round(max(0.0, min(score, 1.0)), 4)

    def available_artists(self) -> list[str]:
        return sorted({c["artist"] for c in self.chunks})

    def chunk_count_per_artist(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for c in self.chunks:
            counts[c["artist"]] += 1
        return dict(counts)
