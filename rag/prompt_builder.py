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


def _build_output_template(structure: str, bars: int = 16) -> str:
    """
    Inject an explicit section-by-section template with bar counts
    derived from the user's selected song length.
    Verse sections receive ~2× the lines of chorus/bridge sections.
    """
    sections = _parse_structure(structure)

    # Assign weight per section type (chorus = 1, verse = 2, intro/outro/pre = 0.75)
    weights: list[float] = []
    for sec in sections:
        lower = sec.lower().replace(" ", "")
        if any(k in lower for k in ("chorus", "hook", "refrain")):
            weights.append(1.0)
        elif any(k in lower for k in ("intro", "outro")):
            weights.append(0.75)
        elif "pre" in lower and "chorus" in lower:
            weights.append(0.75)
        elif "bridge" in lower:
            weights.append(1.0)
        else:
            weights.append(2.0)  # verses

    total_weight = sum(weights) or 1.0
    chorus_label: str | None = None
    lines: list[str] = []

    for sec, w in zip(sections, weights):
        lower = sec.lower().replace(" ", "")
        is_chorus = any(k in lower for k in ("chorus", "hook", "refrain"))
        is_bridge = "bridge" in lower
        is_outro  = "outro" in lower
        is_intro  = "intro" in lower
        is_pre    = "pre" in lower and "chorus" in lower

        sec_bars = max(2, round(bars * w / total_weight))
        label = f"[{sec}]"

        if is_intro:
            hint = f"(EXACTLY {sec_bars} lines — establish the scene or mood)"
        elif is_pre:
            hint = f"(EXACTLY {sec_bars} lines — build tension toward the chorus)"
        elif is_chorus and chorus_label is None:
            hint = f"(EXACTLY {sec_bars} lines — emotionally resonant hook, repeat verbatim each time)"
            chorus_label = sec
        elif is_chorus:
            hint = f"(repeat [{chorus_label}] verbatim — {sec_bars} lines)"
        elif is_bridge:
            hint = f"(EXACTLY {sec_bars} lines — shift in perspective or emotional peak)"
        elif is_outro:
            hint = f"(EXACTLY {sec_bars} lines — wind down or closing thought)"
        else:
            hint = f"(EXACTLY {sec_bars} lines — advance the story or emotion)"

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

Your mission: generate ORIGINAL lyrics indistinguishable from the specified artist's work.
Avoid all generic "AI-sounding" patterns. Deliver high-density, grounded, emotionally specific writing.

----------------------------------------
STYLE DEPTH (CRITICAL)
----------------------------------------

Go beyond surface imitation. Capture:
- The artist's specific vocabulary and slang
- Rhythm, cadence, and line-length variance
- Typical emotional contradictions unique to the artist
- Punctuation habits or intentional fragmentation

{style_instruction}

----------------------------------------
CHORUS ENGINE ({chorus_mode} MODE)
----------------------------------------

{chorus_rules}

----------------------------------------
ANTI-GENERIC RULES (MANDATORY)
----------------------------------------

STRICTLY FORBIDDEN in ANY language:
- "I still rise," "now I glow," "stronger than before," "tears like rain"
- Vague motivational filler that has no sensory or narrative specificity
- Direct translation of clichés from English into other languages

Every line must be GROUNDED in Conversational Realism and specific to the theme.

----------------------------------------
RETRIEVAL USAGE
----------------------------------------

Retrieved fragments below are STYLE EXAMPLES only. Study voice and texture.
DO NOT copy any actual lines.

----------------------------------------
LENGTH & BAR CONTROL (STRICT)
----------------------------------------

- Section headers like [Verse 1] or [Chorus] are NOT counted as lines/bars.
- Each non-header lyrical line = one bar.
- The output template below specifies EXACTLY how many lines each section needs.
- You MUST write every section listed. Do NOT stop until the final [Chorus] is written.
- An incomplete song (missing sections or empty sections) is a FAILURE.

----------------------------------------
LYRIC ALIGNMENT & CADENCE
----------------------------------------

- Lines should be SHORT and singable: 5 to 9 words per lyrical line.
- Maintain rhythmic consistency within each section.
- Cadence anchoring: end each verse with a phrase that leads into the chorus.

{producer_mode_block}
"""

_CHORUS_RULES_NATURAL = """\
NATURAL MODE (artist-style chorus):
- Mirror the length and density of the artist's real choruses.
- The first and last line of the chorus should share sonic resonance (not identical).
- The chorus must be repeatable and emotionally memorable.
- DO NOT restrict to 3 lines — match the artist's natural chorus length.
- Final line must resolve or twist the central hook idea."""

_CHORUS_RULES_STRICT = """\
STRICT HOOK MODE:
1. Hook Reinforcement: Use a central hook phrase. It MUST appear in Line 1 and Line 2 EXACTLY.
2. The chorus MUST be exactly 3 lines.
3. Each line MUST contain exactly 4 to 6 words.
4. VARIETY RULE: Line 3 MUST be conceptually different from Line 1. It resolves or twists the hook.

Example:
[Chorus]
White Ferrari, 3AM
White Ferrari, 3AM
Stayed until the end"""

_PRODUCER_MODE_BLOCK = """\
----------------------------------------
PRODUCER MODE (ACTIVE)
----------------------------------------

You are writing for a REAL MUSIC PRODUCTION. Prioritize:
- STRUCTURE COHERENCE: each section must flow naturally into the next.
- RHYME ALIGNMENT: end-rhymes must be consistent within sections.
- TEMPO MATCHING: line syllable counts must stay consistent within sections (±2 syllables).
- SINGABILITY: every line must be speakable in one breath at natural tempo.
Reduce abstract poetry. Prefer grounded, speakable, emotionally direct writing."""


def build_prompt(
    artists: list[str],
    theme: str,
    structure: str,
    retrieved_chunks: list[dict],
    language: str = "English",
    gender: str = "Neutral",
    bars: int = 16,
    reference_lyrics: str = "",
    mode: str = "generate",          # generate | continue | remix
    perspective_mode: str = "same",  # same | opposite | response
    extra_instructions: str = "",
    style_strength: float = 0.7,
    retrieval_quality: float = 0.5,
    analysis_mode: bool = False,
    remix_mode: bool = False,
    locked_chorus: str = "",
    chorus_strict: bool = False,     # False = natural artist style, True = 3-line strict
    producer_mode: bool = False,     # True = structure/rhyme/tempo emphasis
    instrumental_hint: str = "",     # vibe hint from uploaded instrumental
    # Intelligence Layer additions
    cadence_constraints: str = "",   # from services/cadence_analysis
    genre_tags: str = "",            # from services/genre_engine
    producer_controls_desc: str = "", # from ProducerControls.describe()
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for V4 Product Layer.
    """
    tier = _style_tier(style_strength)
    style_instruction = _STYLE_TIER_INSTRUCTIONS[tier]

    # ── Analysis mode ─────────────────────────────────────────────────────
    if analysis_mode:
        system_prompt = (
            "You are an ELITE music producer and lyrical analyst.\n"
            "Analyze the provided lyrics deeply — as a producer preparing a remix session.\n\n"
            "OUTPUT FORMAT (STRICT JSON — no markdown, no preamble):\n"
            "{\n"
            '  "theme": "Core theme in 1 sentence",\n'
            '  "tone": "Emotional tone and energy level",\n'
            '  "narrative_perspective": "First/second/third person + POV description",\n'
            '  "rhyme_scheme": "ABAB / AABB / free / etc.",\n'
            '  "avg_syllables_per_line": <number>,\n'
            '  "ideas": [\n'
            '    "New verse concept 1 — specific and grounded",\n'
            '    "New verse concept 2 — different emotional angle",\n'
            '    "New verse concept 3 — production direction"\n'
            '  ],\n'
            '  "how_to_improve": [\n'
            '    "Specific improvement 1 — line-level suggestion",\n'
            '    "Specific improvement 2 — rhyme or flow fix",\n'
            '    "Specific improvement 3 — structural or emotional note"\n'
            '  ],\n'
            '  "alternative_concept_ideas": [\n'
            '    "Alternative concept 1 — completely different angle on the same theme",\n'
            '    "Alternative concept 2 — genre or tonal shift suggestion"\n'
            '  ],\n'
            '  "opposite_perspective": "A 1-sentence summary of the opposite POV",\n'
            '  "continuation": "How the story could naturally continue in the next verse"\n'
            "}\n\n"
            f"Artist context: {', '.join(artists)}."
        )
        user_prompt = f"Analyze the following lyrics for a remix/production session:\n\n{reference_lyrics}"
        return system_prompt, user_prompt

    # ── Chorus mode selection ─────────────────────────────────────────────
    chorus_mode   = "STRICT HOOK" if chorus_strict else "NATURAL"
    chorus_rules  = _CHORUS_RULES_STRICT if chorus_strict else _CHORUS_RULES_NATURAL
    producer_block = _PRODUCER_MODE_BLOCK if producer_mode else ""

    system_prompt = _SYSTEM_BASE.format(
        prompt_version=PROMPT_VERSION,
        style_instruction=style_instruction,
        bars=bars,
        chorus_mode=chorus_mode,
        chorus_rules=chorus_rules,
        producer_mode_block=producer_block,
    )

    artist_str = " + ".join(artists) if len(artists) > 1 else artists[0]

    output_template = _build_output_template(structure, bars=bars)
    style_block     = _artist_style_block(artists)
    rq_note         = _retrieval_guidance(retrieval_quality, len(retrieved_chunks))
    chorus_hint     = _detect_chorus_pattern(retrieved_chunks)

    context_lines: list[str] = []
    seen: set[str] = set()
    for chunk in retrieved_chunks:
        key = f"{chunk['artist']}|||{chunk['song']}"
        if key in seen:
            continue
        seen.add(key)
        context_lines.append(f"[{chunk['artist']} / {chunk['song']}]\n{chunk['text']}")
    context_block = "\n\n---\n\n".join(context_lines) if context_lines else "(no examples retrieved)"

    # ── Mode instruction ──────────────────────────────────────────────────
    mode_instruction = ""
    if mode == "continue":
        mode_instruction = (
            "CONTINUATION MODE: Extend the story/narrative from the provided "
            "[REFERENCE LYRICS] seamlessly. Maintain the exact same tone, flow, and rhyme scheme."
        )
    elif mode == "remix" and remix_mode and locked_chorus:
        mode_instruction = (
            "REMIX MODE — CHORUS LOCKED:\n"
            "The following chorus is LOCKED. You MUST copy it VERBATIM every time "
            "[Chorus] appears in the structure.\n"
            "DO NOT alter, paraphrase, shorten, or improve it under any condition.\n\n"
            "=== LOCKED CHORUS (copy exactly) ===\n"
            f"{locked_chorus}\n"
            "=== END LOCKED CHORUS ===\n\n"
            "Your task: write ONLY the Verse 1, Verse 2, and Bridge sections.\n"
            "Rules:\n"
            "- Match the theme, tone, and emotional direction of the locked chorus\n"
            "- Use a rhyme scheme compatible with the chorus ending sounds\n"
            "- Keep line length consistent with the chorus style\n"
            "- Be specific and grounded — no generic filler"
        )
    elif mode == "remix":
        mode_instruction = (
            "REMIX MODE: Rewrite the ideas in [REFERENCE LYRICS] with the same core theme "
            "but using entirely different wording, metaphors, and stylistic variations."
        )

    # ── Perspective ───────────────────────────────────────────────────────
    gender_suffix = f" The narrator is {gender}." if gender and gender.lower() != "neutral" else ""
    if perspective_mode == "opposite":
        perspective_instruction = (
            "PERSPECTIVE: Write from the OPPOSITE emotional perspective. "
            f"If the theme implies regret, write from defiance or indifference.{gender_suffix}"
        )
    elif perspective_mode == "response":
        perspective_instruction = (
            "PERSPECTIVE: Write this as a RESPONSE to another character. "
            f"The reference lyrics were a message — you are replying in the artist's style.{gender_suffix}"
        )
    else:
        perspective_instruction = (
            f"PERSPECTIVE: Write from a {gender} perspective, "
            "maintaining the artist's natural point of view."
        )

    # ── Language enforcement ──────────────────────────────────────────────
    if language.lower() == "english":
        lang_instruction = "LANGUAGE: Write in English."
    else:
        lang_instruction = (
            f"LANGUAGE (CRITICAL): You MUST write ENTIRELY in {language}. "
            f"Every lyrical line, section content, and expression must be native {language}. "
            f"Do NOT write in English. Do NOT translate English clichés. "
            f"Think and write as a native {language}-speaking artist in the target genre. "
            f"Use idioms, slang, and cultural references natural to {language}-speaking audiences."
        )

    # ── Instrumental hint ─────────────────────────────────────────────────
    inst_block = ""
    if instrumental_hint:
        inst_block = (
            f"\nINSTRUMENTAL CONTEXT:\n"
            f"The user has uploaded an instrumental track described as: {instrumental_hint}\n"
            f"Write lyrics that match this vibe, energy, and emotional texture. "
            f"The lyrics must feel like they were written FOR this specific track.\n"
        )

    # ── Intelligence Layer blocks ─────────────────────────────────────────
    cadence_block = f"\n{cadence_constraints}\n" if cadence_constraints else ""
    genre_block = (
        f"\nGENRE DIRECTION:\nTarget genre tags for Suno and production: {genre_tags}\n"
        f"Align lyric density, vocabulary, and cadence to this genre feel.\n"
    ) if genre_tags else ""
    controls_block = (
        f"\nPRODUCER CONTROLS:\n{producer_controls_desc}\n"
        f"Let these controls shape tone, vocabulary intensity, and emotional temperature.\n"
    ) if producer_controls_desc else ""

    # ── Non-English artist style note ────────────────────────────────────
    non_english_style_note = ""
    if language.lower() != "english":
        non_english_style_note = (
            f"\nARTIST STYLE IN {language.upper()}: "
            f"If {artist_str} primarily performs in {language}, apply their authentic stylistic voice. "
            f"If they primarily perform in English, capture their thematic essence "
            f"(emotional depth, flow, vocabulary density) as a {language}-speaking artist in the same genre.\n"
        )

    user_prompt = (
        f"STYLE: {artist_str}\n"
        f"THEME: {theme}\n"
        f"{lang_instruction}\n"
        f"{non_english_style_note}"
        f"{inst_block}"
        f"{genre_block}"
        f"{controls_block}"
        f"{cadence_block}"
        f"{mode_instruction}\n"
        f"{perspective_instruction}\n"
        f"CRITICAL: Write EVERY section shown in the output template. "
        f"Follow the exact line counts specified per section. Do NOT stop until the song is complete.\n"
        f"{(f'ADDITIONAL NOTES: {extra_instructions}') if extra_instructions else ''}\n\n"
        f"{(f'REFERENCE LYRICS:\\n{reference_lyrics}') if reference_lyrics else ''}\n\n"
        f"{style_block}\n"
        f"{rq_note}\n"
        f"{chorus_hint}\n\n"
        f"=== REQUIRED OUTPUT FORMAT ===\n"
        f"{output_template}\n\n"
        f"=== RETRIEVED STYLE EXAMPLES ===\n"
        f"{context_block}\n\n"
        f"=== TASK ===\n"
        f"Write the complete lyrics following ALL constraints above.\n"
        f"Every word must feel like it belongs in the selected artist's catalogue.\n"
        f"Fully localize into {language}.\n"
    )

    return system_prompt, user_prompt
