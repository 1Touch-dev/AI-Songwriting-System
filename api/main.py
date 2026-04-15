"""
api/main.py — FastAPI backend for SonicFlow Studio.

Endpoints:
  POST /login              → { token: str }
  POST /generate           → GenerateResult (with base64 audio fields)
  GET  /artists/search     → { results: [str] }
  GET  /projects           → { projects: [Project] }
  GET  /health             → { status: "ok" }
"""
import base64
import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Project root on path ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# ── Project storage (file-based) ──────────────────────────────────────────
PROJECTS_FILE = ROOT / "data" / "projects.json"
PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)

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

app = FastAPI(title="SonicFlow Studio API", version="3.0.0")

# ── CORS — allow Next.js dev (3001) and prod ──────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy-load pipeline (cached) ───────────────────────────────────────────
_pipeline: Optional[SongwritingPipeline] = None

def get_pipeline() -> SongwritingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SongwritingPipeline()
    return _pipeline


# ── Auth ─────────────────────────────────────────────────────────────────
# Hardcoded studio credentials — replace with DB-backed auth when needed
STUDIO_USERS = {
    "admin@studio.com": "admins",
}
SESSION_TOKEN = "sonicflow-studio-session-v3"   # shared session token

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

class GenerateRequest(BaseModel):
    artists: list[str]
    theme: str
    structure: list[str]
    language: str = "English"
    gender: str = "Neutral"
    bars: int = 16
    reference_lyrics: str = ""
    num_variants: int = 3
    temperature: float = 0.85
    style_strength: float = 0.7
    gen_mode: str = "generate"
    perspective_mode: str = "same"
    enable_voice: bool = True
    enable_music: bool = True

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
    timestamp: str

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

class SaveProjectRequest(BaseModel):
    title: str
    theme: str
    artist: str
    lyrics: str
    has_voice: bool
    has_music: bool
    duration_s: float = 0.0


# ── Routes ────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0"}


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


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, token: str = Depends(verify_token)):
    pipeline = get_pipeline()
    t0 = time.time()

    # Convert structure list → " → " string (pipeline expects a plain string)
    if isinstance(req.structure, list):
        # Strip brackets e.g. "[Verse 1]" → "Verse 1"
        structure_str = " → ".join(s.strip().strip("[]") for s in req.structure)
    else:
        structure_str = req.structure

    # ── Step 1: Lyrics ────────────────────────────────────────────────
    try:
        res = pipeline.run(
            artists=req.artists,
            theme=req.theme,
            structure=structure_str,
            language=req.language,
            gender=req.gender,
            bars=req.bars,
            reference_lyrics=req.reference_lyrics,
            num_variants=req.num_variants,
            temperature=req.temperature,
            style_strength=req.style_strength,
            gen_mode=req.gen_mode,
            perspective_mode=req.perspective_mode,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lyrics generation failed: {e}")

    lyrics: str = res.get("lyrics", "")

    # ── Step 2: Voice synthesis ────────────────────────────────────────
    voice_bytes: Optional[bytes] = None
    if req.enable_voice:
        try:
            voice_bytes = pipeline.voice_gen.generate_voice(lyrics)
            if voice_bytes and len(voice_bytes) < 1000:
                voice_bytes = None
        except Exception as e:
            print(f"[API] Voice error: {e}")

    # ── Step 3: Music generation ───────────────────────────────────────
    music_bytes: Optional[bytes] = None
    if req.enable_music:
        try:
            style_tags = f"{req.artists[0]} style, {req.language}"
            music_bytes = pipeline.music_gen.run_full_generation(
                lyrics, style_tags, res.get("theme", req.theme)
            )
        except Exception as e:
            print(f"[API] Music error: {e}")

    # ── Step 4: Mix ────────────────────────────────────────────────────
    mixed_bytes: Optional[bytes] = None
    if voice_bytes and music_bytes:
        try:
            from rag.audio_mixer import mix_voice_and_music
            mixed_bytes = mix_voice_and_music(voice_bytes, music_bytes)
        except Exception as e:
            print(f"[API] Mix error: {e}")

    # ── Step 5: Analysis ───────────────────────────────────────────────
    analysis = None
    try:
        analysis_res = pipeline.run(
            artists=req.artists,
            theme=req.theme,
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
        theme=res.get("theme", req.theme),
        versions=[
            LyricVariant(
                lyrics=v.get("lyrics", ""),
                style_fidelity=v.get("style_fidelity", 0.0),
            )
            for v in res.get("versions", [])
        ],
        retrieval_quality=res.get("retrieval_quality", 0.0),
        latency_ms=latency_ms,
        retrieval_diagnostics=res.get("retrieval_diagnostics", {}),
        analysis=analysis,
        voice_audio_b64=to_b64(voice_bytes),
        music_audio_b64=to_b64(music_bytes),
        mixed_audio_b64=to_b64(mixed_bytes),
        timestamp=datetime.now().strftime("%H:%M:%S"),
    )


@app.get("/projects")
def get_projects(token: str = Depends(verify_token)):
    projects = _load_projects()
    # Return newest first
    return {"projects": list(reversed(projects))}


@app.post("/projects", response_model=Project)
def save_project(req: SaveProjectRequest, token: str = Depends(verify_token)):
    projects = _load_projects()
    project = {
        "id": str(uuid.uuid4()),
        "title": req.title or req.theme[:40] or "Untitled",
        "theme": req.theme,
        "artist": req.artist,
        "lyrics": req.lyrics,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration_s": req.duration_s,
        "has_voice": req.has_voice,
        "has_music": req.has_music,
    }
    projects.append(project)
    # Keep max 200 projects
    if len(projects) > 200:
        projects = projects[-200:]
    _save_projects(projects)
    return project
