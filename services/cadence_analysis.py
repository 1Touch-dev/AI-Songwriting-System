"""
services/cadence_analysis.py — Flow Transfer & Cadence Intelligence

Extracts cadence, rhyme density, phrasing, and syllabic patterns from existing
lyrics to guide new verse generation. This is what makes remix verses feel
musically compatible with a locked chorus.

Public API:
    extract_cadence(lyrics) -> CadenceProfile
    build_flow_constraints(profile) -> str    # LLM-injectable constraint block
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class RhymeAnalysis:
    scheme: str                    # e.g. "AABB", "ABAB", "AAAA", "free"
    end_sounds: list[str]          # phonetic end-sounds per line
    rhyme_density: float           # 0-1: proportion of lines that rhyme with another
    internal_rhyme_density: float  # 0-1: internal rhymes per line

@dataclass
class PhraseMetrics:
    avg_words_per_line: float
    std_words_per_line: float
    avg_syllables_per_line: float
    line_length_pattern: str       # "short" | "medium" | "long" | "variable"
    breath_points: list[int]       # line indices with likely breath pauses (empty lines)

@dataclass
class FlowPattern:
    density: str                   # "dense" | "medium" | "sparse"
    stress_style: str              # "on-beat" | "syncopated" | "free-verse"
    phrase_momentum: str           # "driving" | "conversational" | "contemplative"
    cadence_descriptors: list[str]

@dataclass
class CadenceProfile:
    rhyme: RhymeAnalysis
    phrase: PhraseMetrics
    flow: FlowPattern
    section_cadences: dict[str, "CadenceProfile"]   # per-section breakdown
    raw_lines: list[str]
    constraint_block: str          # ready-to-inject LLM constraint text


# ── Syllable counting ─────────────────────────────────────────────────────────

_VOWELS = set("aeiouyAEIOUY")

def count_syllables(word: str) -> int:
    """Heuristic syllable counter for English."""
    word = re.sub(r"[^a-zA-Z]", "", word.lower())
    if not word:
        return 0
    count = 0
    prev_vowel = False
    for ch in word:
        is_v = ch in _VOWELS
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    # Silent trailing e
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def line_syllables(line: str) -> int:
    return sum(count_syllables(w) for w in line.split())


# ── Rhyme detection ───────────────────────────────────────────────────────────

def _end_sound(word: str) -> str:
    """Extract the rhyming end-sound (last vowel cluster + consonants)."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return ""
    # Find last vowel position
    last_v = -1
    for i, c in enumerate(word):
        if c in _VOWELS:
            last_v = i
    if last_v < 0:
        return word[-2:] if len(word) >= 2 else word
    return word[last_v:]


def _get_end_word(line: str) -> str:
    words = re.findall(r"[a-zA-Z]+", line)
    return words[-1] if words else ""


def _rhyme_scheme(lines: list[str]) -> tuple[str, list[str], float]:
    """Detect rhyme scheme. Returns (pattern_str, end_sounds, density)."""
    if not lines:
        return "free", [], 0.0

    end_sounds = [_end_sound(_get_end_word(l)) for l in lines]

    # Cluster identical/similar end sounds
    scheme_labels = []
    sound_to_label: dict[str, str] = {}
    label_counter = ord("A")

    for sound in end_sounds:
        # Check similarity to existing sounds (simple prefix match)
        matched = None
        for existing, lbl in sound_to_label.items():
            if existing and sound and (existing == sound or
               (len(existing) > 1 and len(sound) > 1 and existing[-2:] == sound[-2:])):
                matched = lbl
                break
        if matched:
            scheme_labels.append(matched)
        else:
            lbl = chr(label_counter)
            sound_to_label[sound] = lbl
            scheme_labels.append(lbl)
            if label_counter < ord("Z"):
                label_counter += 1

    pattern = "".join(scheme_labels[:8]) if len(scheme_labels) > 0 else "free"

    # Compute rhyme density
    rhyming = sum(1 for s in scheme_labels if scheme_labels.count(s) > 1)
    density = round(rhyming / len(scheme_labels), 2) if scheme_labels else 0.0

    return pattern, end_sounds, density


def _internal_rhyme_density(lines: list[str]) -> float:
    """Estimate internal rhyme density (words mid-line that share end-sounds)."""
    hits = 0
    total = 0
    for line in lines:
        words = re.findall(r"[a-zA-Z]+", line.lower())
        if len(words) < 4:
            continue
        sounds = [_end_sound(w) for w in words[:-1]]  # skip last word
        last = _end_sound(words[-1])
        for s in sounds:
            if s and last and len(s) > 1 and s[-2:] == last[-2:]:
                hits += 1
                break
        total += 1
    return round(hits / total, 2) if total else 0.0


# ── Phrase metrics ─────────────────────────────────────────────────────────────

def _phrase_metrics(lines: list[str]) -> tuple[PhraseMetrics, list[int]]:
    word_counts  = [len(re.findall(r"\S+", l)) for l in lines]
    syl_counts   = [line_syllables(l) for l in lines]
    breath_pts   = [i for i, l in enumerate(lines) if not l.strip()]

    if not word_counts:
        return PhraseMetrics(6.0, 1.0, 8.0, "medium", []), []

    avg_w = round(sum(word_counts) / len(word_counts), 1)
    std_w = round((sum((x - avg_w) ** 2 for x in word_counts) / len(word_counts)) ** 0.5, 1)
    avg_s = round(sum(syl_counts) / len(syl_counts), 1)

    if avg_w < 5:
        length_pat = "short"
    elif avg_w < 8:
        length_pat = "medium"
    elif avg_w < 11:
        length_pat = "long"
    else:
        length_pat = "variable"

    return (
        PhraseMetrics(avg_w, std_w, avg_s, length_pat, breath_pts),
        breath_pts,
    )


# ── Flow pattern ──────────────────────────────────────────────────────────────

def _flow_pattern(rhyme: RhymeAnalysis, phrase: PhraseMetrics, lines: list[str]) -> FlowPattern:
    # Density based on syllable density
    if phrase.avg_syllables_per_line > 10:
        density = "dense"
    elif phrase.avg_syllables_per_line > 6:
        density = "medium"
    else:
        density = "sparse"

    # Stress style from rhyme regularity
    if rhyme.rhyme_density > 0.7:
        stress = "on-beat"
    elif rhyme.internal_rhyme_density > 0.3:
        stress = "syncopated"
    else:
        stress = "free-verse"

    # Momentum from phrase variance
    if phrase.std_words_per_line < 1.5 and density == "dense":
        momentum = "driving"
    elif phrase.std_words_per_line > 3.0:
        momentum = "contemplative"
    else:
        momentum = "conversational"

    descriptors = []
    descriptors.append(f"{phrase.avg_syllables_per_line:.0f} syllables/line average")
    descriptors.append(f"{rhyme.scheme} rhyme scheme")
    if rhyme.rhyme_density > 0.6:
        descriptors.append("strong end-rhyme")
    if rhyme.internal_rhyme_density > 0.2:
        descriptors.append("internal rhymes present")
    descriptors.append(f"{phrase.line_length_pattern} line length")

    return FlowPattern(
        density=density,
        stress_style=stress,
        phrase_momentum=momentum,
        cadence_descriptors=descriptors,
    )


# ── Section extraction ────────────────────────────────────────────────────────

def _extract_sections(lyrics: str) -> dict[str, list[str]]:
    """Split lyrics into named sections."""
    sections: dict[str, list[str]] = {}
    current_section = "global"
    current_lines: list[str] = []

    for line in lyrics.splitlines():
        stripped = line.strip()
        if re.match(r"^\[.+\]", stripped):
            if current_lines:
                sections[current_section] = current_lines
            current_section = stripped.strip("[]").lower()
            current_lines = []
        else:
            if stripped:
                current_lines.append(stripped)

    if current_lines:
        sections[current_section] = current_lines

    return sections


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_cadence(lyrics: str) -> CadenceProfile:
    """
    Analyse lyrics and extract a full cadence profile for flow transfer.
    """
    # Global analysis
    all_lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not re.match(r"^\[", l.strip())]

    rhyme_pat, end_sounds, rhyme_dens = _rhyme_scheme(all_lines)
    int_rhyme = _internal_rhyme_density(all_lines)

    rhyme = RhymeAnalysis(
        scheme=rhyme_pat,
        end_sounds=end_sounds,
        rhyme_density=rhyme_dens,
        internal_rhyme_density=int_rhyme,
    )

    phrase, breath_pts = _phrase_metrics(all_lines)
    flow = _flow_pattern(rhyme, phrase, all_lines)

    # Per-section analysis
    sections = _extract_sections(lyrics)
    section_profiles: dict[str, CadenceProfile] = {}
    for sec_name, sec_lines in sections.items():
        if len(sec_lines) < 2:
            continue
        rp, es, rd = _rhyme_scheme(sec_lines)
        ir = _internal_rhyme_density(sec_lines)
        sr = RhymeAnalysis(rp, es, rd, ir)
        sp, _ = _phrase_metrics(sec_lines)
        sf = _flow_pattern(sr, sp, sec_lines)
        section_profiles[sec_name] = CadenceProfile(
            rhyme=sr, phrase=sp, flow=sf,
            section_cadences={}, raw_lines=sec_lines,
            constraint_block="",
        )

    constraint = build_flow_constraints_from_components(rhyme, phrase, flow)

    return CadenceProfile(
        rhyme=rhyme,
        phrase=phrase,
        flow=flow,
        section_cadences=section_profiles,
        raw_lines=all_lines,
        constraint_block=constraint,
    )


def build_flow_constraints_from_components(
    rhyme: RhymeAnalysis,
    phrase: PhraseMetrics,
    flow: FlowPattern,
) -> str:
    """Build an LLM-injectable constraint block from cadence components."""
    lines = [
        "CADENCE TRANSFER CONSTRAINTS (from source material):",
        f"• Rhyme scheme: {rhyme.scheme} — maintain this pattern in new verses",
        f"• Rhyme density: {rhyme.rhyme_density:.0%} of lines should end-rhyme",
        f"• Average words per line: {phrase.avg_words_per_line:.0f} (±{phrase.std_words_per_line:.0f})",
        f"• Average syllables per line: {phrase.avg_syllables_per_line:.0f}",
        f"• Line length pattern: {phrase.line_length_pattern}",
        f"• Flow density: {flow.density}",
        f"• Stress style: {flow.stress_style}",
        f"• Phrase momentum: {flow.phrase_momentum}",
    ]

    if rhyme.internal_rhyme_density > 0.15:
        lines.append(f"• Internal rhymes: present ({rhyme.internal_rhyme_density:.0%} density) — include internal rhymes")

    if flow.cadence_descriptors:
        lines.append(f"• Cadence notes: {'; '.join(flow.cadence_descriptors)}")

    lines.append(
        "INSTRUCTION: New verses MUST match these metrics. "
        "A producer should be able to sing the new verse over the same backing track "
        "without changing the tempo or feel."
    )

    return "\n".join(lines)


def build_flow_constraints(profile: CadenceProfile) -> str:
    """Get the constraint block from an extracted profile."""
    return profile.constraint_block
