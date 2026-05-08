"""
services/genre_engine.py — SonicFlow Advanced Genre Blending Engine

Loads genre profiles from data/genres/ and provides:
  - Single genre lookup
  - Genre blending (weighted interpolation of BPM, controls, tags)
  - Producer style control resolution
  - Suno prompt tag generation

Public API:
    list_genres() -> list[str]
    get_genre(name) -> GenreProfile | None
    blend_genres(primary, secondary, weight) -> BlendedGenre
    resolve_producer_controls(controls) -> ProducerControls
    build_suno_genre_tags(genre, controls, audio_analysis) -> str
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

GENRES_DIR = Path(__file__).resolve().parent.parent / "data" / "genres"

# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class GenreProfile:
    name: str
    tempo_range: list[int]
    groove: str
    instrumentation: list[str]
    energy_curve: str
    vocal_style: str
    prompt_tokens: list[str]
    # Producer controls (0-1 floats)
    darkness: float = 0.5
    melodicness: float = 0.5
    aggression: float = 0.5
    atmosphere: float = 0.5
    groove_density: float = 0.5

    @property
    def bpm_midpoint(self) -> float:
        return (self.tempo_range[0] + self.tempo_range[1]) / 2.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tempo_range": self.tempo_range,
            "groove": self.groove,
            "instrumentation": self.instrumentation,
            "energy_curve": self.energy_curve,
            "vocal_style": self.vocal_style,
            "prompt_tokens": self.prompt_tokens,
            "darkness": self.darkness,
            "melodicness": self.melodicness,
            "aggression": self.aggression,
            "atmosphere": self.atmosphere,
            "groove_density": self.groove_density,
        }


@dataclass
class BlendedGenre:
    primary: str
    secondary: str
    weight: float                   # 0.0=all primary, 1.0=all secondary
    bpm: float
    instrumentation: list[str]
    groove: str
    vocal_style: str
    prompt_tokens: list[str]
    darkness: float
    melodicness: float
    aggression: float
    atmosphere: float
    groove_density: float
    suno_tags: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ProducerControls:
    darkness: float       = 0.5   # 0=light/uplifting  1=dark/menacing
    melodicness: float    = 0.5   # 0=rhythmic/percussive  1=melodic/harmonic
    aggression: float     = 0.5   # 0=gentle  1=aggressive/intense
    atmosphere: float     = 0.5   # 0=dry/bare  1=atmospheric/lush
    groove_density: float = 0.5   # 0=sparse  1=busy/dense

    def describe(self) -> str:
        """Convert controls to human-readable production descriptors."""
        descriptors = []

        if self.darkness > 0.7:
            descriptors.append("dark and menacing atmosphere")
        elif self.darkness > 0.4:
            descriptors.append("moody undertones")
        else:
            descriptors.append("uplifting bright feel")

        if self.melodicness > 0.7:
            descriptors.append("strongly melodic and harmonic")
        elif self.melodicness < 0.3:
            descriptors.append("rhythm-forward percussive feel")
        else:
            descriptors.append("balanced melody and rhythm")

        if self.aggression > 0.7:
            descriptors.append("aggressive intense energy")
        elif self.aggression > 0.4:
            descriptors.append("confident assertive tone")
        else:
            descriptors.append("calm restrained delivery")

        if self.atmosphere > 0.7:
            descriptors.append("rich atmospheric texture")
        elif self.atmosphere < 0.3:
            descriptors.append("dry sparse production")

        if self.groove_density > 0.8:
            descriptors.append("dense layered groove")
        elif self.groove_density < 0.3:
            descriptors.append("open minimalist groove")

        return "; ".join(descriptors)

    def to_suno_modifiers(self) -> list[str]:
        mods = []
        if self.darkness > 0.6:
            mods.append("dark")
        if self.darkness < 0.3:
            mods.append("bright")
        if self.melodicness > 0.7:
            mods.append("melodic")
        if self.aggression > 0.7:
            mods.append("aggressive")
        if self.atmosphere > 0.7:
            mods.append("atmospheric")
        if self.groove_density > 0.8:
            mods.append("dense production")
        return mods


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, GenreProfile] = {}
_LOADED = False


def _load_genres() -> None:
    global _LOADED
    if _LOADED:
        return
    GENRES_DIR.mkdir(parents=True, exist_ok=True)
    for path in GENRES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            profile = GenreProfile(
                name=data["name"],
                tempo_range=data.get("tempo_range", [90, 130]),
                groove=data.get("groove", ""),
                instrumentation=data.get("instrumentation", []),
                energy_curve=data.get("energy_curve", ""),
                vocal_style=data.get("vocal_style", ""),
                prompt_tokens=data.get("prompt_tokens", []),
                darkness=float(data.get("darkness", 0.5)),
                melodicness=float(data.get("melodicness", 0.5)),
                aggression=float(data.get("aggression", 0.5)),
                atmosphere=float(data.get("atmosphere", 0.5)),
                groove_density=float(data.get("groove_density", 0.5)),
            )
            key = profile.name.lower().replace(" ", "_").replace("-", "_")
            _REGISTRY[key] = profile
        except Exception as e:
            print(f"[GENRE] Failed to load {path.name}: {e}", flush=True)
    _LOADED = True
    print(f"[GENRE] Loaded {len(_REGISTRY)} genre profiles", flush=True)


def list_genres() -> list[str]:
    _load_genres()
    return sorted(p.name for p in _REGISTRY.values())


def get_genre(name: str) -> Optional[GenreProfile]:
    _load_genres()
    key = name.lower().replace(" ", "_").replace("-", "_")
    return _REGISTRY.get(key)


# ── Blending ──────────────────────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blend_genres(
    primary: str,
    secondary: str,
    weight: float = 0.5,
) -> BlendedGenre:
    """
    Blend two genres. weight=0 → all primary, weight=1 → all secondary.
    """
    _load_genres()
    p = get_genre(primary)
    s = get_genre(secondary)

    if p is None and s is None:
        raise ValueError(f"Neither genre found: {primary!r}, {secondary!r}")
    if p is None:
        p = s
    if s is None:
        s = p

    w = max(0.0, min(1.0, weight))

    bpm = _lerp(p.bpm_midpoint, s.bpm_midpoint, w)

    # Interleave instrumentation
    p_inst = p.instrumentation[:4]
    s_inst = [i for i in s.instrumentation[:4] if i not in p_inst]
    instrumentation = p_inst + s_inst[:max(1, int(len(s_inst) * w))]

    # Weighted groove descriptor
    groove = p.groove if w < 0.5 else s.groove

    # Vocal style blend
    vocal_style = f"{p.vocal_style} with {s.name.lower()} influence" if w < 0.5 \
        else f"{s.vocal_style} with {p.name.lower()} influence"

    # Merged prompt tokens (deduplicated)
    seen = set()
    tokens = []
    for t in (p.prompt_tokens + s.prompt_tokens):
        if t not in seen:
            seen.add(t)
            tokens.append(t)

    # Interpolated producer controls
    darkness     = round(_lerp(p.darkness, s.darkness, w), 3)
    melodicness  = round(_lerp(p.melodicness, s.melodicness, w), 3)
    aggression   = round(_lerp(p.aggression, s.aggression, w), 3)
    atmosphere   = round(_lerp(p.atmosphere, s.atmosphere, w), 3)
    groove_dens  = round(_lerp(p.groove_density, s.groove_density, w), 3)

    # Suno tag string
    top_tokens = tokens[:5]
    suno_tags = (
        f"{bpm:.0f}bpm, {', '.join(top_tokens)}, "
        f"{'dark' if darkness > 0.6 else 'bright'}, "
        f"{'melodic' if melodicness > 0.6 else 'rhythmic'}"
    )

    return BlendedGenre(
        primary=p.name,
        secondary=s.name,
        weight=w,
        bpm=round(bpm, 1),
        instrumentation=instrumentation,
        groove=groove,
        vocal_style=vocal_style,
        prompt_tokens=tokens,
        darkness=darkness,
        melodicness=melodicness,
        aggression=aggression,
        atmosphere=atmosphere,
        groove_density=groove_dens,
        suno_tags=suno_tags,
    )


# ── Producer controls ─────────────────────────────────────────────────────────

def resolve_producer_controls(controls: dict) -> ProducerControls:
    """Parse and clamp a dict of producer control values."""
    def clamp(v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    return ProducerControls(
        darkness=clamp(controls.get("darkness", 0.5)),
        melodicness=clamp(controls.get("melodicness", 0.5)),
        aggression=clamp(controls.get("aggression", 0.5)),
        atmosphere=clamp(controls.get("atmosphere", 0.5)),
        groove_density=clamp(controls.get("groove_density", 0.5)),
    )


# ── Suno prompt composer ──────────────────────────────────────────────────────

def build_suno_genre_tags(
    genre_name: Optional[str],
    controls: Optional[ProducerControls],
    audio_analysis=None,   # AudioAnalysis | None
    artist_style: str = "",
    language: str = "English",
) -> str:
    """
    Build a rich structured Suno prompt from genre + controls + audio analysis.
    This is the advanced Suno prompt composer (Phase 5).
    """
    parts: list[str] = []

    # 1. Genre base tags
    if genre_name:
        genre = get_genre(genre_name)
        if genre:
            parts += genre.prompt_tokens[:4]
        else:
            parts.append(genre_name)

    # 2. Audio analysis tags
    if audio_analysis and audio_analysis.error is None:
        parts.append(f"{audio_analysis.beat.bpm:.0f}bpm")
        parts.append(audio_analysis.harmonic.key.lower())
        if audio_analysis.energy.intensity in ("high", "very high"):
            parts.append("energetic")
        if audio_analysis.cadence.stress_pattern == "syncopated":
            parts.append("syncopated")

    # 3. Producer control modifiers
    if controls:
        parts += controls.to_suno_modifiers()

    # 4. Artist style
    if artist_style:
        parts.append(f"{artist_style} inspired")

    # 5. Language tag (for non-English)
    if language and language.lower() != "english":
        parts.append(language.lower())

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return ", ".join(unique) if unique else "pop, melodic"
