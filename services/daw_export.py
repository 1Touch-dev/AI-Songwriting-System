"""
services/daw_export.py — SonicFlow DAW Session Export Engine

Generates:
  - project.json (full metadata + arrangement)
  - arrangement_markers.json (Verse/Chorus/Bridge positions)
  - tempo_map.json
  - chord_midi.mid (chord MIDI from harmonic analysis)
  - melody_guide.mid (melodic contour guide)
  - session.zip (all of the above + stems + lyrics.txt)

Public API:
    build_daw_session(request) -> DAWSession
    export_session_zip(session) -> bytes
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ArrangementMarker:
    label: str          # "Verse 1", "Chorus", "Bridge", etc.
    bar_number: int
    beat_position: float   # absolute beat (bar * beats_per_bar)
    time_s: float          # seconds from start
    color: str             # for DAW color coding
    energy_level: float = 0.5     # 0-1 normalised energy for this section
    tempo_bpm: float = 120.0      # tempo at this section (allows future tempo changes)

@dataclass
class TempoMap:
    bpm: float
    time_signature: str    # "4/4"
    beats_per_bar: int
    total_bars: int
    total_beats: float
    total_duration_s: float
    beat_grid: list[float]  # beat timestamps in seconds

@dataclass
class TrackMetadata:
    title: str
    artist: str
    theme: str
    key: str
    bpm: float
    lyrics: str
    language: str
    output_mode: str
    generated_at: str
    version: str = "SonicFlow v5"

@dataclass
class StemFiles:
    vocals: Optional[str] = None    # filename or None
    drums: Optional[str] = None
    bass: Optional[str] = None
    other: Optional[str] = None     # music/melody layer
    mix: Optional[str] = None       # full mix

@dataclass
class DAWSession:
    project: TrackMetadata
    tempo_map: TempoMap
    markers: list[ArrangementMarker]
    stems: StemFiles
    chord_midi_bytes: Optional[bytes] = None
    melody_midi_bytes: Optional[bytes] = None
    session_id: str = ""

    def to_project_json(self) -> dict:
        return {
            "sonicflow_version": "5.0.0",
            "session_id": self.session_id,
            "generated_at": self.project.generated_at,
            "track": asdict(self.project),
            "tempo_map": asdict(self.tempo_map),
            "arrangement": [asdict(m) for m in self.markers],
            "stems": asdict(self.stems),
        }


# ── Marker colors ─────────────────────────────────────────────────────────────

_SECTION_COLORS = {
    "intro":      "#5B8CFF",
    "verse":      "#4CAF50",
    "pre-chorus": "#FFC107",
    "chorus":     "#E91E63",
    "bridge":     "#9C27B0",
    "drop":       "#FF5722",
    "outro":      "#607D8B",
}

def _section_color(label: str) -> str:
    lower = label.lower()
    for key, color in _SECTION_COLORS.items():
        if key in lower:
            return color
    return "#78909C"


# ── Structure parsing ─────────────────────────────────────────────────────────

def _parse_lyrics_sections(lyrics: str) -> list[str]:
    """Extract ordered section labels from lyrics."""
    return [
        m.group(0).strip("[]")
        for m in re.finditer(r"\[[^\]]+\]", lyrics)
    ]


# ── Tempo map ─────────────────────────────────────────────────────────────────

def _build_tempo_map(bpm: float, total_bars: int, beats_per_bar: int = 4) -> TempoMap:
    beat_duration_s = 60.0 / bpm
    total_beats = float(total_bars * beats_per_bar)
    total_s = total_beats * beat_duration_s
    grid = [round(i * beat_duration_s, 4) for i in range(int(total_beats) + 1)]

    return TempoMap(
        bpm=round(bpm, 2),
        time_signature="4/4",
        beats_per_bar=beats_per_bar,
        total_bars=total_bars,
        total_beats=total_beats,
        total_duration_s=round(total_s, 2),
        beat_grid=grid,
    )


# ── Arrangement markers ───────────────────────────────────────────────────────

def _build_markers(
    sections: list[str],
    bpm: float,
    bars_per_section: int = 8,
    beats_per_bar: int = 4,
    section_energies: Optional[list[float]] = None,
) -> list[ArrangementMarker]:
    """
    Assign bar positions to each section label.
    Includes bar numbers, timestamps, energy level per section, and tempo.
    """
    beat_dur = 60.0 / bpm
    markers = []
    bar_cursor = 1

    for i, label in enumerate(sections):
        beat_pos = (bar_cursor - 1) * beats_per_bar
        time_s   = beat_pos * beat_dur

        # Energy level: use audio analysis section energies if available
        if section_energies and i < len(section_energies):
            energy = section_energies[i]
        else:
            # Heuristic: choruses louder, intros/outros quieter
            label_lower = label.lower()
            if "chorus" in label_lower or "hook" in label_lower or "drop" in label_lower:
                energy = 0.85
            elif "intro" in label_lower or "outro" in label_lower:
                energy = 0.40
            elif "bridge" in label_lower:
                energy = 0.70
            else:
                energy = 0.60

        markers.append(ArrangementMarker(
            label=label,
            bar_number=bar_cursor,
            beat_position=round(beat_pos, 2),
            time_s=round(time_s, 2),
            color=_section_color(label),
            energy_level=round(energy, 3),
            tempo_bpm=round(bpm, 2),
        ))
        bar_cursor += bars_per_section

    return markers


# ── MIDI generation ───────────────────────────────────────────────────────────

_KEY_ROOT_MIDI = {
    "C": 60, "C#": 61, "D": 62, "D#": 63, "E": 64,
    "F": 65, "F#": 66, "G": 67, "G#": 68, "A": 69, "A#": 70, "B": 71,
}

_MAJOR_CHORD_INTERVALS = [0, 4, 7]
_MINOR_CHORD_INTERVALS = [0, 3, 7]
_MAJOR_SCALE           = [0, 2, 4, 5, 7, 9, 11]
_MINOR_SCALE           = [0, 2, 3, 5, 7, 8, 10]


def _build_chord_midi(
    root: str,
    mode: str,
    chords: list[str],
    bpm: float,
    total_bars: int,
    markers: Optional[list["ArrangementMarker"]] = None,
) -> bytes:
    """
    Generate a chord MIDI file from harmonic analysis.

    Improvements:
    - Each chord lasts exactly one bar (4/4), duration = 4 - 0.1 beats (sustain)
    - Velocity varies by section: intro=55 (quiet), chorus=95 (loud), verse=72 (mid)
    - Section marker events added where midiutil supports it
    """
    try:
        from midiutil import MIDIFile

        mf = MIDIFile(1)
        mf.addTempo(0, 0, bpm)
        mf.addTimeSignature(0, 0, 4, 2, 24)

        root_midi = _KEY_ROOT_MIDI.get(root, 60)
        intervals = _MAJOR_CHORD_INTERVALS if mode == "major" else _MINOR_CHORD_INTERVALS
        beats_per_bar = 4
        sustain_beats = beats_per_bar - 0.1   # full bar minus tiny gap

        # Fallback chord progressions when none are provided
        # I–V–vi–IV (major) or i–VII–VI–VII (minor) — ubiquitous song progressions
        _MAJOR_FALLBACK = ["I", "V", "vi", "IV"]  # semitone offsets: 0,7,9,5
        _MAJOR_OFFSETS  = [0, 7, 9, 5]
        _MINOR_OFFSETS  = [0, 10, 8, 10]   # i–VII–VI–VII
        if not chords:
            offsets = _MAJOR_OFFSETS if mode == "major" else _MINOR_OFFSETS
            chord_name_map = {v: k for k, v in _KEY_ROOT_MIDI.items()}
            fallback: list[str] = []
            for offset in offsets:
                chord_root_midi = (root_midi + offset) % 12 + 60
                chord_root_name = chord_name_map.get(chord_root_midi, root)
                if mode == "major" and offset == 9:
                    quality = "min"   # vi chord in major key
                elif mode == "minor" and offset == 0:
                    quality = "min"   # i chord in minor key
                else:
                    quality = "maj"
                fallback.append(f"{chord_root_name}{quality}")
            chords = [fallback[i % len(fallback)] for i in range(total_bars)]
            print(f"[DAW] Fallback progression ({mode}): {fallback}", flush=True)

        # Build bar→velocity map from markers
        bar_velocity: dict[int, int] = {}
        if markers:
            for mk in markers:
                label_lower = mk.label.lower()
                if "intro" in label_lower or "outro" in label_lower:
                    vel = 55
                elif "chorus" in label_lower or "hook" in label_lower:
                    vel = 95
                elif "bridge" in label_lower or "drop" in label_lower:
                    vel = 85
                else:
                    vel = 72  # verse
                # Assign velocity to all bars in this section
                # (We don't know section length, so assign up to next marker)
                bar_velocity[mk.bar_number] = vel

        def _vel_for_bar(bar_1indexed: int) -> int:
            """Return velocity for a given 1-indexed bar number."""
            if not bar_velocity:
                return 75
            # Find the most recent marker that covers this bar
            applicable = [b for b in bar_velocity if b <= bar_1indexed]
            if applicable:
                return bar_velocity[max(applicable)]
            return 75

        for i, chord_label in enumerate(chords[:total_bars]):
            bar_1indexed = i + 1
            beat = i * beats_per_bar  # absolute beat position
            velocity = _vel_for_bar(bar_1indexed)

            # Parse chord root from label (e.g. "Cmaj" → C, "Cmin" → C)
            match = re.match(r"([A-G]#?)", chord_label)
            if match:
                chord_root = _KEY_ROOT_MIDI.get(match.group(1), root_midi)
            else:
                chord_root = root_midi

            # Parse chord quality from label suffix to use correct intervals
            chord_intervals = intervals  # default from session key mode
            label_lower = chord_label.lower()
            if 'dim' in label_lower:
                chord_intervals = [0, 3, 6]
            elif 'aug' in label_lower:
                chord_intervals = [0, 4, 8]
            elif 'maj7' in label_lower or 'major7' in label_lower:
                chord_intervals = [0, 4, 7, 11]
            elif 'min7' in label_lower or ('m7' in label_lower and 'maj' not in label_lower):
                chord_intervals = [0, 3, 7, 10]
            elif '7' in label_lower and 'maj' not in label_lower and 'dim' not in label_lower:
                chord_intervals = [0, 4, 7, 10]  # dominant 7
            elif 'sus4' in label_lower:
                chord_intervals = [0, 5, 7]
            elif 'sus2' in label_lower:
                chord_intervals = [0, 2, 7]
            elif 'min' in label_lower or (label_lower.endswith('m') and not label_lower.endswith('bm')):
                chord_intervals = [0, 3, 7]
            elif 'maj' in label_lower:
                chord_intervals = [0, 4, 7]
            # else: use session key default intervals (already set above)

            for iv in chord_intervals:
                mf.addNote(0, 0, chord_root + iv, beat, sustain_beats, velocity)

            # Add marker text if midiutil supports it
            try:
                mf.addText(0, beat, f"Chord {bar_1indexed}: {chord_label}")
            except Exception:
                pass  # older midiutil versions may not have addText

        buf = io.BytesIO()
        mf.writeFile(buf)
        return buf.getvalue()

    except Exception as exc:
        print(f"[DAW] Chord MIDI generation failed: {exc}", flush=True)
        return b""


def _build_melody_midi(
    root: str,
    mode: str,
    bpm: float,
    total_bars: int,
    darkness: float = 0.5,
) -> bytes:
    """
    Generate a melodic guide MIDI in the detected key.

    Improvements:
    - Stays within C4 (60) to C6 (84) — 2-octave range
    - Mix of quarter notes (1.0 beat) and eighth notes (0.5 beat) for variety
    - 4-bar phrase breathing: small gap (0.1 beat rest) at every 4th bar
    - Velocity variation: alternating strong/weak beats (natural accent)
    - Uses correct major/minor scale for the detected key/mode
    """
    try:
        from midiutil import MIDIFile

        mf = MIDIFile(1)
        mf.addTempo(0, 0, bpm)

        root_midi = _KEY_ROOT_MIDI.get(root, 60)
        scale = _MINOR_SCALE if (mode == "minor" or darkness > 0.6) else _MAJOR_SCALE

        # Build scale within C4 (60) to C6 (84) — 2 octaves
        # Start from root near C4 (middle C)
        start_midi = root_midi
        while start_midi < 60:
            start_midi += 12
        while start_midi > 67:   # keep within lower octave
            start_midi -= 12

        scale_notes: list[int] = []
        for octave_offset in (0, 12):
            for iv in scale:
                pitch = start_midi + octave_offset + iv
                if 60 <= pitch <= 84:
                    scale_notes.append(pitch)
        scale_notes = sorted(set(scale_notes))

        if not scale_notes:
            scale_notes = [60, 62, 64, 65, 67, 69, 71, 72]  # C major fallback

        # Note duration patterns: mix of quarter (1.0) and eighth (0.5)
        # 4/4 bar = 4 beats; fill with: Q Q E E Q pattern = 1+1+0.5+0.5+1 = 4 beats
        phrase_pattern = [1.0, 1.0, 0.5, 0.5, 1.0]   # sums to 4 beats per bar
        # Strong beat velocity (beat 1 and 3) = higher; weak = lower
        phrase_velocities = [80, 65, 70, 60, 75]

        beat = 0.0
        note_idx = 0
        ascending = True

        for bar in range(total_bars):
            # Phrase breathing gap at the end of every 4th bar
            is_phrase_end = (bar > 0 and (bar % 4) == 0)

            pattern_pos = 0
            bar_beat_offset = 0.0

            while bar_beat_offset < 4.0:
                dur = phrase_pattern[pattern_pos % len(phrase_pattern)]
                vel = phrase_velocities[pattern_pos % len(phrase_velocities)]

                # Leave a breath gap at phrase boundary (skip last note of phrase-end bar)
                is_last_beat_of_phrase_end = is_phrase_end and (bar_beat_offset + dur >= 4.0)
                if not is_last_beat_of_phrase_end:
                    pitch = scale_notes[note_idx % len(scale_notes)]
                    note_actual_dur = dur - 0.05  # avoid MIDI overlap
                    mf.addNote(0, 0, pitch, beat + bar_beat_offset, note_actual_dur, vel)

                bar_beat_offset += dur
                pattern_pos += 1

                # Advance note index with direction reversal for melodic contour
                if ascending:
                    note_idx += 1
                    if note_idx >= len(scale_notes) - 1:
                        ascending = False
                else:
                    note_idx -= 1
                    if note_idx <= 0:
                        ascending = True
                note_idx = max(0, min(note_idx, len(scale_notes) - 1))

            beat += 4.0  # always advance by full bar

        buf = io.BytesIO()
        mf.writeFile(buf)
        return buf.getvalue()

    except Exception as exc:
        print(f"[DAW] Melody MIDI generation failed: {exc}", flush=True)
        return b""


# ── Session builder ───────────────────────────────────────────────────────────

@dataclass
class DAWSessionRequest:
    title: str
    artist: str
    theme: str
    lyrics: str
    language: str = "English"
    output_mode: str = "producer"
    bpm: float = 120.0
    key: str = "C major"
    bars: int = 32
    darkness: float = 0.5
    chords: list[str] = field(default_factory=list)
    stem_paths: dict = field(default_factory=dict)   # {"vocals": path, ...}
    audio_analysis: Optional[object] = None
    genre_data: Optional[dict] = None           # genre profile or blend data
    cadence_data: Optional[dict] = None         # cadence profile
    audio_analysis_data: Optional[dict] = None  # BPM/key/chords from audio analysis


def build_daw_session(req: DAWSessionRequest) -> DAWSession:
    """Build a complete DAW session object from generation results."""
    import uuid

    # Parse key
    key_parts = req.key.split()
    root = key_parts[0] if key_parts else "C"
    mode = key_parts[1] if len(key_parts) > 1 else "major"

    # Estimate bars per section from lyrics structure
    sections = _parse_lyrics_sections(req.lyrics)
    n_sections = max(1, len(sections))
    bars_per_section = max(4, req.bars // n_sections)
    total_bars = bars_per_section * n_sections

    tempo = _build_tempo_map(req.bpm, total_bars)

    # Pass section energies from audio analysis if available
    audio_section_energies: Optional[list[float]] = None
    if req.audio_analysis and hasattr(req.audio_analysis, "energy"):
        audio_section_energies = req.audio_analysis.energy.section_energies or None

    markers = _build_markers(sections, req.bpm, bars_per_section, section_energies=audio_section_energies)

    # MIDI — pass markers for velocity variation in chord MIDI
    chord_midi = _build_chord_midi(root, mode, req.chords, req.bpm, total_bars, markers)
    melody_midi = _build_melody_midi(root, mode, req.bpm, total_bars, req.darkness)

    # Stem file mapping with professional naming
    stem_map = req.stem_paths or {}
    stems = StemFiles(
        vocals=stem_map.get("vocals"),
        drums=stem_map.get("drums"),
        bass=stem_map.get("bass"),
        other=stem_map.get("other"),
        mix=stem_map.get("mix"),
    )

    project = TrackMetadata(
        title=req.title,
        artist=req.artist,
        theme=req.theme,
        key=req.key,
        bpm=round(req.bpm, 2),
        lyrics=req.lyrics,
        language=req.language,
        output_mode=req.output_mode,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    session_id = str(uuid.uuid4())[:12]

    return DAWSession(
        project=project,
        tempo_map=tempo,
        markers=markers,
        stems=stems,
        chord_midi_bytes=chord_midi if chord_midi else None,
        melody_midi_bytes=melody_midi if melody_midi else None,
        session_id=session_id,
    )


# ── ZIP export ────────────────────────────────────────────────────────────────

def export_session_zip(
    session: DAWSession,
    stem_bytes: Optional[dict] = None,    # {"vocals": bytes, "drums": bytes, ...}
    voice_bytes: Optional[bytes] = None,
    music_bytes: Optional[bytes] = None,
    mix_bytes: Optional[bytes] = None,
    genre_data: Optional[dict] = None,
    cadence_data: Optional[dict] = None,
    audio_analysis_data: Optional[dict] = None,
) -> bytes:
    """
    Package the full DAW session into a ZIP file.
    Follows professional stem naming convention:
      01_Vocals.mp3, 02_Drums.mp3, 03_Bass.mp3, 04_Music.mp3
    """
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        session_name = re.sub(r"[^\w\-]", "_", session.project.title)[:32]

        # project.json
        zf.writestr(
            f"{session_name}/project.json",
            json.dumps(session.to_project_json(), indent=2, ensure_ascii=False),
        )

        # ── Intelligence metadata files ──────────────────────────────────────
        if genre_data:
            zf.writestr(
                f"{session_name}/intelligence/genre_metadata.json",
                json.dumps(genre_data, indent=2, ensure_ascii=False),
            )
        if cadence_data:
            zf.writestr(
                f"{session_name}/intelligence/cadence_metadata.json",
                json.dumps(cadence_data, indent=2, ensure_ascii=False),
            )
        if audio_analysis_data:
            zf.writestr(
                f"{session_name}/intelligence/audio_analysis.json",
                json.dumps(audio_analysis_data, indent=2, ensure_ascii=False),
            )

        # tempo_map.json
        zf.writestr(
            f"{session_name}/tempo_map.json",
            json.dumps(asdict(session.tempo_map), indent=2),
        )

        # arrangement_markers.json (legacy name, kept for compatibility)
        zf.writestr(
            f"{session_name}/arrangement_markers.json",
            json.dumps([asdict(m) for m in session.markers], indent=2),
        )

        # arrangement.json — full arrangement with bar numbers, timestamps, energy, tempo
        arrangement_data = {
            "version": "5.1",
            "bpm": session.project.bpm,
            "key": session.project.key,
            "total_bars": session.tempo_map.total_bars,
            "total_duration_s": session.tempo_map.total_duration_s,
            "sections": [
                {
                    "label": m.label,
                    "bar_number": m.bar_number,
                    "timestamp_s": m.time_s,
                    "beat_position": m.beat_position,
                    "energy_level": m.energy_level,
                    "tempo_bpm": m.tempo_bpm,
                    "color": m.color,
                }
                for m in session.markers
            ],
        }
        zf.writestr(
            f"{session_name}/arrangement.json",
            json.dumps(arrangement_data, indent=2),
        )

        # lyrics.txt
        zf.writestr(
            f"{session_name}/lyrics.txt",
            session.project.lyrics,
        )

        # MIDI files — professional naming convention
        if session.chord_midi_bytes:
            zf.writestr(f"{session_name}/midi/01_Chords.mid", session.chord_midi_bytes)
        if session.melody_midi_bytes:
            zf.writestr(f"{session_name}/midi/02_Melody.mid", session.melody_midi_bytes)

        # Stems — professional naming
        _STEM_NAMES = {
            "vocals": "01_Vocals.mp3",
            "drums":  "02_Drums.mp3",
            "bass":   "03_Bass.mp3",
            "other":  "04_Music.mp3",
        }

        if stem_bytes:
            for key, data in stem_bytes.items():
                if data:
                    fname = _STEM_NAMES.get(key, f"{key}.mp3")
                    zf.writestr(f"{session_name}/stems/{fname}", data)

        if voice_bytes:
            zf.writestr(f"{session_name}/stems/00_VoiceGuide.mp3", voice_bytes)

        if music_bytes:
            zf.writestr(f"{session_name}/stems/05_FullSong.mp3", music_bytes)

        if mix_bytes:
            zf.writestr(f"{session_name}/stems/06_Mix.mp3", mix_bytes)

        # README
        readme = _build_readme(session)
        zf.writestr(f"{session_name}/README.txt", readme)

    buf.seek(0)
    return buf.read()


def _build_readme(session: DAWSession) -> str:
    m = session.markers
    marker_lines = "\n".join(
        f"  Bar {mk.bar_number:3d}  {mk.time_s:6.1f}s  [{mk.label}]"
        for mk in m
    ) if m else "  (no markers)"

    return f"""SonicFlow Studio v5 — DAW Session Export
==========================================

Track:    {session.project.title}
Artist:   {session.project.artist}
Theme:    {session.project.theme}
Key:      {session.project.key}
BPM:      {session.project.bpm}
Language: {session.project.language}
Session:  {session.session_id}
Exported: {session.project.generated_at}

ARRANGEMENT
-----------
{marker_lines}

STEM FILES
----------
  01_Vocals.mp3   — Lead vocals / vocal guide
  02_Drums.mp3    — Drum track
  03_Bass.mp3     — Bass track
  04_Music.mp3    — Melody / harmony layer
  05_FullSong.mp3 — Complete generated song (if available)
  06_Mix.mp3      — Mixed master (if available)

MIDI FILES
----------
  midi/01_Chords.mid  — Chord changes (velocity-varied by section)
  midi/02_Melody.mid  — Melodic guide in the detected key (C4-C6 range)

ARRANGEMENT FILES
-----------------
  arrangement.json          — Full arrangement with bar numbers, timestamps, energy
  arrangement_markers.json  — Legacy format (same data)
  tempo_map.json            — Beat grid and timing reference

IMPORT TIPS
-----------
• Set your DAW project tempo to {session.project.bpm} BPM before importing stems
• Use arrangement.json to set session markers automatically
• All stems are time-aligned from bar 1, beat 1
• Import midi/01_Chords.mid to a MIDI instrument track for harmonic reference
• Import midi/02_Melody.mid as a melodic phrase reference

Generated by SonicFlow Studio — AI Remix Production System
"""
