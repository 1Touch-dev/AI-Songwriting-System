"""
services/producer_assistant.py — SonicFlow AI Producer Assistant

Analyses lyrics for musical quality and provides actionable producer feedback:
  - Hook strength scoring
  - Arrangement balance
  - Emotional arc analysis
  - Remix + genre flip suggestions
  - Replayability estimation

Public API:
    analyse_production(lyrics, theme, artists, genre) -> ProductionAnalysis
"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass, field
from typing import Optional

from services.cadence_analysis import extract_cadence


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class HookAnalysis:
    score: float              # 0-1
    strengths: list[str]
    weaknesses: list[str]
    suggested_rewrites: list[str]
    replayability: float      # 0-1

@dataclass
class ArrangementAnalysis:
    section_balance: dict[str, int]    # section_name → line count
    is_chorus_heavy: bool
    is_verse_heavy: bool
    energy_arc: str                    # "builds", "flat", "peaks-early", "peaks-late"
    suggestions: list[str]

@dataclass
class EmotionalArcAnalysis:
    detected_tone: str                 # e.g. "melancholic", "triumphant"
    emotional_journey: list[str]       # per-section emotional tone
    tension_points: list[str]          # sections with high tension
    resolution: str                    # how/whether the song resolves
    coherence_score: float             # 0-1 — how consistent the arc is

@dataclass
class RemixSuggestion:
    genre: str
    rationale: str
    bpm_shift: str
    key_suggestion: str

@dataclass
class ProductionAnalysis:
    hook: HookAnalysis
    arrangement: ArrangementAnalysis
    emotional_arc: EmotionalArcAnalysis
    remix_suggestions: list[RemixSuggestion]
    overall_score: float               # 0-1
    producer_notes: list[str]         # top-level actionable notes
    llm_analysis: Optional[dict] = None  # raw LLM analysis if requested


# ── Scoring utilities ─────────────────────────────────────────────────────────

_STRONG_HOOK_SIGNALS = [
    "tonight", "never", "always", "forever", "again", "right now",
    "love", "fire", "gold", "rise", "fall", "break", "run",
]

_WEAK_FILLER = [
    "i feel", "so strong", "i rise", "now i glow", "stronger than",
    "tears like", "in my heart", "from the start", "we stand together",
]


def _score_hook_heuristic(chorus_lines: list[str]) -> tuple[float, list[str], list[str]]:
    if not chorus_lines:
        return 0.0, [], ["No chorus found"]

    strengths = []
    weaknesses = []
    score = 0.5

    text = " ".join(chorus_lines).lower()
    word_counts = [len(l.split()) for l in chorus_lines]

    # Length check (4-8 words per line is ideal)
    avg_wc = sum(word_counts) / len(word_counts) if word_counts else 0
    if 4 <= avg_wc <= 8:
        score += 0.1
        strengths.append("Singable line length")
    else:
        score -= 0.1
        weaknesses.append(f"Line length {avg_wc:.0f} words — aim for 4-8")

    # Strong anchor words
    if any(w in text for w in _STRONG_HOOK_SIGNALS):
        score += 0.1
        strengths.append("Contains strong hook anchors")

    # Weak filler
    if any(f in text for f in _WEAK_FILLER):
        score -= 0.2
        weaknesses.append("Contains generic filler phrases")

    # Repetition (good for hooks)
    if len(chorus_lines) >= 2:
        first_words = chorus_lines[0].lower().split()[:3]
        second_words = chorus_lines[1].lower().split()[:3]
        if first_words == second_words:
            score += 0.15
            strengths.append("Strong hook repetition in L1/L2")
        else:
            weaknesses.append("Hook not repeated between L1 and L2")

    # Uniqueness (no identical triplets)
    if len(chorus_lines) >= 3 and all(l.lower() == chorus_lines[0].lower() for l in chorus_lines):
        score -= 0.3
        weaknesses.append("All lines identical — add variation in L3")

    return round(max(0.0, min(1.0, score)), 2), strengths, weaknesses


def _replayability(chorus_lines: list[str]) -> float:
    """Estimate how likely the listener is to replay the hook."""
    if not chorus_lines:
        return 0.0
    text = " ".join(chorus_lines).lower()
    score = 0.4
    # Short, punchy lines score higher
    if all(len(l.split()) <= 6 for l in chorus_lines):
        score += 0.2
    # Melodic anchors
    if any(w in text for w in ("oh", "yeah", "hey", "na", "la", "whoa")):
        score += 0.15
    # Avoids complex vocabulary
    complex_words = [w for w in re.findall(r"\b\w{8,}\b", text)]
    if len(complex_words) < 3:
        score += 0.1
    return round(min(1.0, score), 2)


# ── Arrangement analysis ──────────────────────────────────────────────────────

def _analyse_arrangement(lyrics: str) -> ArrangementAnalysis:
    sections = {}
    current = "unknown"
    current_lines = []

    for line in lyrics.splitlines():
        stripped = line.strip()
        if re.match(r"^\[.+\]", stripped):
            if current_lines:
                label = re.sub(r"\s+\d+$", "", current).strip().lower()  # normalise "verse 1" → "verse"
                sections[label] = sections.get(label, 0) + len(current_lines)
            current = stripped.strip("[]")
            current_lines = []
        elif stripped:
            current_lines.append(stripped)
    if current_lines:
        label = re.sub(r"\s+\d+$", "", current).strip().lower()
        sections[label] = sections.get(label, 0) + len(current_lines)

    total = sum(sections.values()) or 1
    chorus_pct = sections.get("chorus", 0) / total
    verse_pct  = sum(v for k, v in sections.items() if "verse" in k) / total

    is_chorus_heavy = chorus_pct > 0.45
    is_verse_heavy  = verse_pct > 0.6

    # Energy arc heuristic from section order
    energy_arc = "balanced"
    if chorus_pct > 0.5:
        energy_arc = "peaks-early"
    elif "bridge" in sections and sections.get("bridge", 0) > sections.get("chorus", 0):
        energy_arc = "peaks-late"
    elif verse_pct > 0.55:
        energy_arc = "builds"

    suggestions = []
    if is_chorus_heavy:
        suggestions.append("Too chorus-heavy — add a verse to develop the story")
    if is_verse_heavy:
        suggestions.append("Too verse-heavy — add more chorus repetitions for catchiness")
    if "bridge" not in sections:
        suggestions.append("No bridge detected — a bridge adds emotional contrast and replay value")

    return ArrangementAnalysis(
        section_balance=sections,
        is_chorus_heavy=is_chorus_heavy,
        is_verse_heavy=is_verse_heavy,
        energy_arc=energy_arc,
        suggestions=suggestions,
    )


# ── Emotional arc ─────────────────────────────────────────────────────────────

_TONE_SIGNALS = {
    "melancholic":  ["alone", "miss", "gone", "cry", "hurt", "lost", "cold", "empty"],
    "triumphant":   ["rise", "win", "top", "best", "gold", "throne", "conquer"],
    "romantic":     ["love", "heart", "kiss", "feel", "together", "forever", "close"],
    "aggressive":   ["fire", "smoke", "kill", "shoot", "run", "chase", "power"],
    "nostalgic":    ["used to", "remember", "back then", "years ago", "miss those"],
    "hopeful":      ["tomorrow", "new day", "light", "grow", "dream", "believe"],
}

def _detect_tone(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for tone, words in _TONE_SIGNALS.items():
        scores[tone] = sum(1 for w in words if w in text_lower)
    if not any(scores.values()):
        return "neutral"
    return max(scores, key=scores.get)


def _analyse_emotional_arc(lyrics: str) -> EmotionalArcAnalysis:
    sections_text: dict[str, str] = {}
    current = "intro"
    current_lines: list[str] = []

    for line in lyrics.splitlines():
        stripped = line.strip()
        if re.match(r"^\[.+\]", stripped):
            if current_lines:
                sections_text[current] = " ".join(current_lines)
            current = stripped.strip("[]").lower()
            current_lines = []
        elif stripped:
            current_lines.append(stripped)
    if current_lines:
        sections_text[current] = " ".join(current_lines)

    all_text = " ".join(sections_text.values())
    overall_tone = _detect_tone(all_text)

    journey = [f"{sec}: {_detect_tone(text)}" for sec, text in sections_text.items()]

    # Tension: sections with aggressive or melancholic tone
    tension_pts = [
        sec for sec, text in sections_text.items()
        if _detect_tone(text) in ("aggressive", "melancholic")
    ]

    # Resolution: last section tone
    last_tone = _detect_tone(list(sections_text.values())[-1]) if sections_text else "neutral"
    if last_tone in ("hopeful", "triumphant"):
        resolution = "resolves positively"
    elif last_tone in ("melancholic",):
        resolution = "ends in unresolved tension"
    else:
        resolution = "neutral resolution"

    # Coherence: how many sections share the dominant tone
    tone_counts = {}
    for sec, text in sections_text.items():
        t = _detect_tone(text)
        tone_counts[t] = tone_counts.get(t, 0) + 1
    dominant_pct = max(tone_counts.values()) / max(len(sections_text), 1) if tone_counts else 0.5
    coherence = round(min(1.0, dominant_pct * 1.2), 2)

    return EmotionalArcAnalysis(
        detected_tone=overall_tone,
        emotional_journey=journey,
        tension_points=tension_pts,
        resolution=resolution,
        coherence_score=coherence,
    )


# ── Remix suggestions ─────────────────────────────────────────────────────────

_TONE_TO_GENRES = {
    "melancholic":  [("Synthwave", "The dark nostalgia fits perfectly", "+10 BPM", "minor"),
                     ("Acoustic", "Strip it back for maximum emotional impact", "-20 BPM", "minor")],
    "triumphant":   [("EDM", "An EDM drop would amplify the triumph", "+30 BPM", "major"),
                     ("Afrobeat", "Afrobeat energy matches the uplifting vibe", "same BPM", "major")],
    "romantic":     [("House", "Deep house suits the intimate mood", "same BPM", "minor"),
                     ("K-Pop", "K-pop sheen would make this radio-ready", "+15 BPM", "major")],
    "aggressive":   [("Drill", "Drill production amplifies the aggression", "same BPM", "minor"),
                     ("Trap", "Trap 808s would hit harder here", "+5 BPM", "minor")],
    "nostalgic":    [("Synthwave", "Synthwave IS nostalgia", "-10 BPM", "major"),
                     ("Acoustic", "Acoustic strips nostalgia to its core", "-20 BPM", "major")],
    "hopeful":      [("Reggaeton", "Reggaeton bounce would energize the hope", "same BPM", "major"),
                     ("Afrobeat", "Afrobeat polyrhythms amplify the optimism", "+10 BPM", "major")],
}

def _build_remix_suggestions(tone: str) -> list[RemixSuggestion]:
    suggestions = _TONE_TO_GENRES.get(tone, [
        ("Drill", "Contrast with the source material", "+10 BPM", "minor"),
        ("EDM", "Amplify for festival energy", "+25 BPM", "major"),
    ])
    return [
        RemixSuggestion(genre=g, rationale=r, bpm_shift=b, key_suggestion=k)
        for g, r, b, k in suggestions
    ]


# ── Main entry point ──────────────────────────────────────────────────────────

def analyse_production(
    lyrics: str,
    theme: str = "",
    artists: list[str] = None,
    genre: str = "",
    openai_client=None,
    use_llm: bool = True,
) -> ProductionAnalysis:
    """
    Full production analysis of lyrics.
    Combines deterministic scoring with optional LLM deep analysis.
    """
    if artists is None:
        artists = []

    # Extract chorus lines
    chorus_match = re.search(r"\[Chorus[^\]]*\]\n(.*?)(?=\n\[|\Z)", lyrics + "\n\n[END]", re.DOTALL)
    chorus_lines: list[str] = []
    if chorus_match:
        chorus_lines = [l.strip() for l in chorus_match.group(1).strip().splitlines() if l.strip()]

    # Hook scoring
    hook_score, strengths, weaknesses = _score_hook_heuristic(chorus_lines)
    replay = _replayability(chorus_lines)

    # Suggested rewrites (simple heuristic)
    rewrites: list[str] = []
    if weaknesses:
        rewrites.append("Shorten lines to 4-6 words for maximum impact")
    if "No hook repetition" in str(weaknesses):
        rewrites.append("Repeat the first line of the chorus as line 2 (L1 = L2 hook pattern)")

    hook = HookAnalysis(
        score=hook_score,
        strengths=strengths,
        weaknesses=weaknesses,
        suggested_rewrites=rewrites,
        replayability=replay,
    )

    # Arrangement
    arrangement = _analyse_arrangement(lyrics)

    # Emotional arc
    emotional = _analyse_emotional_arc(lyrics)

    # Remix suggestions based on detected tone
    remix_sug = _build_remix_suggestions(emotional.detected_tone)

    # Overall score
    overall = round((hook_score * 0.4 + emotional.coherence_score * 0.3 + replay * 0.3), 2)

    # Producer notes
    notes: list[str] = []
    if hook_score < 0.5:
        notes.append(f"Hook needs work (score {hook_score:.0%}) — {weaknesses[0] if weaknesses else 'strengthen the chorus'}")
    if arrangement.suggestions:
        notes.append(arrangement.suggestions[0])
    notes.append(f"Detected tone: {emotional.detected_tone} — try a {remix_sug[0].genre} remix for contrast")
    if replay < 0.5:
        notes.append("Low replayability — shorten and punch up the chorus hook")

    # Optional LLM deep analysis
    llm_data = None
    if use_llm and openai_client and lyrics:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=600,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "system",
                    "content": (
                        "You are an elite music producer. Analyse these lyrics and return JSON:\n"
                        '{"hook_quality": "1-10 score with 1 sentence why",\n'
                        '"melodic_tension": "describe the melodic tension arc",\n'
                        '"arrangement_notes": ["note1", "note2"],\n'
                        '"strongest_line": "quote the single strongest lyric line",\n'
                        '"weakest_line": "quote the single weakest line",\n'
                        '"commercial_potential": "1-10 with brief reason"}'
                    ),
                }, {
                    "role": "user",
                    "content": f"Theme: {theme}\nArtists: {', '.join(artists)}\n\nLyrics:\n{lyrics[:2000]}",
                }],
            )
            llm_data = json.loads(resp.choices[0].message.content.strip())
        except Exception as exc:
            print(f"[PRODUCER] LLM analysis error: {exc}", flush=True)

    return ProductionAnalysis(
        hook=hook,
        arrangement=arrangement,
        emotional_arc=emotional,
        remix_suggestions=remix_sug,
        overall_score=overall,
        producer_notes=notes,
        llm_analysis=llm_data,
    )
