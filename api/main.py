"""
api/main.py — FastAPI backend for SonicFlow Studio.

Endpoints:
  POST /login                → { token: str }
  POST /generate             → GenerateResult (lyrics + base64 audio)
  GET  /artists/search       → { results: [str] }
  GET  /global-artists       → { artists: dict }
  POST /chorus/extract       → { chorus: str, found: bool }
  POST /stems/extract        → { job_id: str, status: str }
  GET  /stems/{job_id}       → { status, stems: {name: url} }
  GET  /projects             → { projects: [Project] }
  POST /projects             → Project
  DELETE /projects/{id}      → { deleted: str }
  GET  /health               → { status: "ok" }
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

from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Project root on path ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# ── Dirs ──────────────────────────────────────────────────────────────────
PROJECTS_FILE  = ROOT / "data" / "projects.json"
STEMS_DIR      = ROOT / "data" / "stems"
UPLOADS_DIR    = ROOT / "data" / "uploads"
GLOBAL_ARTISTS = ROOT / "data" / "global_artists.json"
for d in (PROJECTS_FILE.parent, STEMS_DIR, UPLOADS_DIR):
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

app = FastAPI(title="SonicFlow Studio API", version="4.0.0")

# ── Static files for stems ────────────────────────────────────────────────
app.mount("/static/stems", StaticFiles(directory=str(STEMS_DIR)), name="stems")

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy-load pipeline ────────────────────────────────────────────────────
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
    # Remix mode fields
    remix_mode: bool = False
    locked_chorus: str = ""

class ChorusExtractRequest(BaseModel):
    lyrics: str

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
    locked_chorus: Optional[str]
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


# ── Chorus extraction helper ──────────────────────────────────────────────
def _extract_chorus_from_lyrics(lyrics: str) -> str:
    """
    Extract the chorus/hook from song lyrics.
    1. Try labeled section headers ([Chorus], [Hook], [Refrain])
    2. Fall back to GPT-4o-mini for unlabeled lyrics
    """
    from openai import OpenAI

    # Fast path: labelled sections
    for pattern in [
        r'\[chorus\](.*?)(?=\n\[|\Z)',
        r'\[hook\](.*?)(?=\n\[|\Z)',
        r'\[refr[ae]in\](.*?)(?=\n\[|\Z)',
    ]:
        m = re.search(pattern, lyrics, re.I | re.DOTALL)
        if m:
            return m.group(1).strip()

    # Fallback: LLM extraction
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    "Extract ONLY the chorus or most-repeated hook section from these song lyrics. "
                    "Return just the chorus lines with no labels, no commentary.\n\n"
                    f"Lyrics:\n{lyrics[:2000]}"
                ),
            }],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[API] Chorus extraction LLM error: {e}")
        return ""


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0"}


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
    """Return global artist database, optionally filtered by language."""
    try:
        data = json.loads(GLOBAL_ARTISTS.read_text()) if GLOBAL_ARTISTS.exists() else {}
        if language:
            return {"artists": {language: data.get(language, {})}}
        return {"artists": data}
    except Exception as e:
        return {"artists": {}, "error": str(e)}


@app.post("/chorus/extract")
def chorus_extract(req: ChorusExtractRequest, token: str = Depends(verify_token)):
    """Extract the chorus/hook from provided song lyrics."""
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
    """
    Upload an audio file (MP3/WAV) and start async stem extraction.
    Returns job_id immediately. Poll GET /stems/{job_id} for status.
    """
    ext = Path(file.filename or "audio.mp3").suffix.lower()
    if ext not in (".mp3", ".wav", ".m4a", ".flac"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}. Use MP3 or WAV.")

    # Save uploaded file
    file_id = uuid.uuid4().hex[:10]
    upload_path = UPLOADS_DIR / f"{file_id}{ext}"
    content = await file.read()
    if len(content) > 60 * 1024 * 1024:  # 60 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 60 MB)")
    upload_path.write_bytes(content)

    # Start background extraction
    job_id = extract_stems_async(str(upload_path))
    print(f"[API] Stem extraction job {job_id} started for {file.filename}", flush=True)

    # Schedule cleanup of old jobs periodically
    background_tasks.add_task(cleanup_old_jobs, 7200)

    return {
        "job_id": job_id,
        "status": "processing",
        "filename": file.filename,
        "size_kb": len(content) // 1024,
    }


@app.get("/stems/{job_id}")
def stems_status(job_id: str, token: str = Depends(verify_token)):
    """
    Poll stem extraction job status.
    When done, returns stem download URLs relative to this server.
    """
    job = get_job(job_id)
    if job.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    ec2_ip = os.getenv("EC2_PUBLIC_IP", "localhost")
    base_url = f"http://{ec2_ip}:8000/static/stems/{job_id}"

    stem_urls: dict[str, str] = {}
    if job.get("status") == "done":
        for stem_name, file_path in job.get("stems", {}).items():
            if Path(file_path).exists():
                stem_urls[stem_name] = f"{base_url}/{stem_name}.wav"

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "stems": stem_urls,
        "error": job.get("error"),
        "elapsed_s": int(time.time() - job.get("started", time.time())),
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, token: str = Depends(verify_token)):
    pipeline = get_pipeline()
    t0 = time.time()

    # Convert structure list → " → " string
    if isinstance(req.structure, list):
        structure_str = " → ".join(s.strip().strip("[]") for s in req.structure)
    else:
        structure_str = req.structure

    # Determine locked chorus for remix mode
    locked_chorus = req.locked_chorus.strip() if req.remix_mode else ""
    if req.remix_mode and not locked_chorus and req.reference_lyrics:
        # Auto-extract chorus from reference lyrics
        locked_chorus = _extract_chorus_from_lyrics(req.reference_lyrics)
        print(f"[API] Remix mode: auto-extracted chorus ({len(locked_chorus)} chars)", flush=True)

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
            remix_mode=req.remix_mode,
            locked_chorus=locked_chorus,
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lyrics generation failed: {e}")

    lyrics: str = res.get("lyrics", "")

    # ── Step 2: Voice synthesis (ElevenLabs → OpenAI TTS fallback) ────
    voice_bytes: Optional[bytes] = None
    voice_error: Optional[str]  = None
    if req.enable_voice:
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

    # ── Step 3: Music generation ───────────────────────────────────────
    music_bytes: Optional[bytes] = None
    music_error: Optional[str]  = None
    if req.enable_music:
        try:
            style_tags = f"{req.artists[0]} style, {req.language}"
            music_bytes = pipeline.music_gen.run_full_generation(
                lyrics, style_tags, res.get("theme", req.theme)
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

    mixed_bytes: Optional[bytes] = None

    # ── Step 4: Analysis ───────────────────────────────────────────────
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
        locked_chorus=locked_chorus or None,
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
    if len(projects) > 200:
        projects = projects[-200:]
    _save_projects(projects)
    return project
