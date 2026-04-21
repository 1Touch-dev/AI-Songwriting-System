"""
api/main.py — SonicFlow Studio API v5.0

Endpoints:
  POST /login                → { token }
  POST /generate             → GenerateResult (multipart: JSON fields + optional instrumental file)
  GET  /artists/search       → { results }
  GET  /global-artists       → { artists }
  POST /chorus/extract       → { chorus, found }
  POST /stems/extract        → { job_id, status }
  GET  /stems/{job_id}       → { status, stems }
  GET  /projects             → { projects }
  POST /projects             → Project
  DELETE /projects/{id}      → { deleted }
  GET  /health               → { status }
"""
import base64
import json
import os
import re
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

PROJECTS_FILE  = ROOT / "data" / "projects.json"
STEMS_DIR      = ROOT / "data" / "stems"
UPLOADS_DIR    = ROOT / "data" / "uploads"
AUDIO_DIR      = ROOT / "data" / "audio"
GLOBAL_ARTISTS = ROOT / "data" / "global_artists.json"
for d in (PROJECTS_FILE.parent, STEMS_DIR, UPLOADS_DIR, AUDIO_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _load_projects() -> list[dict]:
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text())
    except Exception:
        return []

def _save_projects(projects: list[dict]) -> None:
    PROJECTS_FILE.write_text(json.dumps(projects, ensure_ascii=False, indent=2))


from rag.pipeline import SongwritingPipeline, STRUCTURES
from utils.genius_utils import search_genius_artists
from services.stem_extractor import extract_stems_async, get_job, cleanup_old_jobs
from services.audio_mixer import mix_vocal_with_instrumental_bytes, is_ffmpeg_available

app = FastAPI(title="SonicFlow Studio API", version="5.0.0")

app.mount("/static/stems", StaticFiles(directory=str(STEMS_DIR)), name="stems")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline: Optional[SongwritingPipeline] = None

def get_pipeline() -> SongwritingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SongwritingPipeline()
    return _pipeline


# ── Auth ──────────────────────────────────────────────────────────────────
STUDIO_USERS  = {"admin@studio.com": "admins"}
SESSION_TOKEN = "sonicflow-studio-session-v3"

def verify_token(authorization: str = Header(default="")) -> str:
    token = authorization.replace("Bearer ", "").strip()
    if token != SESSION_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return token


# ── Schemas ───────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str

class LyricVariant(BaseModel):
    lyrics: str
    style_fidelity: float

class GenerateResponse(BaseModel):
    lyrics: str
    theme: str
    versions: list[LyricVariant]
    retrieval_quality: float
    latency_ms: float
    retrieval_diagnostics: dict
    analysis: Optional[dict]
    voice_audio_b64: Optional[str]
    music_audio_b64: Optional[str]
    mixed_audio_b64: Optional[str]
    voice_error: Optional[str]
    music_error: Optional[str]
    mix_error: Optional[str]
    locked_chorus: Optional[str]
    instrumental_hint: Optional[str]
    timestamp: str

class ChorusExtractRequest(BaseModel):
    lyrics: str

class Project(BaseModel):
    id: str
    title: str
    theme: str
    artist: str
    lyrics: str
    timestamp: str
    duration_s: float
    has_voice: bool
    has_music: bool
    has_mix: bool = False
    voice_url: Optional[str] = None
    music_url: Optional[str] = None
    mix_url: Optional[str] = None
    # Generation inputs
    language: Optional[str] = "English"
    bars: Optional[int] = None
    structure: Optional[str] = None
    gen_mode: Optional[str] = None
    perspective_mode: Optional[str] = None
    gender: Optional[str] = None
    style_strength: Optional[float] = None
    temperature: Optional[float] = None
    chorus_strict: Optional[bool] = None
    producer_mode: Optional[bool] = None
    section_mode: Optional[str] = None
    ref_lyrics: Optional[str] = None
    analysis: Optional[dict] = None

class SaveProjectRequest(BaseModel):
    title: str
    theme: str
    artist: str
    lyrics: str
    has_voice: bool
    has_music: bool
    has_mix: bool = False
    duration_s: float = 0.0
    voice_audio_b64: Optional[str] = None
    music_audio_b64: Optional[str] = None
    mixed_audio_b64: Optional[str] = None
    # Generation inputs
    language: Optional[str] = "English"
    bars: Optional[int] = None
    structure: Optional[str] = None
    gen_mode: Optional[str] = None
    perspective_mode: Optional[str] = None
    gender: Optional[str] = None
    style_strength: Optional[float] = None
    temperature: Optional[float] = None
    chorus_strict: Optional[bool] = None
    producer_mode: Optional[bool] = None
    section_mode: Optional[str] = None
    ref_lyrics: Optional[str] = None
    analysis: Optional[dict] = None


# ── Chorus extraction helper ──────────────────────────────────────────────
def _extract_chorus_from_lyrics(lyrics: str) -> str:
    """
    1. Regex — labeled sections ([Chorus], [Hook], [Refrain])
    2. GPT-4o-mini fallback for unlabeled lyrics
    """
    from openai import OpenAI

    for pattern in [
        r'\[chorus\](.*?)(?=\n\[|\Z)',
        r'\[hook\](.*?)(?=\n\[|\Z)',
        r'\[refr[ae]in\](.*?)(?=\n\[|\Z)',
    ]:
        m = re.search(pattern, lyrics, re.I | re.DOTALL)
        if m:
            return m.group(1).strip()

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Extract ONLY the chorus or most-repeated hook section from these lyrics. "
                    "Return just the lines with no labels or commentary.\n\n"
                    f"Lyrics:\n{lyrics[:2000]}"
                ),
            }],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[API] Chorus LLM error: {e}")
        return ""


# ── Instrumental analysis helper ──────────────────────────────────────────
def _analyze_instrumental(file_bytes: bytes, filename: str) -> str:
    """
    Return a production-grade prompt hint for the uploaded instrumental.
    Estimates duration and builds a specific lyric-alignment instruction.
    """
    ext      = Path(filename).suffix.lower()
    size_mb  = len(file_bytes) / (1024 * 1024)
    name_hint = Path(filename).stem.replace('_', ' ').replace('-', ' ')

    # Bitrate-based duration estimate
    bitrate_kbps = 128 if ext == ".mp3" else 1411  # WAV ~1411kbps (44.1k/16bit/stereo)
    est_seconds  = (size_mb * 8 * 1024) / bitrate_kbps
    est_minutes  = est_seconds / 60

    # Rough energy / tempo heuristic from filename keywords
    fname_lower = filename.lower()
    if any(w in fname_lower for w in ("hard", "heavy", "trap", "drill", "metal", "banger")):
        energy_hint = "high-energy, aggressive track"
        tempo_hint  = "fast pacing, short punchy lines (4–6 words), driving rhythm"
    elif any(w in fname_lower for w in ("slow", "sad", "chill", "lo-fi", "lofi", "ballad", "soft")):
        energy_hint = "slow, emotional track"
        tempo_hint  = "slow pacing, longer lines (6–9 words), drawn-out phrasing"
    elif any(w in fname_lower for w in ("mid", "groove", "r&b", "rnb", "smooth", "vibe")):
        energy_hint = "mid-tempo groove track"
        tempo_hint  = "medium pacing, flowing lines (5–8 words), melodic cadence"
    else:
        energy_hint = "instrumental track"
        tempo_hint  = "medium pacing, singable lines (5–8 words)"

    hint = (
        f"The user uploaded a {ext.lstrip('.')} file: '{name_hint}' "
        f"(~{est_minutes:.1f} min, {energy_hint}). "
        f"Match the tempo, pacing, and emotional cadence of this instrumental. "
        f"{tempo_hint}. "
        f"Ensure every lyrical line fits naturally within a consistent rhythmic grid "
        f"suitable for recording over this track. "
        f"The emotional arc of the lyrics must mirror the dynamic shape of the music."
    )
    return hint


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "5.0.0", "ffmpeg": is_ffmpeg_available()}


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    """Serve saved project audio files with proper CORS headers."""
    safe = Path(filename).name  # prevent path traversal
    path = AUDIO_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/mpeg", filename=safe)


@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    expected_pw = STUDIO_USERS.get(req.email.lower().strip())
    if expected_pw is None or req.password != expected_pw:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": SESSION_TOKEN}


@app.get("/artists/search")
def artists_search(q: str = ""):
    if len(q) < 2:
        return {"results": []}
    try:
        results = search_genius_artists(q)
        return {"results": results[:8]}
    except Exception as e:
        print(f"[API] Artist search error: {e}")
        return {"results": []}


@app.get("/global-artists")
def global_artists(language: str = ""):
    try:
        data = json.loads(GLOBAL_ARTISTS.read_text()) if GLOBAL_ARTISTS.exists() else {}
        if language:
            return {"artists": {language: data.get(language, {})}}
        return {"artists": data}
    except Exception as e:
        return {"artists": {}, "error": str(e)}


@app.post("/chorus/extract")
def chorus_extract(req: ChorusExtractRequest, token: str = Depends(verify_token)):
    if not req.lyrics.strip():
        raise HTTPException(status_code=400, detail="lyrics field is empty")
    chorus = _extract_chorus_from_lyrics(req.lyrics)
    return {"chorus": chorus, "found": bool(chorus)}


@app.post("/stems/extract")
async def stems_extract(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    ext = Path(file.filename or "audio.mp3").suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".flac"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}. Use MP3 or WAV.")

    content = await file.read()
    if len(content) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 60 MB)")

    file_id     = uuid.uuid4().hex[:10]
    upload_path = UPLOADS_DIR / f"{file_id}{ext}"
    upload_path.write_bytes(content)

    job_id = extract_stems_async(str(upload_path))
    print(f"[API] Stem job {job_id} started for {file.filename}", flush=True)

    background_tasks.add_task(cleanup_old_jobs, 7200)

    return {
        "job_id":    job_id,
        "status":    "processing",
        "filename":  file.filename,
        "size_kb":   len(content) // 1024,
    }


@app.get("/stems/{job_id}")
def stems_status(job_id: str, token: str = Depends(verify_token)):
    job = get_job(job_id)
    if job.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    ec2_ip   = os.getenv("EC2_PUBLIC_IP", "localhost")
    base_url = f"http://{ec2_ip}:8000/static/stems/{job_id}"

    stem_urls: dict[str, str] = {}
    if job.get("status") == "done":
        for stem_name, file_path in job.get("stems", {}).items():
            if Path(file_path).exists():
                stem_urls[stem_name] = f"{base_url}/{stem_name}.wav"

    return {
        "job_id":    job_id,
        "status":    job.get("status"),
        "stems":     stem_urls,
        "error":     job.get("error"),
        "elapsed_s": int(time.time() - job.get("started", time.time())),
    }


# ── Main generation endpoint — accepts multipart form with optional instrumental ──
@app.post("/generate", response_model=GenerateResponse)
async def generate(
    # JSON payload as a form field
    payload: str = Form(...),
    # Optional instrumental file
    instrumental: Optional[UploadFile] = File(default=None),
    token: str = Depends(verify_token),
):
    """
    Multipart endpoint:
      - payload: JSON string with all generation params
      - instrumental: optional MP3/WAV file to guide lyric style
    """
    try:
        req_data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON in payload field")

    pipeline = get_pipeline()
    t0 = time.time()

    # Extract all request params with defaults
    artists          = req_data.get("artists", ["Drake"])
    theme            = req_data.get("theme", "")
    structure_list   = req_data.get("structure", ["[Verse 1]", "[Chorus]", "[Verse 2]", "[Chorus]"])
    language         = req_data.get("language", "English")
    gender           = req_data.get("gender", "Neutral")
    bars             = int(req_data.get("bars", 16))
    reference_lyrics = req_data.get("reference_lyrics", "")
    num_variants     = int(req_data.get("num_variants", 3))
    temperature      = float(req_data.get("temperature", 0.85))
    style_strength   = float(req_data.get("style_strength", 0.7))
    gen_mode         = req_data.get("gen_mode", "generate")
    perspective_mode = req_data.get("perspective_mode", "same")
    enable_voice     = bool(req_data.get("enable_voice", True))
    enable_music     = bool(req_data.get("enable_music", True))
    remix_mode       = bool(req_data.get("remix_mode", False))
    locked_chorus    = req_data.get("locked_chorus", "").strip()
    section_mode     = req_data.get("section_mode", "Full Song")  # Verse Only, Full Song, etc.
    chorus_strict    = bool(req_data.get("chorus_strict", False))
    producer_mode    = bool(req_data.get("producer_mode", False))

    # Structure: convert list to string
    if isinstance(structure_list, list):
        structure_str = " → ".join(s.strip().strip("[]") for s in structure_list)
    else:
        structure_str = str(structure_list)

    # Verse Only mode: override structure
    if section_mode == "Verse Only":
        structure_str = "Verse 1"

    # ── Handle uploaded instrumental ──────────────────────────────────────
    instrumental_hint: str = ""
    instrumental_bytes: Optional[bytes] = None
    instrumental_ext: str = ".mp3"

    if instrumental is not None and instrumental.filename:
        try:
            instrumental_bytes = await instrumental.read()
            instrumental_ext   = Path(instrumental.filename).suffix.lower() or ".mp3"
            if len(instrumental_bytes) > 60 * 1024 * 1024:
                instrumental_bytes = None
                print("[API] Instrumental too large (>60MB) — skipped.", flush=True)
            else:
                instrumental_hint = _analyze_instrumental(instrumental_bytes, instrumental.filename)
                print(f"[API] Instrumental uploaded: {len(instrumental_bytes):,} bytes, hint: {instrumental_hint[:80]}", flush=True)
        except Exception as e:
            print(f"[API] Instrumental read error: {e}", flush=True)

    # ── Determine locked chorus ───────────────────────────────────────────
    if remix_mode and not locked_chorus and reference_lyrics:
        locked_chorus = _extract_chorus_from_lyrics(reference_lyrics)
        print(f"[API] Auto-extracted chorus ({len(locked_chorus)} chars)", flush=True)

    # ── Step 1: Lyrics ────────────────────────────────────────────────────
    try:
        res = pipeline.run(
            artists=artists,
            theme=theme,
            structure=structure_str,
            language=language,
            gender=gender,
            bars=bars,
            reference_lyrics=reference_lyrics,
            num_variants=num_variants,
            temperature=temperature,
            style_strength=style_strength,
            gen_mode=gen_mode,
            perspective_mode=perspective_mode,
            remix_mode=remix_mode,
            locked_chorus=locked_chorus,
            chorus_strict=chorus_strict,
            producer_mode=producer_mode,
            instrumental_hint=instrumental_hint,
            mode=section_mode,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lyrics generation failed: {e}")

    lyrics: str = res.get("lyrics", "")

    # ── Step 2: Voice synthesis ───────────────────────────────────────────
    voice_bytes: Optional[bytes] = None
    voice_error: Optional[str]  = None
    if enable_voice:
        try:
            voice_bytes = pipeline.voice_gen.generate_voice(lyrics)
            if voice_bytes and len(voice_bytes) < 1000:
                voice_error = f"Audio too small ({len(voice_bytes)} bytes)"
                voice_bytes = None
            elif not voice_bytes:
                vg = pipeline.voice_gen
                if not vg._eleven_client and not vg._openai_client:
                    voice_error = "No voice provider configured"
                elif vg._import_error:
                    voice_error = f"Package error: {vg._import_error}"
                else:
                    voice_error = "All voice providers exhausted"
        except Exception as e:
            voice_error = str(e)
            print(f"[API] Voice error: {e}")

    # ── Step 3: Music generation ───────────────────────────────────────────
    music_bytes: Optional[bytes] = None
    music_error: Optional[str]  = None
    if enable_music:
        try:
            style_tags  = f"{artists[0]} style, {language}"
            music_bytes = pipeline.music_gen.run_full_generation(
                lyrics, style_tags, res.get("theme", theme)
            )
            if not music_bytes:
                mg = pipeline.music_gen
                music_error = (
                    "Music backend disabled (no API keys)"
                    if mg.backend == "disabled"
                    else "All music backends failed — check Suno credits"
                )
        except Exception as e:
            music_error = str(e)
            print(f"[API] Music error: {e}")

    # ── Step 4: Audio mixing ──────────────────────────────────────────────
    mixed_bytes: Optional[bytes] = None
    mix_error:   Optional[str]  = None

    # Mix: vocal + uploaded instrumental if both present
    if voice_bytes and instrumental_bytes:
        try:
            mixed_bytes = mix_vocal_with_instrumental_bytes(
                voice_bytes,
                instrumental_bytes,
                ext=instrumental_ext,
                vocal_vol=1.0,
                inst_vol=0.55,
            )
            if not mixed_bytes:
                mix_error = "FFmpeg mixing failed — ffmpeg may not be installed"
        except Exception as e:
            mix_error = str(e)
            print(f"[API] Mix error: {e}")
    elif voice_bytes and not instrumental_bytes:
        # No instrumental uploaded — skip mixing
        pass

    # ── Step 5: Real AI Analysis ──────────────────────────────────────────
    analysis = None
    try:
        analysis_res = pipeline.run(
            artists=artists,
            theme=theme,
            structure=structure_str,
            reference_lyrics=lyrics,
            analysis_mode=True,
        )
        analysis = analysis_res.get("analysis")
    except Exception as e:
        print(f"[API] Analysis error: {e}")

    latency_ms = (time.time() - t0) * 1000

    def to_b64(b: Optional[bytes]) -> Optional[str]:
        return base64.b64encode(b).decode() if b else None

    return GenerateResponse(
        lyrics=lyrics,
        theme=res.get("theme", theme),
        versions=[
            LyricVariant(lyrics=v.get("lyrics", ""), style_fidelity=v.get("style_fidelity", 0.0))
            for v in res.get("versions", [])
        ],
        retrieval_quality=res.get("retrieval_quality", 0.0),
        latency_ms=latency_ms,
        retrieval_diagnostics=res.get("retrieval_diagnostics", {}),
        analysis=analysis,
        voice_audio_b64=to_b64(voice_bytes),
        music_audio_b64=to_b64(music_bytes),
        mixed_audio_b64=to_b64(mixed_bytes),
        voice_error=voice_error,
        music_error=music_error,
        mix_error=mix_error,
        locked_chorus=locked_chorus or None,
        instrumental_hint=instrumental_hint or None,
        timestamp=datetime.now().strftime("%H:%M:%S"),
    )


@app.get("/projects")
def get_projects(token: str = Depends(verify_token)):
    projects = _load_projects()
    return {"projects": list(reversed(projects))}


@app.delete("/projects/{project_id}")
def delete_project(project_id: str, token: str = Depends(verify_token)):
    projects = _load_projects()
    filtered = [p for p in projects if p.get("id") != project_id]
    if len(filtered) == len(projects):
        raise HTTPException(status_code=404, detail="Project not found")
    _save_projects(filtered)
    return {"deleted": project_id}


@app.post("/projects", response_model=Project)
def save_project(req: SaveProjectRequest, token: str = Depends(verify_token)):
    projects = _load_projects()
    project_id = str(uuid.uuid4())

    def _write_audio(b64_data: Optional[str], suffix: str) -> Optional[str]:
        if not b64_data:
            return None
        try:
            raw = base64.b64decode(b64_data)
            fname = f"{project_id}_{suffix}.mp3"
            (AUDIO_DIR / fname).write_bytes(raw)
            return f"/audio/{fname}"
        except Exception as e:
            print(f"[PROJECTS] Audio write failed ({suffix}): {e}", flush=True)
            return None

    voice_url = _write_audio(req.voice_audio_b64, "voice")
    music_url = _write_audio(req.music_audio_b64, "music")
    mix_url   = _write_audio(req.mixed_audio_b64, "mix")

    project = {
        "id":               project_id,
        "title":            req.title or req.theme[:40] or "Untitled",
        "theme":            req.theme,
        "artist":           req.artist,
        "lyrics":           req.lyrics,
        "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration_s":       req.duration_s,
        "has_voice":        req.has_voice,
        "has_music":        req.has_music,
        "has_mix":          req.has_mix,
        "voice_url":        voice_url,
        "music_url":        music_url,
        "mix_url":          mix_url,
        "language":         req.language,
        "bars":             req.bars,
        "structure":        req.structure,
        "gen_mode":         req.gen_mode,
        "perspective_mode": req.perspective_mode,
        "gender":           req.gender,
        "style_strength":   req.style_strength,
        "temperature":      req.temperature,
        "chorus_strict":    req.chorus_strict,
        "producer_mode":    req.producer_mode,
        "section_mode":     req.section_mode,
        "ref_lyrics":       req.ref_lyrics,
        "analysis":         req.analysis,
    }
    projects.append(project)
    if len(projects) > 200:
        projects = projects[-200:]
    _save_projects(projects)
    return project
