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
) -> list[ArrangementMarker]:
    """Assign bar positions to each section label."""
    beat_dur = 60.0 / bpm
    markers = []
    bar_cursor = 1

    for label in sections:
        beat_pos = (bar_cursor - 1) * beats_per_bar
        time_s   = beat_pos * beat_dur
        markers.append(ArrangementMarker(
            label=label,
            bar_number=bar_cursor,
            beat_position=round(beat_pos, 2),
            time_s=round(time_s, 2),
            color=_section_color(label),
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
) -> bytes:
    """Generate a chord MIDI file from harmonic analysis."""
    try:
        from midiutil import MIDIFile

        mf = MIDIFile(1)
        mf.addTempo(0, 0, bpm)
        mf.addTimeSignature(0, 0, 4, 2, 24)

        root_midi = _KEY_ROOT_MIDI.get(root, 60)
        intervals = _MAJOR_CHORD_INTERVALS if mode == "major" else _MINOR_CHORD_INTERVALS
        beats_per_bar = 4
        bar = 0

        for i, chord_label in enumerate(chords[:total_bars]):
            beat = bar * beats_per_bar
            # Parse chord root from label (e.g. "Cmaj" → C)
            match = re.match(r"([A-G]#?)", chord_label)
            if match:
                chord_root = _KEY_ROOT_MIDI.get(match.group(1), root_midi)
            else:
                chord_root = root_midi

            for iv in intervals:
                mf.addNote(0, 0, chord_root + iv, beat, beats_per_bar - 0.1, 75)

            bar += 1

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
    """Generate a simple melodic guide MIDI in the detected key."""
    try:
        from midiutil import MIDIFile

        mf = MIDIFile(1)
        mf.addTempo(0, 0, bpm)

        root_midi = _KEY_ROOT_MIDI.get(root, 60)
        scale = _MINOR_SCALE if (mode == "minor" or darkness > 0.6) else _MAJOR_SCALE
        scale_notes = [root_midi + iv for iv in scale] + [root_midi + 12 + iv for iv in scale]

        beat = 0.0
        note_dur = 0.5   # eighth notes
        note_idx = 0

        for bar in range(total_bars):
            for _ in range(8):   # 8 eighth notes per bar
                pitch = scale_notes[note_idx % len(scale_notes)]
                mf.addNote(0, 0, pitch, beat, note_dur - 0.05, 60)
                beat += note_dur
                # Step through scale, direction reversal for variation
                if note_idx % 8 < 4:
                    note_idx += 1
                else:
                    note_idx -= 1
                note_idx = max(0, note_idx)

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
    markers = _build_markers(sections, req.bpm, bars_per_section)

    # MIDI
    chord_midi = _build_chord_midi(root, mode, req.chords, req.bpm, total_bars)
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

        # tempo_map.json
        zf.writestr(
            f"{session_name}/tempo_map.json",
            json.dumps(asdict(session.tempo_map), indent=2),
        )

        # arrangement_markers.json
        zf.writestr(
            f"{session_name}/arrangement_markers.json",
            json.dumps([asdict(m) for m in session.markers], indent=2),
        )

        # lyrics.txt
        zf.writestr(
            f"{session_name}/lyrics.txt",
            session.project.lyrics,
        )

        # MIDI files
        if session.chord_midi_bytes:
            zf.writestr(f"{session_name}/midi/chord_progression.mid", session.chord_midi_bytes)
        if session.melody_midi_bytes:
            zf.writestr(f"{session_name}/midi/melody_guide.mid", session.melody_midi_bytes)

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
  midi/chord_progression.mid  — Chord changes for this session
  midi/melody_guide.mid        — Melodic guide in the detected key

IMPORT TIPS
-----------
• Set your DAW project tempo to {session.project.bpm} BPM before importing stems
• Use arrangement_markers.json to set session markers automatically
• All stems are time-aligned from bar 1, beat 1
• Import chord_progression.mid to a MIDI instrument track for harmonic reference

Generated by SonicFlow Studio — AI Remix Production System
"""
