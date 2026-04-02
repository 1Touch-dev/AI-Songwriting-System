import json
import os
import sys
import time
from pathlib import Path

import importlib.util

# Add root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.pipeline import SongwritingPipeline, STRUCTURES
from utils.config import EVAL_DETAILED_RESULTS_PATH

# Load the evaluation module dynamically because it starts with a number
spec = importlib.util.spec_from_file_location("evaluate_04", "scripts/04_evaluate.py")
eval_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_mod)

retrieval_metrics = eval_mod.retrieval_metrics
structure_accuracy = eval_mod.structure_accuracy
style_similarity = eval_mod.style_similarity
repetition_score = eval_mod.repetition_score
llm_judge = eval_mod.llm_judge
overall_score = eval_mod.overall_score

# ── Extension of Test Cases ────────────────────────────────────────────────
QA_TEST_BATTERY = [
    # 1. Single Artist
    {"id": "QA_01", "artists": ["Drake"], "theme": "Regret & Heartbreak", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.8},
    {"id": "QA_02", "artists": ["Kendrick Lamar"], "theme": "Social Commentary", "structure": STRUCTURES["Verse Heavy (V-V-C-V-C)"], "strength": 0.9},
    {"id": "QA_03", "artists": ["SZA"], "theme": "Self-Doubt in Relationships", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.8},
    {"id": "QA_04", "artists": ["The Weeknd"], "theme": "Late Night Loneliness", "structure": STRUCTURES["Extended (Intro-V-PC-C-V-PC-C-B-C-Outro)"], "strength": 0.8},
    {"id": "QA_05", "artists": ["Taylor Swift"], "theme": "Nostalgic Storytelling", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.7},

    # 2. Multi-Artist Mix
    {"id": "QA_06", "artists": ["Drake", "SZA"], "theme": "Toxic Texting", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.8},
    {"id": "QA_07", "artists": ["Kendrick Lamar", "J. Cole"], "theme": "The Burden of Success", "structure": STRUCTURES["Verse Heavy (V-V-C-V-C)"], "strength": 0.9},
    {"id": "QA_08", "artists": ["Travis Scott", "The Weeknd"], "theme": "Cinematic Excess", "structure": STRUCTURES["Hook Heavy (V-H-V-H-H)"], "strength": 0.8},
    {"id": "QA_09", "artists": ["Taylor Swift", "Billie Eilish"], "theme": "Growing Up Too Fast", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.7},

    # 3. Thematic & Genre Variety
    {"id": "QA_10", "artists": ["Bad Bunny"], "theme": "Club Confidence", "structure": STRUCTURES["Simple (V-C-V-C)"], "strength": 0.8, "language": "Spanish"},
    {"id": "QA_11", "artists": ["Nicki Minaj"], "theme": "Competitive Fire", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.8},
    {"id": "QA_12", "artists": ["Frank Ocean"], "theme": "Sparse Memory", "structure": STRUCTURES["Simple (V-C-V-C)"], "strength": 0.9},
    {"id": "QA_13", "artists": ["Morgan Wallen"], "theme": "Small Town Pride", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.7},

    # 4. Edge Cases
    {"id": "QA_14", "artists": ["Drake"], "theme": "Life", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 0.8},
    {"id": "QA_15", "artists": ["Billie Eilish"], "theme": "Euphoric Sadness", "structure": STRUCTURES["Simple (V-C-V-C)"], "strength": 0.8},
    {"id": "QA_16", "artists": ["Kendrick Lamar"], "theme": "Social Justice", "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "strength": 1.0, 
     "extra": "Use complex internal rhymes and double entendres."},
]

def run_qa_suite():
    pipeline = SongwritingPipeline()
    results = []
    
    print(f"🚀 Starting Expert QA Suite: {len(QA_TEST_BATTERY)} cases\n")
    
    for tc in QA_TEST_BATTERY:
        print(f"Testing {tc['id']}: {' + '.join(tc['artists'])} - {tc['theme']}...", end=" ", flush=True)
        try:
            res = pipeline.run(
                artists=tc["artists"],
                theme=tc["theme"],
                structure=tc["structure"],
                style_strength=tc.get("strength", 0.7),
                language=tc.get("language", "English"),
                extra_instructions=tc.get("extra", "")
            )
            
            output = res["lyrics"]
            chunks = res["context"]
            
            ret = retrieval_metrics(chunks, res)
            gen = {
                "structure_accuracy": structure_accuracy(output, tc["structure"]),
                "style_similarity": style_similarity(output, chunks),
                "repetition_score": repetition_score(output)
            }
            judge = llm_judge(tc["artists"], tc["theme"], tc["structure"], chunks, output)
            score = overall_score(ret, gen, judge)
            
            results.append({
                "input": tc,
                "output": output,
                "metrics": {
                    "retrieval": ret,
                    "generation": gen,
                    "judge": judge,
                    "overall": score
                },
                "latency_ms": res.get("latency_ms", 0),
                "status": "ok"
            })
            print(f"Score: {score:.2f} ✓")
            
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({"id": tc["id"], "status": "error", "error": str(e)})
            
        time.sleep(1) # Rate limit safety

    # Save results
    output_path = Path("evaluation/qa_detailed_results.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ QA Suite Complete. Results saved to {output_path}")

if __name__ == "__main__":
    run_qa_suite()
