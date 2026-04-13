"""
RAG Pipeline  (v3 — style_strength + retrieval diagnostics + adaptive prompting)
================================================================================
New in this version:
  - style_strength parameter (0.0–1.0) flows through to prompt_builder
  - retrieval_quality computed from chunk scores, used to tune the prompt
  - retrieval_diagnostics dict included in every result for UI/eval use
  - PROMPT_VERSION stamped on every log record

Usage:
    from rag.pipeline import SongwritingPipeline
    pipe = SongwritingPipeline()
    result = pipe.run(
        artists=["Drake", "SZA"],
        theme="heartbreak",
        structure="Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Outro",
        style_strength=0.8,
    )
    print(result["lyrics"])
    print(result["retrieval_diagnostics"])
"""

from __future__ import annotations

import os
import time
import json
import re
import concurrent.futures
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from utils.cache_utils import expansion_cache
from rag.retriever import Retriever
from rag.prompt_builder import build_prompt
from rag.voice import VoiceGenerator
from rag.music import MusicGenerator
from utils.config import (
    FALLBACK_TOP_K,
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    LABELING_MODEL,
    MAX_RETRY_ATTEMPTS,
    MIN_CHUNKS_THRESHOLD,
    PROMPT_VERSION,
    STYLE_STRENGTH_DEFAULT,
    TOP_K,
    CHORUS_VALIDATION_ENABLED,
)
from utils.logger import log_generation
from rag.validator import ChorusValidator, score_hook, extract_lines

# ── Song structure presets ────────────────────────────────────────────────
STRUCTURES = {
    "Standard (V-C-V-C-B-C)":
        "Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Chorus → Outro",
    "Hook Heavy (V-H-V-H-H)":
        "Verse 1 → Hook → Verse 2 → Hook → Hook → Outro",
    "Verse Heavy (V-V-C-V-C)":
        "Verse 1 → Verse 2 → Chorus → Verse 3 → Chorus → Outro",
    "Simple (V-C-V-C)":
        "Verse 1 → Chorus → Verse 2 → Chorus",
    "Extended (Intro-V-PC-C-V-PC-C-B-C-Outro)":
        "Intro → Verse 1 → Pre-Chorus → Chorus → Verse 2 → Pre-Chorus"
        " → Chorus → Bridge → Chorus → Outro",
}


class SongwritingPipeline:
    """End-to-end RAG songwriting pipeline."""

    def __init__(self):
        self.retriever = Retriever()
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._validator = ChorusValidator() if CHORUS_VALIDATION_ENABLED else None
        self.voice_gen = VoiceGenerator()
        self.music_gen = MusicGenerator()

    def _expand_query(self, artists: list[str], theme: str) -> dict:
        """Use LLM to generate expanded queries (with caching)."""
        cache_key = {"artists": artists, "theme": theme}
        cached = expansion_cache.get(cache_key)
        if cached:
            return cached

        prompt = f"""
Given the theme '{theme}' for artist(s) {artists}, generate 4-6 related search query phrases 
including synonyms, emotional variations, and related concepts to retrieve lyrical inspiration.
Also classify the query type as either 'emotional' (abstract, feelings) or 'specific' (locations, concrete objects).

Respond ONLY with valid JSON:
{{
    "expanded_queries": ["query1", "query2", ...],
    "query_type": "emotional" | "specific"
}}
"""
        try:
            res = self._client.chat.completions.create(
                model=LABELING_MODEL, # Use mini for expansion too
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(res.choices[0].message.content.strip())
            expansion_cache.set(cache_key, data)
            return data
        except Exception as e:
            return {"expanded_queries": [theme], "query_type": "emotional"}

    def _generate_single(
        self, attempt_index: int, system_prompt: str, user_prompt: str, temperature: float
    ) -> tuple[str, Optional[Exception]]:
        """Worker for concurrent generation."""
        try:
            # slightly jitter temperature to guarantee variety across parallel runs
            jitter_temp = min(1.0, temperature + (attempt_index * 0.05))
            response = self._client.chat.completions.create(
                model=GENERATION_MODEL,
                temperature=jitter_temp,
                max_tokens=GENERATION_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            lyrics = response.choices[0].message.content.strip()
            if CHORUS_VALIDATION_ENABLED and self._validator:
                lyrics = self._validator.validate_and_fix(lyrics)
            return lyrics, None
        except Exception as exc:
            return "", exc

    def improve_hook_only(self, old_lyrics: str) -> str:
        """Regenerate ONLY the chorus section, keeping verses intact."""
        if not self._validator:
            return old_lyrics
        return self._validator.validate_and_fix(old_lyrics) # The validator re-writes the chorus using strict prompt

    def regenerate_version(self, artists, theme, structure, language, top_k, temperature, extra, style_strength, mode="Full Song") -> dict:
        """Helper to regenerate a single version with slightly different temp."""
        # This can be used for "Regenerate This Version" buttons in UI
        return self.run(artists, theme, structure, language, top_k, temperature, extra, style_strength, mode=mode)

    def _score_hook(self, hook: str) -> float:
        """
        Score a hook based on simplicity, repetition, and memorability (anchors).
        Migrated from LLM Judge to deterministic scoring in validator.py.
        """
        lines = extract_lines(hook)
        return score_hook(lines)

    def run(
        self,
        artists: list[str],
        theme: str,
        structure: str,
        language: str = "English",
        gender: str = "Neutral",
        bars: int = 16,
        reference_lyrics: str = "",
        num_variants: int = 1,
        top_k: int = TOP_K,
        temperature: float = GENERATION_TEMPERATURE,
        extra_instructions: str = "",
        style_strength: float = STYLE_STRENGTH_DEFAULT,
        mode: str = "Full Song", # Generation section mode (Verse, Chorus, Full)
        gen_mode: str = "generate", # Product mode (generate, continue, remix)
        perspective_mode: str = "same", # POV mode (same, opposite, response)
        analysis_mode: bool = False,
    ) -> dict:
        """
        Run the full pipeline and return a result dict.
        """
        t_start = time.time()

        # Adjust structure based on section mode
        if mode == "Chorus Only":
            structure = "Chorus"
        elif mode == "Verse Only":
            structure = "Verse 1"
        elif mode == "Bridge":
            structure = "Bridge"
        elif mode == "Hook Generator":
            structure = "Chorus"

        user_input = {
            "artists": artists,
            "theme": theme,
            "structure": structure,
            "language": language,
            "gender": gender,
            "bars": bars,
            "reference_lyrics": reference_lyrics,
            "num_variants": num_variants,
            "top_k": top_k,
            "temperature": temperature,
            "extra_instructions": extra_instructions,
            "style_strength": style_strength,
            "mode": mode,
            "gen_mode": gen_mode,
            "perspective_mode": perspective_mode,
            "analysis_mode": analysis_mode,
        }

        # ── Parallel Query Expansion & Base Retrieval ─────────────────────
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            expansion_future = executor.submit(self._expand_query, artists, theme)
            # Pre-fetch base theme while expansion is running
            base_retrieval_future = executor.submit(
                self.retriever.retrieve, 
                query=f"{' '.join(artists)} {theme} {structure}", 
                artists=artists, top_k=top_k
            )
            
            expansion = expansion_future.result()
            base_chunks = base_retrieval_future.result()

        expanded_queries = expansion.get("expanded_queries", [theme])
        q_type = expansion.get("query_type", "emotional")
        
        # Adjust weights dynamically
        v_weight = 0.8 if q_type == "emotional" else 0.5
        b_weight = 0.2 if q_type == "emotional" else 0.5
        
        # ── Parallel Multi-Query Retrieval ────────────────────────────────
        all_chunks_dict = {c["chunk_id"]: c for c in base_chunks}
        
        def _fetch(eq: str):
            q = f"{' '.join(artists)} {eq} {structure}"
            return self.retriever.retrieve(
                query=q, artists=artists, top_k=top_k, 
                vector_weight=v_weight, bm25_weight=b_weight
            )

        # Remove base theme from expanded queries if present to avoid redundancy
        other_queries = [q for q in expanded_queries if q.lower() != theme.lower()][:4]

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(other_queries) + 1) as executor:
            future_to_query = {executor.submit(_fetch, eq): eq for eq in other_queries}
            for future in concurrent.futures.as_completed(future_to_query):
                c_list = future.result()
                for c in c_list:
                    all_chunks_dict[c["chunk_id"]] = c
                
        # convert back to list and take top according to max hybrid score observed
        chunks = list(all_chunks_dict.values())
        chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        chunks = chunks[:top_k]

        retrieval_fallback = any(c.get("fallback") for c in chunks)

        # Last-resort: if too sparse
        if len(chunks) < MIN_CHUNKS_THRESHOLD:
            chunks = self.retriever.retrieve(query=theme, top_k=FALLBACK_TOP_K)
            retrieval_fallback = True

        # Compute retrieval quality (mean hybrid score)
        rq = self.retriever.retrieval_quality(chunks)

        # Retrieval diagnostics for logging / UI
        retrieval_diagnostics = {
            "path": chunks[0].get("retrieval_path", "unknown") if chunks else "none",
            "fallback": chunks[0].get("fallback") if chunks else None,
            "n_chunks": len(chunks),
            "quality": rq,
            "query_type": q_type,
            "expanded_queries": expanded_queries,
            "top_scores": [round(c.get("score", 0), 4) for c in chunks[:3]],
        }

        # ── Step 3: Prompt Building ───────────────────────────────────────
        system_prompt, user_prompt = build_prompt(
            artists=artists,
            theme=theme,
            structure=structure,
            retrieved_chunks=chunks,
            language=language,
            gender=gender,
            bars=bars,
            reference_lyrics=reference_lyrics,
            mode=gen_mode,
            perspective_mode=perspective_mode,
            extra_instructions=extra_instructions,
            style_strength=style_strength,
            retrieval_quality=rq,
            analysis_mode=analysis_mode,
        )

        if analysis_mode:
            # Short-circuit for analysis
            response = self._client.chat.completions.create(
                model=GENERATION_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            analysis = response.choices[0].message.content.strip()
            return {"analysis": analysis, "latency_ms": int((time.time() - t_start) * 1000)}

        # ── Step 4: Multi-variant Generation ──────────────────────────────
        versions = []
        last_error: Optional[Exception] = None

        # Diverse Anchor Strategy for Hook Generator
        hook_variants = [
            "REQUISITE: Include a specific location anchor (street, city, or place).",
            "REQUISITE: Include a concrete object anchor (car, watch, bottle, or clothing).",
            "REQUISITE: Include a specific time or seasonal anchor (midnight, morning, or day of week).",
            "REQUISITE: Include a weather-based anchor (rain, sun, fog).",
            "REQUISITE: Include a sensory anchor (scent, sound, touch)."
        ] if mode == "Hook Generator" else [""] * num_variants

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, num_variants)) as executor:
            futures = [
                executor.submit(
                    self._generate_single, 
                    i, 
                    system_prompt, 
                    user_prompt + (f"\n\n{hook_variants[i % 5]}" if mode == "Hook Generator" else ""), 
                    temperature
                )
                for i in range(num_variants)
            ]
            for future in concurrent.futures.as_completed(futures):
                lyr, err = future.result()
                if err:
                    last_error = err
                elif lyr:
                    versions.append(lyr)

        latency_ms = int((time.time() - t_start) * 1000)
        
        # ── Identify Best Version (Style Fidelity) ───────────────────────
        def _score_style_fidelity(lyr: str, context_chunks: list[dict], language: str = "English") -> float:
            # Deterministic: Jaccard similarity of vocabulary with artist chunks
            lyr_words = set(re.findall(r"\w+", lyr.lower()))
            ctx_words = set()
            for c in context_chunks:
                ctx_words.update(re.findall(r"\w+", c["text"].lower()))
            if not ctx_words: return 0.0
            
            intersection = lyr_words.intersection(ctx_words)
            raw_overlap = len(intersection) / len(lyr_words) if lyr_words else 0.0
            
            # Calibration: 0.15 raw overlap is actually very high for lyrics. 
            # We map [0.05, 0.25] -> [0.60, 0.95] for a more "human-friendly" production scale.
            if raw_overlap < 0.05:
                fidelity = 0.3 + (raw_overlap / 0.05) * 0.3
            else:
                fidelity = 0.6 + min(0.35, ((raw_overlap - 0.05) / 0.20) * 0.35)
                
            # CROSS-LANGUAGE NORMALIZATION:
            # If generating in a non-English language (e.g., Spanish) but chunks are primarily English,
            # we apply a "Persona Transfer" boost because vocabulary overlap is naturally biased.
            if language.lower() != "english":
                # We assume TARGET_ARTISTS are English-primary. If the user intentionally shifts language,
                # we increase the score to value "Stylistic Tone" over "Word-for-word matching".
                fidelity = min(0.95, fidelity + 0.25)
                
            return round(fidelity, 3)

        scored_versions = []
        for v in versions:
            scored_versions.append({
                "lyrics": v,
                "style_fidelity": _score_style_fidelity(v, chunks, language=language)
            })
        
        # Sort by fidelity, pick best
        scored_versions.sort(key=lambda x: x["style_fidelity"], reverse=True)
        
        # ── Hook Generator Logic ──────────────────────────────────────────
        if mode == "Hook Generator":
            print("[HOOK] Running hook generator scoring...")
            for v in scored_versions:
                v["hook_score"] = self._score_hook(v["lyrics"])
            
            # Re-sort by hook_score
            scored_versions.sort(key=lambda x: x.get("hook_score", 0), reverse=True)
            print(f"[HOOK] Best hook score: {scored_versions[0].get('hook_score')}")
            
            # HOOK QUALITY FLOOR: Regenerate if score < 0.6 (1-retry limit)
            if scored_versions[0].get('hook_score', 0) < 0.6 and not user_input.get("_is_retry"):
                print("[HOOK] Quality floor not met (score < 0.6). Retrying generation once...")
                retry_input = user_input.copy()
                retry_input["_is_retry"] = True
                return self.run(**retry_input)

        # Final Validation for chosen hook (Post-generation rules)
        if mode == "Hook Generator" and scored_versions:
            best_v = scored_versions[0]
            if self._validator:
                validated_lyrics = self._validator.validate_hook(best_v["lyrics"])
                if validated_lyrics != best_v["lyrics"]:
                    best_v["lyrics"] = validated_lyrics
                    # Update score for validated version
                    best_v["hook_score"] = self._score_hook(validated_lyrics)
            lyrics = best_v["lyrics"]
        if not scored_versions:
             if last_error: raise last_error
             raise RuntimeError("Generation failed: No versions produced.")

        best_v = scored_versions[0]
        lyrics = best_v["lyrics"]

        # ── Log ───────────────────────────────────────────────────────────
        log_generation(
            user_input=user_input,
            chunks=chunks,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output=lyrics,
            latency_ms=latency_ms,
            error=str(last_error) if last_error else None,
            retrieval_diagnostics=retrieval_diagnostics,
            prompt_version=PROMPT_VERSION,
        )

        return {
            "lyrics": lyrics,
            "versions": scored_versions,
            "artists": artists,
            "theme": theme,
            "structure": structure,
            "context": chunks,
            "latency_ms": latency_ms,
            "retrieval_fallback": retrieval_fallback,
            "retrieval_quality": rq,
            "retrieval_diagnostics": retrieval_diagnostics,
            "style_strength": style_strength,
            "prompt_version": PROMPT_VERSION,
        }
