"""
services/remix_engine.py — SonicFlow Remix Intelligence Engine

Orchestrates multi-genre remix variant generation.
Uses the cadence system + genre engine to produce genuine remixes:
NOT just temperature changes — actual genre/style/instrumentation shifts.

Public API:
    generate_remix_variants(request) -> list[RemixVariant]
    build_remix_prompt(genre, locked_chorus, cadence_profile, controls) -> str
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from services.genre_engine import GenreProfile, ProducerControls, get_genre, build_suno_genre_tags
from services.cadence_analysis import CadenceProfile


# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class RemixVariantRequest:
    locked_chorus: str
    original_lyrics: str
    theme: str
    artists: list[str]
    target_genres: list[str]           # e.g. ["drill", "edm", "acoustic"]
    bars: int = 16
    language: str = "English"
    cadence_profile: Optional[CadenceProfile] = None
    controls: Optional[ProducerControls] = None
    audio_analysis: Optional[object] = None   # AudioAnalysis | None

@dataclass
class RemixVariant:
    genre: str
    lyrics: str
    locked_chorus: str
    suno_tags: str
    style_notes: str
    instrumentation: list[str]
    bpm_target: float
    cadence_match_score: float        # 0-1 quality estimate

    def to_dict(self) -> dict:
        return self.__dict__


# ── Remix prompt builder ──────────────────────────────────────────────────────

def build_remix_prompt(
    genre: Optional[GenreProfile],
    locked_chorus: str,
    cadence_profile: Optional[CadenceProfile],
    controls: Optional[ProducerControls],
    theme: str,
    artists: list[str],
    bars: int,
    language: str,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for a genre remix.
    Incorporates locked chorus, cadence constraints, and genre direction.
    """
    genre_name = genre.name if genre else "Contemporary Pop"
    groove = genre.groove if genre else "melodic groove"
    vocal_style = genre.vocal_style if genre else "melodic delivery"
    bpm = genre.bpm_midpoint if genre else 120.0

    controls_desc = controls.describe() if controls else "balanced production feel"

    cadence_block = ""
    if cadence_profile:
        cadence_block = f"\n{cadence_profile.constraint_block}\n"

    system_prompt = f"""You are an elite remix producer and songwriter.

MISSION: Write a {genre_name.upper()} REMIX of the provided song.

GENRE BLUEPRINT
───────────────
Genre:         {genre_name}
BPM target:    {bpm:.0f} BPM
Groove:        {groove}
Vocal style:   {vocal_style}
Production:    {controls_desc}

ABSOLUTE RULES
──────────────
1. The [Chorus] sections MUST be copied VERBATIM from the LOCKED CHORUS below.
   Do NOT change a single word.
2. Write ONLY the verse sections (and bridge if requested).
3. The verses MUST feel like they belong to the genre "{genre_name}".
4. Maintain thematic continuity with the locked chorus.
5. Language: write in {language}.
{cadence_block}
ANTI-GENERIC MANDATE
────────────────────
DO NOT write generic AI lyrics. Every line must be:
- Grounded in specific imagery
- Stylistically aligned with {genre_name}
- Singable at {bpm:.0f} BPM
"""

    artist_str = " + ".join(artists) if artists else "the artist"
    locked_chorus_block = (
        f"\n=== LOCKED CHORUS (copy VERBATIM each time [Chorus] appears) ===\n"
        f"{locked_chorus}\n"
        f"=== END LOCKED CHORUS ===\n"
    )

    user_prompt = (
        f"STYLE: {artist_str} in {genre_name} style\n"
        f"THEME: {theme}\n"
        f"LANGUAGE: {language}\n"
        f"BARS: {bars} total lyrical lines\n\n"
        f"{locked_chorus_block}\n"
        f"Write ONLY the verse and bridge sections. "
        f"Insert the locked chorus verbatim wherever [Chorus] appears in the structure.\n\n"
        f"Structure:\n"
        f"[Verse 1]\n(EXACTLY {max(4, bars // 3)} lines — {genre_name} style, {bpm:.0f} BPM feel)\n\n"
        f"[Chorus]\n(COPY LOCKED CHORUS VERBATIM)\n\n"
        f"[Verse 2]\n(EXACTLY {max(4, bars // 3)} lines — advance the story)\n\n"
        f"[Chorus]\n(COPY LOCKED CHORUS VERBATIM)\n\n"
        f"[Bridge]\n(EXACTLY {max(2, bars // 6)} lines — emotional peak or genre drop moment)\n\n"
        f"[Chorus]\n(COPY LOCKED CHORUS VERBATIM)"
    )

    return system_prompt, user_prompt


# ── Variant generation ────────────────────────────────────────────────────────

def generate_remix_variants(
    request: RemixVariantRequest,
    openai_client=None,
    model: str = "gpt-4o-mini",
) -> list[RemixVariant]:
    """
    Generate one remix variant per target genre.
    Uses the OpenAI client directly for clean separation from the RAG pipeline.
    Falls back gracefully if a genre is unknown.
    """
    if openai_client is None:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    variants: list[RemixVariant] = []

    for genre_name in request.target_genres:
        genre = get_genre(genre_name)

        try:
            sys_p, usr_p = build_remix_prompt(
                genre=genre,
                locked_chorus=request.locked_chorus,
                cadence_profile=request.cadence_profile,
                controls=request.controls,
                theme=request.theme,
                artists=request.artists,
                bars=request.bars,
                language=request.language,
            )

            resp = openai_client.chat.completions.create(
                model=model,
                temperature=0.85,
                max_tokens=1200,
                messages=[
                    {"role": "system", "content": sys_p},
                    {"role": "user",   "content": usr_p},
                ],
            )
            lyrics = resp.choices[0].message.content.strip()

            # Ensure locked chorus is present verbatim
            if request.locked_chorus and "[Chorus]" in lyrics:
                lyrics = _inject_locked_chorus(lyrics, request.locked_chorus)

            suno_tags = build_suno_genre_tags(
                genre_name=genre_name,
                controls=request.controls,
                audio_analysis=request.audio_analysis,
                artist_style=request.artists[0] if request.artists else "",
                language=request.language,
            )

            style_notes = (
                f"{genre.name} remix: {genre.groove}, ~{genre.bpm_midpoint:.0f} BPM, "
                f"{genre.vocal_style}"
            ) if genre else f"{genre_name} remix"

            cadence_score = _estimate_cadence_match(lyrics, request.cadence_profile)

            variants.append(RemixVariant(
                genre=genre.name if genre else genre_name,
                lyrics=lyrics,
                locked_chorus=request.locked_chorus,
                suno_tags=suno_tags,
                style_notes=style_notes,
                instrumentation=genre.instrumentation[:4] if genre else [],
                bpm_target=genre.bpm_midpoint if genre else 120.0,
                cadence_match_score=cadence_score,
            ))

            print(f"[REMIX] {genre_name} variant complete — {len(lyrics.splitlines())} lines", flush=True)

        except Exception as exc:
            print(f"[REMIX] Failed for genre {genre_name!r}: {exc}", flush=True)

    return variants


def _inject_locked_chorus(lyrics: str, locked_chorus: str) -> str:
    """Replace any [Chorus] section content with the locked chorus verbatim."""
    import re
    # Find all [Chorus] blocks and replace their content
    def replace_chorus(m):
        return f"[Chorus]\n{locked_chorus.strip()}"

    return re.sub(
        r"\[Chorus[^\]]*\]\n.*?(?=\n\[|\Z)",
        replace_chorus,
        lyrics,
        flags=re.DOTALL,
    )


def _estimate_cadence_match(lyrics: str, profile: Optional[CadenceProfile]) -> float:
    """Quick heuristic cadence match score (0-1)."""
    if profile is None:
        return 0.5

    from services.cadence_analysis import extract_cadence
    try:
        new_profile = extract_cadence(lyrics)
        # Compare syllable density and line length
        syl_diff = abs(new_profile.phrase.avg_syllables_per_line - profile.phrase.avg_syllables_per_line)
        word_diff = abs(new_profile.phrase.avg_words_per_line - profile.phrase.avg_words_per_line)
        score = max(0.0, 1.0 - (syl_diff / 8.0) - (word_diff / 4.0))
        return round(score, 2)
    except Exception:
        return 0.5
