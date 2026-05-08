"""
services/audio_analysis.py — SonicFlow Real Audio Intelligence Engine

Provides genuine audio analysis that replaces the former filename-based hinting.
All analysis is done via librosa (BPM, key, energy, cadence, structure).
Results feed into prompt construction, Suno prompt generation, and DAW export.

Public API:
    analyze_audio(audio_bytes, filename) -> AudioAnalysis
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

# ── Types ─────────────────────────────────────────────────────────────────────

@dataclass
class BeatInfo:
    bpm: float
    bpm_confidence: float          # 0-1
    beat_positions: list[float]    # seconds
    tempo_variation: str           # "steady" | "variable" | "rubato"
    beat_grid_ms: list[int]        # beat positions in milliseconds

@dataclass
class HarmonicInfo:
    key: str                       # e.g. "C major"
    root: str                      # e.g. "C"
    mode: str                      # "major" | "minor"
    chords: list[str]              # detected chord labels per segment
    key_confidence: float          # 0-1

@dataclass
class EnergyInfo:
    rms_mean: float                # average RMS
    rms_std: float                 # variation
    dynamic_range: float           # dB
    intensity: str                 # "low" | "medium" | "high" | "very high"
    section_energies: list[float]  # normalised energy per segment

@dataclass
class CadenceInfo:
    onset_density: float           # onsets per second
    syllable_density_estimate: float  # estimated syllables/second from onsets
    avg_phrase_gap_s: float        # mean gap between phrase bursts
    pause_pattern: str             # "dense" | "moderate" | "sparse"
    stress_pattern: str            # "regular" | "syncopated" | "free"
    flow_descriptors: list[str]    # human-readable cadence descriptors

@dataclass
class StructureInfo:
    segments: list[dict]           # [{label, start_s, end_s, energy}]
    detected_sections: list[str]   # ["intro","verse","chorus","bridge","outro"]
    total_duration_s: float

@dataclass
class AudioAnalysis:
    beat: BeatInfo
    harmonic: HarmonicInfo
    energy: EnergyInfo
    cadence: CadenceInfo
    structure: StructureInfo
    prompt_hint: str               # rich natural-language hint for LLM prompts
    suno_tags: str                 # structured tags for Suno prompt composer
    analysis_latency_ms: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_audio(audio_bytes: bytes, filename: str = "track.mp3") -> AudioAnalysis:
    """
    Fully analyse an audio file from raw bytes.
    Falls back gracefully if librosa is unavailable or analysis fails.
    """
    t0 = time.time()
    try:
        import librosa
        import soundfile  # noqa: F401 — ensure soundfile backend is present

        y, sr = _load_audio(audio_bytes, filename)
        if y is None:
            return _fallback_analysis(filename, "Failed to decode audio", t0)

        beat     = _analyse_beat(y, sr)
        harmonic = _analyse_harmonic(y, sr)
        energy   = _analyse_energy(y, sr)
        cadence  = _analyse_cadence(y, sr)
        structure = _analyse_structure(y, sr)

        hint = _build_prompt_hint(beat, harmonic, energy, cadence, structure)
        suno = _build_suno_tags(beat, harmonic, energy, cadence)
        ms   = int((time.time() - t0) * 1000)

        print(f"[AUDIO] Analysis complete in {ms}ms — {beat.bpm:.1f} BPM, {harmonic.key}, {energy.intensity} energy", flush=True)

        return AudioAnalysis(
            beat=beat, harmonic=harmonic, energy=energy,
            cadence=cadence, structure=structure,
            prompt_hint=hint, suno_tags=suno,
            analysis_latency_ms=ms,
        )

    except ImportError:
        return _fallback_analysis(filename, "librosa not available", t0)
    except Exception as exc:
        print(f"[AUDIO] Analysis error: {exc}", flush=True)
        return _fallback_analysis(filename, str(exc), t0)


# ── Audio loading ─────────────────────────────────────────────────────────────

def _load_audio(audio_bytes: bytes, filename: str):
    """Load audio bytes into a mono float32 numpy array at 22050 Hz."""
    import librosa

    buf = io.BytesIO(audio_bytes)
    try:
        y, sr = librosa.load(buf, sr=22050, mono=True, duration=180)
        return y, sr
    except Exception:
        # Try via soundfile path
        try:
            buf.seek(0)
            import soundfile as sf
            y_sf, sr_sf = sf.read(buf, dtype="float32", always_2d=False)
            if y_sf.ndim > 1:
                y_sf = y_sf.mean(axis=1)
            y_resampled = librosa.resample(y_sf, orig_sr=sr_sf, target_sr=22050)
            return y_resampled, 22050
        except Exception as e:
            print(f"[AUDIO] Load failed: {e}", flush=True)
            return None, None


# ── Beat & BPM ────────────────────────────────────────────────────────────────

def _analyse_beat(y, sr) -> BeatInfo:
    import librosa

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    beat_ms    = [int(t * 1000) for t in beat_times]

    # Tempo variation: measure std of inter-beat intervals
    if len(beat_times) > 4:
        ibi = np.diff(beat_times)
        cv  = float(np.std(ibi) / (np.mean(ibi) + 1e-6))
        if cv < 0.05:
            variation = "steady"
        elif cv < 0.15:
            variation = "variable"
        else:
            variation = "rubato"
    else:
        variation = "steady"

    confidence = min(1.0, float(len(beat_times)) / 32.0)

    return BeatInfo(
        bpm=round(bpm, 1),
        bpm_confidence=round(confidence, 2),
        beat_positions=beat_times[:64],
        tempo_variation=variation,
        beat_grid_ms=beat_ms[:64],
    )


# ── Harmonic / Key / Chords ───────────────────────────────────────────────────

_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl–Schmuckler key-finding profiles
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

def _ks_key(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    """Krumhansl-Schmuckler key finding. Returns (root, mode, confidence)."""
    best_score = -np.inf
    best_root  = "C"
    best_mode  = "major"

    for i, pc in enumerate(_PITCH_CLASSES):
        rotated = np.roll(chroma_mean, -i)
        major_r = float(np.corrcoef(rotated, _KS_MAJOR)[0, 1])
        minor_r = float(np.corrcoef(rotated, _KS_MINOR)[0, 1])
        if major_r > best_score:
            best_score = major_r; best_root = pc; best_mode = "major"
        if minor_r > best_score:
            best_score = minor_r; best_root = pc; best_mode = "minor"

    confidence = min(1.0, max(0.0, (best_score + 1) / 2))
    return best_root, best_mode, round(confidence, 2)


_CHORD_TEMPLATES = {
    "maj":  np.array([1,0,0,0,1,0,0,1,0,0,0,0], dtype=float),
    "min":  np.array([1,0,0,1,0,0,0,1,0,0,0,0], dtype=float),
    "7":    np.array([1,0,0,0,1,0,0,1,0,0,1,0], dtype=float),
    "min7": np.array([1,0,0,1,0,0,0,1,0,0,1,0], dtype=float),
}

def _detect_chords(chroma: np.ndarray, n_segments: int = 8) -> list[str]:
    """Simple template-matching chord detection over n_segments."""
    chords = []
    seg_size = chroma.shape[1] // n_segments
    if seg_size < 1:
        return []

    for i in range(n_segments):
        seg = chroma[:, i * seg_size: (i + 1) * seg_size].mean(axis=1)
        best_chord = "N"
        best_score = -np.inf
        for pc_idx, pc in enumerate(_PITCH_CLASSES):
            rotated = np.roll(seg, -pc_idx)
            for suffix, template in _CHORD_TEMPLATES.items():
                score = float(np.dot(rotated, template))
                if score > best_score:
                    best_score = score
                    best_chord = f"{pc}{suffix}"
        chords.append(best_chord)
    return chords


def _analyse_harmonic(y, sr) -> HarmonicInfo:
    import librosa

    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=12, n_fft=4096)
    chroma_mean = chroma.mean(axis=1)

    root, mode, confidence = _ks_key(chroma_mean)
    key_label = f"{root} {mode}"

    chords = _detect_chords(chroma)

    return HarmonicInfo(
        key=key_label,
        root=root,
        mode=mode,
        chords=chords,
        key_confidence=confidence,
    )


# ── Energy ────────────────────────────────────────────────────────────────────

def _analyse_energy(y, sr) -> EnergyInfo:
    import librosa

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    rms_mean = float(rms.mean())
    rms_std  = float(rms.std())

    # Dynamic range in dB (95th - 5th percentile)
    db_rms = librosa.amplitude_to_db(rms + 1e-9)
    dr = float(np.percentile(db_rms, 95) - np.percentile(db_rms, 5))

    # Intensity tier
    if rms_mean < 0.02:
        intensity = "low"
    elif rms_mean < 0.06:
        intensity = "medium"
    elif rms_mean < 0.12:
        intensity = "high"
    else:
        intensity = "very high"

    # Section energies (8 equal windows)
    n = 8
    seg = len(rms) // n
    section_energies = [float(rms[i*seg:(i+1)*seg].mean()) for i in range(n)] if seg > 0 else []
    max_e = max(section_energies) if section_energies else 1.0
    section_energies = [round(e / max_e, 3) for e in section_energies]

    return EnergyInfo(
        rms_mean=round(rms_mean, 4),
        rms_std=round(rms_std, 4),
        dynamic_range=round(dr, 1),
        intensity=intensity,
        section_energies=section_energies,
    )


# ── Cadence ───────────────────────────────────────────────────────────────────

def _analyse_cadence(y, sr) -> CadenceInfo:
    import librosa

    # Onset detection
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames", backtrack=True)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)
    duration     = float(len(y) / sr)

    onset_density = len(onset_times) / max(duration, 1.0)
    syllable_est  = onset_density * 0.6  # rough: ~60% of onsets are syllable boundaries

    # Phrase gap: measure gaps between dense onset clusters
    if len(onset_times) > 4:
        ioi = np.diff(onset_times)
        gap_threshold = np.percentile(ioi, 80)
        phrase_gaps = ioi[ioi > gap_threshold]
        avg_gap = float(phrase_gaps.mean()) if len(phrase_gaps) > 0 else 0.5
    else:
        avg_gap = 0.5

    # Pause pattern
    if onset_density > 6:
        pause_pattern = "dense"
    elif onset_density > 3:
        pause_pattern = "moderate"
    else:
        pause_pattern = "sparse"

    # Stress pattern: check regularity of inter-onset intervals
    if len(onset_times) > 8:
        ioi_all = np.diff(onset_times)
        cv = float(np.std(ioi_all) / (np.mean(ioi_all) + 1e-6))
        if cv < 0.2:
            stress = "regular"
        elif cv < 0.45:
            stress = "syncopated"
        else:
            stress = "free"
    else:
        stress = "regular"

    # Human-readable flow descriptors
    descriptors = []
    if onset_density > 7:
        descriptors.append("rapid-fire delivery")
    elif onset_density > 4:
        descriptors.append("mid-tempo flow")
    else:
        descriptors.append("slow deliberate phrasing")

    if stress == "syncopated":
        descriptors.append("syncopated rhythm")
    elif stress == "regular":
        descriptors.append("on-beat cadence")

    if avg_gap > 1.2:
        descriptors.append("breath pauses between phrases")
    elif avg_gap < 0.4:
        descriptors.append("continuous flow")

    return CadenceInfo(
        onset_density=round(onset_density, 2),
        syllable_density_estimate=round(syllable_est, 2),
        avg_phrase_gap_s=round(avg_gap, 3),
        pause_pattern=pause_pattern,
        stress_pattern=stress,
        flow_descriptors=descriptors,
    )


# ── Structural Segmentation ───────────────────────────────────────────────────

def _analyse_structure(y, sr) -> StructureInfo:
    import librosa

    duration = float(len(y) / sr)

    # MFCC-based self-similarity for novelty
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    # Segment into 8 equal sections and label by energy
    rms = librosa.feature.rms(y=y)[0]
    n_seg = min(8, max(2, int(duration / 15)))  # ~15s segments
    seg_dur = duration / n_seg

    rms_frame_dur = len(rms) / duration
    segments = []
    for i in range(n_seg):
        start_s = i * seg_dur
        end_s   = (i + 1) * seg_dur
        f_start = int(i * len(rms) / n_seg)
        f_end   = int((i + 1) * len(rms) / n_seg)
        seg_energy = float(rms[f_start:f_end].mean()) if f_end > f_start else 0.0

        segments.append({
            "label":    f"Section {i+1}",
            "start_s":  round(start_s, 2),
            "end_s":    round(end_s, 2),
            "energy":   round(seg_energy, 4),
        })

    # Heuristic section labeling
    energies = [s["energy"] for s in segments]
    if not energies:
        detected = ["verse", "chorus"]
    else:
        med_e  = np.median(energies)
        detected = []
        for i, s in enumerate(segments):
            if i == 0:
                label = "intro"
            elif i == len(segments) - 1:
                label = "outro"
            elif s["energy"] > med_e * 1.25:
                label = "chorus"
            elif s["energy"] < med_e * 0.75:
                label = "bridge"
            else:
                label = "verse"
            s["label"] = label
            if label not in detected:
                detected.append(label)

    return StructureInfo(
        segments=segments,
        detected_sections=detected,
        total_duration_s=round(duration, 2),
    )


# ── Prompt + Suno hint builders ───────────────────────────────────────────────

def _build_prompt_hint(
    beat: BeatInfo,
    harmonic: HarmonicInfo,
    energy: EnergyInfo,
    cadence: CadenceInfo,
    structure: StructureInfo,
) -> str:
    """Build a rich natural-language hint for LLM prompt injection."""
    flow = ", ".join(cadence.flow_descriptors) if cadence.flow_descriptors else "moderate flow"
    sections = ", ".join(structure.detected_sections) if structure.detected_sections else "verse, chorus"

    return (
        f"The uploaded instrumental is in {harmonic.key} at {beat.bpm:.0f} BPM "
        f"({beat.tempo_variation} tempo). "
        f"Energy level is {energy.intensity} with {energy.dynamic_range:.0f}dB dynamic range. "
        f"Detected structure: {sections}. "
        f"Vocal delivery style implied: {flow}. "
        f"Lyric density target: ~{cadence.syllable_density_estimate:.1f} syllables/second. "
        f"Write lyrics that feel WRITTEN FOR this specific instrumental — "
        f"match the tempo feel, harmonic mood ({harmonic.mode}), and energy arc."
    )


def _build_suno_tags(
    beat: BeatInfo,
    harmonic: HarmonicInfo,
    energy: EnergyInfo,
    cadence: CadenceInfo,
) -> str:
    """Build structured Suno prompt tags from audio analysis."""
    tags = [
        f"{beat.bpm:.0f}bpm",
        harmonic.key.lower(),
        harmonic.mode,
    ]

    if energy.intensity == "very high":
        tags += ["energetic", "powerful"]
    elif energy.intensity == "high":
        tags += ["driving", "upbeat"]
    elif energy.intensity == "low":
        tags += ["atmospheric", "mellow"]
    else:
        tags += ["balanced", "mid-energy"]

    if cadence.stress_pattern == "syncopated":
        tags.append("syncopated groove")
    if cadence.pause_pattern == "dense":
        tags.append("rapid delivery")

    return ", ".join(tags)


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_analysis(filename: str, error: str, t0: float) -> AudioAnalysis:
    """Return a safe default analysis when real analysis fails."""
    print(f"[AUDIO] Using fallback analysis ({error})", flush=True)
    ms = int((time.time() - t0) * 1000)

    # Infer minimal hints from filename
    name = filename.lower()
    bpm_hint = 128.0
    key_hint = "C major"
    if any(w in name for w in ("slow", "ballad", "soft", "chill")):
        bpm_hint = 75.0
        intensity = "low"
    elif any(w in name for w in ("trap", "drill", "bounce")):
        bpm_hint = 140.0
        intensity = "high"
    else:
        intensity = "medium"

    beat = BeatInfo(bpm=bpm_hint, bpm_confidence=0.0, beat_positions=[], tempo_variation="steady", beat_grid_ms=[])
    harmonic = HarmonicInfo(key=key_hint, root="C", mode="major", chords=[], key_confidence=0.0)
    energy = EnergyInfo(rms_mean=0.05, rms_std=0.01, dynamic_range=12.0, intensity=intensity, section_energies=[])
    cadence = CadenceInfo(onset_density=4.0, syllable_density_estimate=2.5, avg_phrase_gap_s=0.5, pause_pattern="moderate", stress_pattern="regular", flow_descriptors=["moderate flow"])
    structure = StructureInfo(segments=[], detected_sections=["intro", "verse", "chorus", "outro"], total_duration_s=0.0)

    hint = f"Instrumental: {filename}. Target {bpm_hint:.0f} BPM feel, {key_hint} mood, {intensity} energy."
    suno = f"{bpm_hint:.0f}bpm, {key_hint.lower()}, {intensity}"

    return AudioAnalysis(
        beat=beat, harmonic=harmonic, energy=energy,
        cadence=cadence, structure=structure,
        prompt_hint=hint, suno_tags=suno,
        analysis_latency_ms=ms, error=error,
    )
