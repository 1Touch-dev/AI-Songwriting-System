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
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from rag.retriever import Retriever
from rag.prompt_builder import build_prompt
from utils.config import (
    FALLBACK_TOP_K,
    GENERATION_MAX_TOKENS,
    GENERATION_MODEL,
    GENERATION_TEMPERATURE,
    MAX_RETRY_ATTEMPTS,
    MIN_CHUNKS_THRESHOLD,
    PROMPT_VERSION,
    STYLE_STRENGTH_DEFAULT,
    TOP_K,
)
from utils.logger import log_generation

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

    def run(
        self,
        artists: list[str],
        theme: str,
        structure: str,
        language: str = "English",
        top_k: int = TOP_K,
        temperature: float = GENERATION_TEMPERATURE,
        extra_instructions: str = "",
        style_strength: float = STYLE_STRENGTH_DEFAULT,
    ) -> dict:
        """
        Run the full pipeline and return a result dict.

        Returns
        -------
        dict:
            lyrics               str
            artists              list[str]
            theme                str
            structure            str
            context              list[dict]   retrieved chunks
            latency_ms           int
            retrieval_fallback   bool
            retrieval_quality    float        mean hybrid score 0-1
            retrieval_diagnostics dict        path/fallback/counts
            style_strength       float
            prompt_version       str
        """
        t_start = time.time()

        user_input = {
            "artists": artists,
            "theme": theme,
            "structure": structure,
            "language": language,
            "top_k": top_k,
            "temperature": temperature,
            "extra_instructions": extra_instructions,
            "style_strength": style_strength,
        }

        # ── Retrieval ─────────────────────────────────────────────────────
        query = f"{' '.join(artists)} {theme} {structure}"
        chunks = self.retriever.retrieve(query=query, artists=artists, top_k=top_k)

        retrieval_fallback = any(c.get("fallback") for c in chunks)

        # Last-resort: if too sparse after retriever's own fallback chain
        if len(chunks) < MIN_CHUNKS_THRESHOLD:
            chunks = self.retriever.retrieve(query=query, top_k=FALLBACK_TOP_K)
            retrieval_fallback = True

        # Compute retrieval quality (mean hybrid score)
        rq = self.retriever.retrieval_quality(chunks)

        # Retrieval diagnostics for logging / UI
        retrieval_diagnostics = {
            "path": chunks[0].get("retrieval_path", "unknown") if chunks else "none",
            "fallback": chunks[0].get("fallback") if chunks else None,
            "n_chunks": len(chunks),
            "quality": rq,
            "top_scores": [round(c.get("score", 0), 4) for c in chunks[:3]],
        }

        # ── Retry loop ────────────────────────────────────────────────────
        last_error: Optional[Exception] = None
        lyrics = ""
        system_prompt = ""
        user_prompt = ""

        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            attempt_extra = extra_instructions
            attempt_temp = temperature
            attempt_strength = style_strength

            if attempt == 2:
                attempt_extra = (
                    (extra_instructions + " Keep language simple and direct.")
                    if extra_instructions else "Keep language simple and direct."
                )
            elif attempt >= 3:
                attempt_temp = max(0.65, temperature - 0.15)
                attempt_strength = min(style_strength + 0.1, 1.0)
                attempt_extra = "Focus on emotional clarity and clean rhymes."

            system_prompt, user_prompt = build_prompt(
                artists=artists,
                theme=theme,
                structure=structure,
                retrieved_chunks=chunks,
                language=language,
                extra_instructions=attempt_extra,
                style_strength=attempt_strength,
                retrieval_quality=rq,
            )

            try:
                response = self._client.chat.completions.create(
                    model=GENERATION_MODEL,
                    temperature=attempt_temp,
                    max_tokens=GENERATION_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
                lyrics = response.choices[0].message.content.strip()
                last_error = None
                break

            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRY_ATTEMPTS:
                    time.sleep(2 ** attempt)

        latency_ms = int((time.time() - t_start) * 1000)

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

        if last_error and not lyrics:
            raise RuntimeError(
                f"Generation failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"
            )

        return {
            "lyrics": lyrics,
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
