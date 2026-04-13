"""
Prompt Builder  (v3 — adaptive style_strength + retrieval-quality tuning)
=========================================================================
New in this version:
  - style_strength (0.0 → 1.0): scales how strictly the LLM imitates the
    target artist.  Low = loose inspiration, high = strict imitation.
    Maps to three prompt tiers: "loose", "moderate", "strict".
  - retrieval_quality (0.0 → 1.0): if retrieval confidence is weak,
    extra guidance is added to compensate.  If retrieval is strong, the
    LLM is given more freedom to lean on examples.
  - Adaptive chorus detection: counts chorus/hook chunks in retrieved set
    and reflects the dominant repetition pattern in the prompt.
  - PROMPT_VERSION constant used for logging/reproducibility.

Usage:
    from rag.prompt_builder import build_prompt
    system_p, user_p = build_prompt(
        artists=["Drake", "SZA"],
        theme="heartbreak",
        structure="Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Outro",
        retrieved_chunks=[...],
        style_strength=0.8,
        retrieval_quality=0.65,
    )
"""

from __future__ import annotations

import re

from utils.config import PROMPT_VERSION

# ── Structure parsing ─────────────────────────────────────────────────────

def _parse_structure(structure: str) -> list[str]:
    parts = re.split(r"[→,\n]+", structure)
    return [p.strip() for p in parts if p.strip()]


def _build_output_template(structure: str) -> str:
    """
    Inject an explicit section-by-section template so the LLM knows
    exactly how to label and size each section.
    """
    sections = _parse_structure(structure)
    lines: list[str] = []
    chorus_label: str | None = None

    for sec in sections:
        lower = sec.lower().replace(" ", "")
        is_chorus = any(k in lower for k in ("chorus", "hook", "refrain"))
        is_bridge = "bridge" in lower
        is_outro  = "outro" in lower
        is_intro  = "intro" in lower
        is_pre    = "pre" in lower and "chorus" in lower

        label = f"[{sec}]"
        if is_intro:
            hint = "(2–4 lines, establish the scene or mood)"
        elif is_pre:
            hint = "(2–4 lines, build tension toward the chorus)"
        elif is_chorus and chorus_label is None:
            hint = "(2–6 lines, emotionally resonant — will repeat verbatim)"
            chorus_label = sec
        elif is_chorus:
            hint = f"(repeat [{chorus_label}] verbatim or near-verbatim)"
        elif is_bridge:
            hint = "(4–8 lines, shift in perspective or emotional peak)"
        elif is_outro:
            hint = "(2–4 lines, wind down or closing thought)"
        else:
            hint = "(6–10 lines, advance the story or emotion)"

        lines.append(f"{label}\n{hint}")

    return "\n\n".join(lines)


# ── Style strength tiers ──────────────────────────────────────────────────

def _style_tier(style_strength: float) -> str:
    """Map 0-1 float to a tier string."""
    if style_strength >= 0.75:
        return "strict"
    if style_strength >= 0.40:
        return "moderate"
    return "loose"


_STYLE_TIER_INSTRUCTIONS: dict[str, str] = {
    "strict": (
        "STRICT IMITATION MODE: Mirror the artist's exact vocabulary, slang, "
        "rhyme scheme, cadence, and recurring motifs as closely as possible "
        "without copying actual lines. A listener should immediately recognise the style."
    ),
    "moderate": (
        "MODERATE STYLE MODE: Capture the overall feel, vocabulary, and flow of "
        "the artist without rigid imitation. Allow creative interpretation while "
        "keeping the stylistic DNA recognisable."
    ),
    "loose": (
        "LOOSE INSPIRATION MODE: Use the artist as a starting point. Prioritise "
        "thematic resonance and emotional authenticity over strict stylistic matching."
    ),
}


# ── Artist style fingerprints ─────────────────────────────────────────────

# ── Artist style fingerprints ─────────────────────────────────────────────

_STYLE_NOTES: dict[str, str] = {
    "Drake":             "introspective bars mixed with singing, braggadocious yet vulnerable, name-drops, melodic hooks",
    "Kendrick Lamar":    "dense internal rhymes, social/political commentary, polysyllabic wordplay, concept-driven",
    "J. Cole":           "smooth reflective cadence, minimal hook dependency, conversational bars, storytelling",
    "Travis Scott":      "auto-tune melodic flow, abstract/surreal imagery, hypnotic repetition, atmospheric texture",
    "The Weeknd":        "dark R&B, cinematic excess, haunting falsetto, hedonistic regret",
    "Taylor Swift":      "narrative detail, specific imagery, clever ABAB rhymes, emotional vulnerability",
    "Billie Eilish":     "whisper dynamics, dark-pop, confessional intimacy, unconventional quiet-loud structure",
    "SZA":               "free-flowing R&B, raw emotional honesty, jazz-inflected phrasing, conversational verse",
    "Frank Ocean":       "non-linear narrative, layered subtext, sparse references, introspective stream-of-consciousness",
    "Ariana Grande":     "melismatic power runs, high-note climaxes, love/empowerment themes, pop hooks",
    "Bad Bunny":         "reggaeton flow, Spanglish code-switching, street playfulness, romantic vulnerability",
    "Tyler the Creator": "stream-of-consciousness, vivid surreal imagery, unconventional rhyme schemes, genre-blending",
    "Doja Cat":          "witty punchlines, rapid flow switches, infectious pop-rap hooks, playful self-awareness",
    "Childish Gambino":  "meta self-awareness, genre fluidity, layered pop-culture references, emotional swing",
    "Post Malone":       "melodic singing-rap blend, melancholic undertone, catchy hooks, lifestyle themes",
    "Lil Wayne":         "rapid-fire punchlines, multi-layered metaphors, wordplay-dense verse, ad-libs",
    "Nicki Minaj":       "aggressive flow switches, theatrical personas, sharp punchlines, pop hooks",
    "Cardi B":           "brash confidence, street authenticity, rhythmic punch, boastful themes",
    "Brent Faiyaz":      "vulnerable toxic R&B, high-register vocals, cynical romanticism, layered harmonies",
    "PinkPantheress":    "fast-paced UK garage beats, delicate vocals, nostalgic loops, short punchy songs",
    "Morgan Wallen":     "Southern drawl storytelling, rural imagery, whiskey/nostalgia themes, singalong choruses",
    "Coldplay":          "anthemic melodic rises, hope-in-darkness imagery, piano-driven feel, uplifting resolution",
    "Imagine Dragons":   "epic arena-rock swell, personal-demon battle, power-chorus anthems",
}

_GENRE_NOTES: dict[str, str] = {
    "hip-hop":    "rhythmic flow, verse-hook structure, internal rhymes, cultural references",
    "pop":        "memorable catchy hooks, emotional resonance, clean rhymes, anthemic choruses",
    "r&b":        "smooth melodies, sensual/emotional imagery, vocal runs, love and longing",
    "rock":       "raw energy, power imagery, anthemic choruses, personal defiance",
    "country":    "storytelling, rural/heartland imagery, singalong hooks, twangy phrasing",
    "latin":      "reggaeton rhythm, Spanish/Spanglish, romantic or party themes",
    "afrobeats":   "percussive polyrhythms, melodic pidgin hooks, vibrant energy, rhythmic repetition",
    "electronic": "hypnotic repetition, euphoric builds, minimal lyrics, drop-centric structure",
}


def _artist_style_block(artists: list[str]) -> str:
    lines: list[str] = []
    for a in artists:
        note = _STYLE_NOTES.get(a)
        if note:
            lines.append(f"• {a}: {note}")
    return ("**Artist style fingerprints:**\n" + "\n".join(lines)) if lines else ""


# ── Retrieval-quality guidance ────────────────────────────────────────────

def _retrieval_guidance(retrieval_quality: float, n_chunks: int) -> str:
    """Return extra instruction based on how good retrieval was."""
    if n_chunks == 0:
        return (
            "No examples were retrieved. Rely entirely on your own knowledge of the "
            "artist's style — be extra deliberate about vocabulary and flow choices."
        )
    if retrieval_quality < 0.35:
        return (
            "Retrieval confidence is LOW. The examples below may not perfectly match the "
            "requested style. Prioritise the artist style fingerprints over the examples."
        )
    if retrieval_quality >= 0.70:
        return (
            "Retrieval confidence is HIGH. The examples below are strong style matches — "
            "lean into their vocabulary and flow patterns."
        )
    return ""   # moderate quality — no extra instruction needed


# ── Adaptive repetition detection ─────────────────────────────────────────

def _detect_chorus_pattern(chunks: list[dict]) -> str:
    """
    Count retrieved chorus/hook chunks and return a repetition hint.
    """
    hook_chunks = [
        c for c in chunks
        if any(k in c.get("section", "").lower() for k in ("chorus", "hook", "refrain"))
    ]
    if not hook_chunks:
        return ""
    avg_lines = sum(
        len([l for l in c.get("text", "").split("\n") if l.strip()])
        for c in hook_chunks
    ) / len(hook_chunks)
    return (
        f"Pattern hint: retrieved chorus/hook sections average "
        f"{avg_lines:.0f} lines — match this length for authenticity."
    )


# ── System prompt ─────────────────────────────────────────────────────────

_SYSTEM_BASE = """\
You are an ELITE songwriter and stylistic chameleon. 
Prompt version: {prompt_version}

Your mission is to generate ORIGINAL lyrics that are indistinguishable from the specified artist's actual work. You must avoid generic "AI-sounding" patterns and deliver high-density, grounded, and emotionally specific writing.

----------------------------------------
STYLE DEPTH (CRITICAL)
----------------------------------------

You MUST go beyond surface imitation. Mimic the artist's:
- Specific vocabulary and slang
- Rhythm, cadence, and line-length variance
- Typical contradictions (e.g., Drake's "successful but lonely", SZA's "raw but poetic")
- Punctuation habits or intentional fragmentation

{style_instruction}

----------------------------------------
CHORUS ENGINE (STRICT REINFORCEMENT)
----------------------------------------

The chorus MUST follow these "Repeatable Rhythm" rules:
1. Hook Reinforcement: Use a central hook phrase. It MUST appear in Line 1 and Line 2 EXACTLY.
2. 3-Line Absolute: The chorus MUST be exactly 3 lines.
3. Word Density: Each line MUST contain exactly 4 to 5 words.
4. VARIETY RULE: Line 3 MUST be conceptually and lyrically different from Line 1. DO NOT repeat the hook in Line 3. Use Line 3 to resolve the thought or add a twist.

Correct Example:
[Chorus]
White Ferrari, 3AM
White Ferrari, 3AM
Stayed until the end

----------------------------------------
ANTI-GENERIC RULES (MANDATORY)
----------------------------------------

STRICTLY FORBIDDEN:
- "I still rise," "now I glow," "stronger than before."
- Any generic "broken heart" or "tears like rain" clichés.
- Overly motivational or vague poetic filler.

Every line must be GROUNDED in Conversational Realism.

----------------------------------------
RETRIEVAL USAGE
----------------------------------------

You are given fragments from real songs. Use them EXCLUSIVELY to study voice and texture. DO NOT COPY text.
"""


def build_prompt(
    artists: list[str],
    theme: str,
    structure: str,
    retrieved_chunks: list[dict],
    language: str = "English",
    gender: str = "Neutral",
    bars: int = 16,
    reference_lyrics: str = "",
    mode: str = "generate", # generate, continue, remix
    perspective_mode: str = "same", # same, opposite, response
    extra_instructions: str = "",
    style_strength: float = 0.7,
    retrieval_quality: float = 0.5,
    analysis_mode: bool = False,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for V3 Product Layer.
    """
    tier = _style_tier(style_strength)
    style_instruction = _STYLE_TIER_INSTRUCTIONS[tier]

    if analysis_mode:
        system_prompt = f"""You are an ELITE Lyrical Analyst. 
Your task is to analyze the provided lyrics and provide:
1. THEMES: Core concepts explored.
2. EMOTIONS: Primary feelings conveyed.
3. VERSE IDEAS: Specific suggestions for new verses.
4. ALTERNATIVE PERSPECTIVES: How another character might view these events.

Style inspiration should remain grounded in: {", ".join(artists)}.
"""
        user_prompt = f"Analyze the following lyrics:\n\n{reference_lyrics}"
        return system_prompt, user_prompt

    system_prompt = _SYSTEM_BASE.format(
        prompt_version=PROMPT_VERSION,
        style_instruction=style_instruction,
    )

    artist_str = " + ".join(artists) if len(artists) > 1 else artists[0]

    # Output template
    output_template = _build_output_template(structure)

    # Artist style block
    style_block = _artist_style_block(artists)

    # Retrieval quality guidance
    rq_note = _retrieval_guidance(retrieval_quality, len(retrieved_chunks))

    # Chorus pattern hint
    chorus_hint = _detect_chorus_pattern(retrieved_chunks)

    # Context block
    context_lines: list[str] = []
    seen = set()
    for chunk in retrieved_chunks:
        key = f"{chunk['artist']}|||{chunk['song']}"
        if key in seen: continue
        seen.add(key)
        context_lines.append(f"[{chunk['artist']} / {chunk['song']}]\n{chunk['text']}")

    context_block = "\n\n---\n\n".join(context_lines) if context_lines else "(no examples retrieved)"

    # --- Mode-specific Logic ---
    mode_instruction = ""
    if mode == "continue":
        mode_instruction = f"CONTINUATION MODE: Extend the story/narrative from the provided [REFERENCE LYRICS] seamlessly. Maintain the exact same tone and flow."
    elif mode == "remix":
        mode_instruction = f"REMIX MODE: Rewrite the ideas in [REFERENCE LYRICS] with the same core theme but using entirely different wording, metaphors, and stylistic variations. A new 'take' on the old song."

    # --- Perspective logic ---
    perspective_instruction = ""
    if perspective_mode == "opposite":
        perspective_instruction = "PERSPECTIVE: Write from the OPPOSITE emotional perspective of the theme/reference. If the theme is regret, write from a place of defiance or indifference."
    elif perspective_mode == "response":
        perspective_instruction = "PERSPECTIVE: Write this as a RESPONSE to another character. Imagine the reference lyrics were a message sent to you, and you are replying in the artist's style."
    else:
        perspective_instruction = f"PERSPECTIVE: Write from a {gender} perspective, maintaining the primary point of view of the artist."

    # --- Language Enforcement ---
    lang_instruction = f"LANGUAGE: You MUST write ONLY in {language}. Do not mix languages unless explicitly part of the artist's style (like Spanglish for Bad Bunny). Enforce linguistic purity for {language}."

    user_prompt = f"""STYLE: {artist_str}
THEME: {theme}
{lang_instruction}
{mode_instruction}
{perspective_instruction}
LENGTH CONSTRAINT: Ensure each verse is exactly {bars} lines (bars) long.
{f'ADDITIONAL NOTES: {extra_instructions}' if extra_instructions else ''}

{f'REFERENCE LYRICS: \n{reference_lyrics}' if reference_lyrics else ''}

{style_block}
{rq_note}
{chorus_hint}

=== REQUIRED OUTPUT FORMAT ===
{output_template}

=== RETRIEVED STYLE EXAMPLES ===
{context_block}

=== TASK ===
Write the lyrics following the format and style constraints above.
Ensure everything is fully localized into {language}.
"""

    return system_prompt, user_prompt
