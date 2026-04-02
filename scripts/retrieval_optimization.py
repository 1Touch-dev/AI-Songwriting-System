import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from rag.retriever import Retriever

_oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Test Suite ─────────────────────────────────────────────────────────────

TEST_CASES = [
    {"id": "tc01", "artists": ["Drake"], "theme": "Montreal in the fall, crisp air, luxury, heartbreak"},
    {"id": "tc02", "artists": ["Kendrick Lamar"], "theme": "Life in the city, struggle, wisdom, spirituality"},
    {"id": "tc03", "artists": ["SZA"], "theme": "Moving on from toxic love, self-worth, vulnerability"},
    {"id": "tc04", "artists": ["Drake", "SZA"], "theme": "Heartbreak, missed calls, high-end toxicity"},
    {"id": "tc05", "artists": ["Kendrick Lamar", "J. Cole"], "theme": "Street wisdom, legacy, the weight of the crown"},
    {"id": "tc06", "artists": ["Taylor Swift"], "theme": "Small town nostalgia, summer rain, letters never sent"},
    {"id": "tc07", "artists": ["Morgan Wallen"], "theme": "Small town pride, whiskey, dirt roads"},
    {"id": "tc08", "artists": ["The Weeknd"], "theme": "Dark pop, late-night obsession, hedonism"},
    {"id": "tc09", "artists": ["Travis Scott"], "theme": "Abstract imagery, fame, dark vibes, energy"},
    {"id": "tc10", "artists": ["21 Savage"], "theme": "Survival, the block, loyalty, cold reality"},
]

# ── LLM-as-judge (Faithfulness/Grounding) ──────────────────────────────────

JUDGE_SYSTEM = """
You are an expert music critic. 
Your task is to evaluate how well a set of retrieved lyric chunks "ground" a specific artist's style for a given theme.
Rate the "Faithfulness" of the retrieved context to the requested artist(s) on a scale 1-10.
10 = Perfectly captures the artist's unique voice, slang, and thematic essence.
1 = Feels generic or unrelated to the specific artist.
Respond ONLY with a JSON object: {"faithfulness": score, "reason": "short explanation"}
"""

def judge_grounding(artists: list[str], theme: str, chunks: list[dict]) -> dict:
    artist_str = " + ".join(artists)
    context_text = "\n---\n".join([f"[{c['song']}] {c['text'][:300]}" for c in chunks])
    
    prompt = f"""
Artist(s): {artist_str}
Theme: {theme}

Retrieved Context Chunks:
{context_text}

How well does this context ground the target artist(s)' style for this theme?
"""
    try:
        resp = _oai.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {"faithfulness": 5, "reason": f"Error: {e}"}

# ── Optimization Loop ──────────────────────────────────────────────────────

def run_experiment(config: dict) -> dict:
    print(f"  Testing Config: {config} ...")
    retriever = Retriever(
        top_k=config.get("top_k", 8),
        bm25_weight=config.get("bm25_weight", 0.3),
        vector_weight=1.0 - config.get("bm25_weight", 0.3),
        rerank_enabled=config.get("rerank_enabled", False),
        rerank_candidate_n=config.get("rerank_candidate_n", 12)
    )
    
    case_results = []
    latencies = []
    
    for tc in TEST_CASES:
        start_time = time.time()
        chunks = retriever.retrieve(query=tc["theme"], artists=tc["artists"])
        latency = (time.time() - start_time) * 1000
        latencies.append(latency)
        
        quality = retriever.retrieval_quality(chunks)
        judge = judge_grounding(tc["artists"], tc["theme"], chunks[:5]) # Judge top 5 primarily
        
        case_results.append({
            "id": tc["id"],
            "relevance": quality,
            "faithfulness": judge["faithfulness"] / 10.0,
            "latency": latency
        })
    
    avg_relevance = np.mean([r["relevance"] for r in case_results])
    avg_faithfulness = np.mean([r["faithfulness"] for r in case_results])
    avg_latency = np.mean(latencies)
    
    # Combined optimization score (Quality * 0.7 + Faithfulness * 0.3)
    # Actually, the user wants retrieval_quality > 0.65.
    score = (avg_relevance * 0.6) + (avg_faithfulness * 0.4)
    
    return {
        "config": config,
        "avg_relevance": round(float(avg_relevance), 4),
        "avg_faithfulness": round(float(avg_faithfulness), 4),
        "avg_latency": round(float(avg_latency), 2),
        "optim_score": round(float(score), 4),
    }

if __name__ == "__main__":
    configs = [
        # Baseline
        {"top_k": 8, "bm25_weight": 0.3, "rerank_enabled": False},
        
        # Grid Search Coarse
        {"top_k": 12, "bm25_weight": 0.3, "rerank_enabled": False},
        {"top_k": 16, "bm25_weight": 0.3, "rerank_enabled": False},
        
        {"top_k": 12, "bm25_weight": 0.4, "rerank_enabled": False},
        {"top_k": 12, "bm25_weight": 0.5, "rerank_enabled": False},
        
        # Reranking Experiments
        {"top_k": 8,  "bm25_weight": 0.3, "rerank_enabled": True, "rerank_candidate_n": 15},
        {"top_k": 10, "bm25_weight": 0.3, "rerank_enabled": True, "rerank_candidate_n": 20},
        {"top_k": 10, "bm25_weight": 0.4, "rerank_enabled": True, "rerank_candidate_n": 30},
    ]
    
    all_results = []
    print(f"Starting Optimization Loop with {len(configs)} configurations...")
    
    for cfg in configs:
        res = run_experiment(cfg)
        all_results.append(res)
        print(f"    => Score: {res['optim_score']} (Rel={res['avg_relevance']}, Faith={res['avg_faithfulness']}, Lat={res['avg_latency']}ms)")
        time.sleep(1)
        
    all_results.sort(key=lambda x: x["optim_score"], reverse=True)
    
    output_path = Path("evaluation/retrieval_optimization_results.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nOptimization Finished. Best Configuration:")
    print(json.dumps(all_results[0], indent=2))
    print(f"\nResults saved to {output_path}")
