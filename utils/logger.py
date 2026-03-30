"""
Generation Logger  (v2 — extended fields)
==========================================
Extended fields added in v2:
  - retrieval_diagnostics  (path, fallback, quality, top_scores)
  - prompt_version         (for reproducibility tracking)
  - eval_scores            (optional, written by the evaluation script)

Usage:
    from utils.logger import log_generation
    log_generation(
        user_input={...},
        chunks=[...],
        system_prompt="...",
        user_prompt="...",
        output="...",
        latency_ms=1234,
        retrieval_diagnostics={...},
        prompt_version="v3",
    )
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.config import GEN_LOG_PATH


def log_generation(
    user_input: dict,
    chunks: list[dict],
    system_prompt: str,
    user_prompt: str,
    output: str,
    latency_ms: int = 0,
    error: Optional[str] = None,
    retrieval_diagnostics: Optional[dict] = None,
    prompt_version: str = "unknown",
    eval_scores: Optional[dict] = None,
) -> None:
    """
    Append one generation record to GEN_LOG_PATH (JSONL).
    Never raises — logging failures are swallowed so they cannot crash
    the main pipeline.
    """
    try:
        chunk_summary = [
            {
                "artist":        c.get("artist"),
                "song":          c.get("song"),
                "section":       c.get("section"),
                "score":         round(c.get("score",         0.0), 4),
                "vector_score":  round(c.get("vector_score",  0.0), 4),
                "keyword_score": round(c.get("keyword_score", 0.0), 4),
                "retrieval_path": c.get("retrieval_path"),
                "fallback":      c.get("fallback"),
            }
            for c in chunks
        ]

        record = {
            "timestamp":             datetime.now(timezone.utc).isoformat(),
            "prompt_version":        prompt_version,
            "latency_ms":            latency_ms,
            "user_input":            user_input,
            "retrieval_diagnostics": retrieval_diagnostics or {},
            "retrieved_chunks":      chunk_summary,
            "system_prompt":         system_prompt,
            "user_prompt":           user_prompt,
            "output":                output,
            "error":                 error,
            "eval_scores":           eval_scores,
        }

        GEN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GEN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    except Exception:
        pass  # logging must never break the pipeline
