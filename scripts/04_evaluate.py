"""
Step 6: Advanced Evaluation  (v2 — LLM-as-judge + retrieval metrics)
=====================================================================
Evaluation now covers BOTH retrieval and generation separately so failures
can be precisely diagnosed.

Retrieval metrics (heuristic, no LLM cost):
  context_relevance   — mean hybrid score of retrieved chunks (proxy for
                        how well the retrieval matched the query)
  context_diversity   — fraction of unique artists among retrieved chunks;
                        low = echo-chamber retrieval, high = varied examples
  fallback_rate       — whether genre/corpus fallback was used

Generation metrics (heuristic, cheap):
  structure_accuracy  — fraction of expected section labels present
  style_similarity    — Jaccard word-overlap with retrieved chunks
  repetition_score    — chorus/hook line consistency

LLM-as-judge metrics (one GPT call per test case, costs ~$0.01 each):
  faithfulness        — is the output grounded in the retrieved style?  (1-10)
  coherence           — does the song flow logically and emotionally?    (1-10)
  structure_adherence — does the output strictly follow the template?    (1-10)
  overall_quality     — holistic quality judgment                        (1-10)

Output schema per test case:
  {
    id, artists, theme, structure, language,
    retrieval_score: {context_relevance, context_diversity, fallback_used},
    generation_score: {structure_accuracy, style_similarity, repetition_score},
    llm_judge_score: {faithfulness, coherence, structure_adherence, overall_quality},
    overall_score: float  (0-1, weighted average of all dimensions),
    output_preview: str,
    latency_ms: int,
    status: "ok" | "error"
  }

Saved to:
  evaluation/results.json          (heuristic metrics — backwards-compatible)
  evaluation/detailed_results.json (full schema including LLM-judge)

Run: python scripts/04_evaluate.py [--no-llm-judge]
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI

from rag.pipeline import SongwritingPipeline, STRUCTURES
from utils.config import (
    EVAL_DETAILED_RESULTS_PATH,
    EVAL_JUDGE_MODEL,
    EVAL_RESULTS_PATH,
)

_oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Test set ──────────────────────────────────────────────────────────────

TEST_CASES: list[dict] = [
    {"id": "tc01", "artists": ["Drake"],
     "theme": "emotional, hook-heavy, success and loneliness",
     "structure": STRUCTURES["Hook Heavy (V-H-V-H-H)"], "language": "English"},
    {"id": "tc02", "artists": ["Kendrick Lamar"],
     "theme": "social commentary, street life, survival",
     "structure": STRUCTURES["Verse Heavy (V-V-C-V-C)"], "language": "English"},
    {"id": "tc03", "artists": ["J. Cole"],
     "theme": "self-reflection, growth, humble beginnings",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
    {"id": "tc04", "artists": ["Travis Scott"],
     "theme": "dark vibes, fame, abstract imagery",
     "structure": STRUCTURES["Simple (V-C-V-C)"], "language": "English"},
    {"id": "tc05", "artists": ["Drake", "SZA"],
     "theme": "heartbreak and moving on, R&B-rap fusion",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
    {"id": "tc06", "artists": ["Kendrick Lamar", "J. Cole"],
     "theme": "introspective rap, real vs fake, loyalty",
     "structure": STRUCTURES["Verse Heavy (V-V-C-V-C)"], "language": "English"},
    {"id": "tc07", "artists": ["The Weeknd", "Doja Cat"],
     "theme": "dark pop, late-night obsession, desire",
     "structure": STRUCTURES["Extended (Intro-V-PC-C-V-PC-C-B-C-Outro)"], "language": "English"},
    {"id": "tc08", "artists": ["Taylor Swift"],
     "theme": "nostalgia, lost love, small-town memories",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
    {"id": "tc09", "artists": ["Billie Eilish"],
     "theme": "anxiety, isolation, growing up too fast",
     "structure": STRUCTURES["Simple (V-C-V-C)"], "language": "English"},
    {"id": "tc10", "artists": ["Ariana Grande"],
     "theme": "empowerment, self-love, moving on from toxic relationship",
     "structure": STRUCTURES["Hook Heavy (V-H-V-H-H)"], "language": "English"},
    {"id": "tc11", "artists": ["Frank Ocean"],
     "theme": "unrequited love, memory, coming of age",
     "structure": STRUCTURES["Verse Heavy (V-V-C-V-C)"], "language": "English"},
    {"id": "tc12", "artists": ["SZA"],
     "theme": "vulnerability, self-worth, complicated love",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
    {"id": "tc13", "artists": ["The Weeknd"],
     "theme": "dark romance, excess, regret",
     "structure": STRUCTURES["Extended (Intro-V-PC-C-V-PC-C-B-C-Outro)"], "language": "English"},
    {"id": "tc14", "artists": ["Bad Bunny"],
     "theme": "party, heartbreak, street life",
     "structure": STRUCTURES["Simple (V-C-V-C)"], "language": "Spanish"},
    {"id": "tc15", "artists": ["Imagine Dragons"],
     "theme": "personal demons, fighting back, resilience",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
    {"id": "tc16", "artists": ["Coldplay"],
     "theme": "hope, loss, finding light in darkness",
     "structure": STRUCTURES["Simple (V-C-V-C)"], "language": "English"},
    {"id": "tc17", "artists": ["Drake", "Future", "Travis Scott"],
     "theme": "trap vibes, money, ambition",
     "structure": STRUCTURES["Hook Heavy (V-H-V-H-H)"], "language": "English"},
    {"id": "tc18", "artists": ["Morgan Wallen"],
     "theme": "small town, whiskey, summer nights, heartbreak",
     "structure": STRUCTURES["Standard (V-C-V-C-B-C)"], "language": "English"},
]

# ── Retrieval metrics ─────────────────────────────────────────────────────

def retrieval_metrics(chunks: list[dict], result: dict) -> dict:
    """
    context_relevance  — mean hybrid score of retrieved chunks (0-1)
    context_diversity  — fraction of unique artists in retrieved chunks (0-1)
    fallback_used      — bool
    retrieval_path     — str
    """
    if not chunks:
        return {
            "context_relevance": 0.0,
            "context_diversity": 0.0,
            "fallback_used": True,
            "retrieval_path": "none",
        }

    relevance = round(
        sum(c.get("score", 0.0) for c in chunks) / len(chunks), 3
    )
    unique_artists = len({c.get("artist", "") for c in chunks})
    diversity = round(unique_artists / len(chunks), 3)
    path = result.get("retrieval_diagnostics", {}).get("path", "unknown")

    return {
        "context_relevance": relevance,
        "context_diversity": diversity,
        "fallback_used": result.get("retrieval_fallback", False),
        "retrieval_path": path,
    }


# ── Heuristic generation metrics ──────────────────────────────────────────

def _extract_labels(text: str) -> list[str]:
    return [m.lower() for m in re.findall(r"\[([^\]]+)\]", text)]


def structure_accuracy(output: str, structure: str) -> float:
    expected = [
        re.sub(r"\s*\d+$", "", p).strip().lower()
        for p in re.split(r"[→,\n]+", structure) if p.strip()
    ]
    found = _extract_labels(output)
    if not expected:
        return 0.0
    hits = sum(1 for e in set(expected) if any(e in f for f in found))
    return round(hits / len(set(expected)), 3)


def style_similarity(output: str, chunks: list[dict]) -> float:
    _SW = {
        "the","a","an","and","or","but","in","on","at","to","for","of",
        "with","is","was","are","be","been","i","you","he","she","we",
        "they","it","that","this","my","your","me","him","her","us",
        "them","do","did","have","had","not","no","so","as","if","all",
        "just","can",
    }
    def tok(t: str) -> set[str]:
        return {w for w in re.findall(r"[a-z']+", t.lower())
                if w not in _SW and len(w) > 2}
    ow = tok(output)
    rw = tok(" ".join(c.get("text","") for c in chunks))
    if not ow or not rw:
        return 0.0
    return round(len(ow & rw) / len(ow | rw), 3)


def repetition_score(output: str) -> float:
    secs: dict[str, list[str]] = {}
    cur_label: str | None = None
    cur_lines: list[str] = []

    for line in output.split("\n"):
        m = re.match(r"\[([^\]]+)\]", line.strip())
        if m:
            if cur_label:
                k = re.sub(r"\s*\d+$", "", cur_label).lower()
                secs.setdefault(k, []).append("\n".join(cur_lines).strip())
            cur_label = m.group(1)
            cur_lines = []
        elif cur_label:
            cur_lines.append(line)
    if cur_label:
        k = re.sub(r"\s*\d+$", "", cur_label).lower()
        secs.setdefault(k, []).append("\n".join(cur_lines).strip())

    repeats = {k: v for k, v in secs.items()
               if k in ("chorus","hook","refrain") and len(v) >= 2}
    if not repeats:
        return 0.0

    scores: list[float] = []
    for blocks in repeats.values():
        for i in range(len(blocks)):
            for j in range(i+1, len(blocks)):
                a = {l.strip().lower() for l in blocks[i].split("\n") if l.strip()}
                b = {l.strip().lower() for l in blocks[j].split("\n") if l.strip()}
                if a and b:
                    scores.append(len(a & b) / max(len(a), len(b)))
    return round(sum(scores)/len(scores), 3) if scores else 0.0


# ── LLM-as-judge ─────────────────────────────────────────────────────────

_JUDGE_SYSTEM = """\
You are an expert music critic and lyric analyst.
Evaluate the generated song lyrics on four dimensions (each 1-10):
  faithfulness      — do the lyrics genuinely reflect the artist's known style and vocabulary?
  coherence         — does the song flow logically with consistent emotion and narrative?
  structure_adherence — are ALL requested sections present and correctly labelled?
  overall_quality   — holistic assessment of artistic merit and craft

Respond ONLY with valid JSON. Example:
{"faithfulness": 8, "coherence": 7, "structure_adherence": 9, "overall_quality": 8}
"""

def llm_judge(
    artists: list[str],
    theme: str,
    structure: str,
    retrieved_chunks: list[dict],
    output: str,
) -> dict:
    """Call OpenAI to score the generated lyrics on 4 dimensions."""
    artist_str = " + ".join(artists)
    context_sample = "\n---\n".join(
        c.get("text","")[:200] for c in retrieved_chunks[:3]
    )
    user_msg = f"""Artist(s): {artist_str}
Theme: {theme}
Requested structure: {structure}

Retrieved style examples (first 3):
{context_sample}

Generated lyrics:
{output[:1500]}

Score the generated lyrics on the four dimensions."""

    for attempt in range(3):
        try:
            resp = _oai.chat.completions.create(
                model=EVAL_JUDGE_MODEL,
                temperature=0,
                max_tokens=80,
                messages=[
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"```[a-z]*", "", raw).strip("`").strip()
            scores = json.loads(raw)
            return {
                "faithfulness":        round(int(scores.get("faithfulness",       5)) / 10, 2),
                "coherence":           round(int(scores.get("coherence",           5)) / 10, 2),
                "structure_adherence": round(int(scores.get("structure_adherence", 5)) / 10, 2),
                "overall_quality":     round(int(scores.get("overall_quality",     5)) / 10, 2),
            }
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    # Fallback: neutral scores
    return {"faithfulness": 0.5, "coherence": 0.5,
            "structure_adherence": 0.5, "overall_quality": 0.5}


# ── Overall score ─────────────────────────────────────────────────────────

def overall_score(
    retrieval: dict,
    generation: dict,
    judge: dict,
) -> float:
    """
    Weighted average across all metric dimensions.
    Weights (sum to 1.0):
      context_relevance     0.10
      context_diversity     0.05
      structure_accuracy    0.15
      style_similarity      0.10
      repetition_score      0.10
      faithfulness          0.15
      coherence             0.15
      structure_adherence   0.10
      overall_quality       0.10
    """
    s = (
        0.10 * retrieval.get("context_relevance", 0)
      + 0.05 * retrieval.get("context_diversity",  0)
      + 0.15 * generation.get("structure_accuracy", 0)
      + 0.10 * generation.get("style_similarity",  0)
      + 0.10 * generation.get("repetition_score",  0)
      + 0.15 * judge.get("faithfulness",        0)
      + 0.15 * judge.get("coherence",           0)
      + 0.10 * judge.get("structure_adherence", 0)
      + 0.10 * judge.get("overall_quality",     0)
    )
    return round(s, 3)


# ── Runner ────────────────────────────────────────────────────────────────

def run_evaluation(
    test_cases: list[dict] | None = None,
    use_llm_judge: bool = True,
) -> dict:
    if test_cases is None:
        test_cases = TEST_CASES

    pipeline = SongwritingPipeline()
    detailed: list[dict] = []
    simple: list[dict] = []

    # Running totals for aggregate
    agg: dict[str, float] = {
        "context_relevance": 0.0, "context_diversity": 0.0,
        "structure_accuracy": 0.0, "style_similarity": 0.0, "repetition_score": 0.0,
        "faithfulness": 0.0, "coherence": 0.0,
        "structure_adherence": 0.0, "overall_quality": 0.0, "overall_score": 0.0,
    }
    ok_count = 0

    print(f"Running evaluation on {len(test_cases)} cases  "
          f"(LLM judge: {'on' if use_llm_judge else 'off'}) …\n")

    for tc in test_cases:
        tc_id = tc["id"]
        artist_str = " + ".join(tc["artists"])
        print(f"  [{tc_id}] {artist_str} | {tc['theme'][:45]} …", end=" ", flush=True)

        try:
            result = pipeline.run(
                artists=tc["artists"],
                theme=tc["theme"],
                structure=tc["structure"],
                language=tc.get("language", "English"),
            )
            output = result["lyrics"]
            chunks = result["context"]

            # ── Metrics ───────────────────────────────────────────────────
            ret  = retrieval_metrics(chunks, result)
            gen  = {
                "structure_accuracy": structure_accuracy(output, tc["structure"]),
                "style_similarity":   style_similarity(output, chunks),
                "repetition_score":   repetition_score(output),
            }
            judge = (
                llm_judge(tc["artists"], tc["theme"], tc["structure"], chunks, output)
                if use_llm_judge else
                {"faithfulness": None, "coherence": None,
                 "structure_adherence": None, "overall_quality": None}
            )

            os_ = overall_score(ret, gen, judge) if use_llm_judge else None

            print(
                f"CR={ret['context_relevance']:.2f}  "
                f"SA={gen['structure_accuracy']:.2f}  "
                f"SS={gen['style_similarity']:.2f}  "
                f"RS={gen['repetition_score']:.2f}  "
                + (f"LLM={judge['overall_quality']:.2f}  OS={os_:.2f}" if use_llm_judge else "")
                + "  ✓"
            )

            if use_llm_judge and os_ is not None:
                agg["context_relevance"]    += ret["context_relevance"]
                agg["context_diversity"]    += ret["context_diversity"]
                agg["structure_accuracy"]   += gen["structure_accuracy"]
                agg["style_similarity"]     += gen["style_similarity"]
                agg["repetition_score"]     += gen["repetition_score"]
                agg["faithfulness"]         += judge["faithfulness"]
                agg["coherence"]            += judge["coherence"]
                agg["structure_adherence"]  += judge["structure_adherence"]
                agg["overall_quality"]      += judge["overall_quality"]
                agg["overall_score"]        += os_
                ok_count += 1

            rec = {
                "id": tc_id,
                "artists": tc["artists"],
                "theme": tc["theme"],
                "structure": tc["structure"],
                "language": tc.get("language", "English"),
                "retrieval_score":   ret,
                "generation_score":  gen,
                "llm_judge_score":   judge,
                "overall_score":     os_,
                "output_preview":    output[:400],
                "latency_ms":        result.get("latency_ms", 0),
                "retrieval_quality": result.get("retrieval_quality", 0),
                "prompt_version":    result.get("prompt_version", "unknown"),
                "status":            "ok",
            }
            detailed.append(rec)
            # Backwards-compat simplified record
            simple.append({
                "id": tc_id, "artists": tc["artists"],
                "theme": tc["theme"], "structure": tc["structure"],
                "metrics": gen,
                "retrieval_fallback": result.get("retrieval_fallback", False),
                "chunks_retrieved": len(chunks),
                "latency_ms": result.get("latency_ms", 0),
                "status": "ok",
            })

        except Exception as exc:
            print(f"ERROR: {exc}")
            detailed.append({
                "id": tc_id, "artists": tc["artists"],
                "theme": tc["theme"], "structure": tc["structure"],
                "retrieval_score": {}, "generation_score": {},
                "llm_judge_score": {}, "overall_score": None,
                "status": "error", "error": str(exc),
            })
            simple.append({
                "id": tc_id, "artists": tc["artists"],
                "metrics": {}, "status": "error", "error": str(exc),
            })

        time.sleep(0.8)

    # ── Aggregate ─────────────────────────────────────────────────────────
    n = ok_count or 1
    agg_out = {k: round(v / n, 3) for k, v in agg.items()}

    detailed_doc = {
        "summary": {
            "total_cases": len(test_cases),
            "evaluated":   ok_count,
            "llm_judge":   use_llm_judge,
            "aggregate":   agg_out,
            "thresholds": {
                "context_relevance":   ">= 0.40",
                "context_diversity":   ">= 0.30",
                "structure_accuracy":  ">= 0.80",
                "style_similarity":    ">= 0.05",
                "repetition_score":    ">= 0.50",
                "faithfulness":        ">= 0.65",
                "coherence":           ">= 0.65",
                "structure_adherence": ">= 0.75",
                "overall_quality":     ">= 0.65",
                "overall_score":       ">= 0.55",
            },
        },
        "results": detailed,
    }

    simple_doc = {
        "summary": {
            "total_cases": len(test_cases),
            "aggregate_metrics": {
                k: agg_out[k]
                for k in ("structure_accuracy","style_similarity","repetition_score")
            },
        },
        "results": simple,
    }

    EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(simple_doc, f, indent=2, ensure_ascii=False)

    with open(EVAL_DETAILED_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(detailed_doc, f, indent=2, ensure_ascii=False)

    print(f"\n── Aggregate ───────────────────────────────────────")
    for k, v in agg_out.items():
        print(f"  {k:<28} {v:.3f}")
    print(f"\nSaved → {EVAL_RESULTS_PATH}")
    print(f"Saved → {EVAL_DETAILED_RESULTS_PATH}")

    return detailed_doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-llm-judge", action="store_true",
        help="Skip LLM-as-judge scoring (faster, free)",
    )
    args = parser.parse_args()
    run_evaluation(use_llm_judge=not args.no_llm_judge)
