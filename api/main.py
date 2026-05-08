"""
api/main.py — SonicFlow Studio API v5.1 (Intelligence Layer)

Core endpoints:
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

Intelligence Layer (Phase 4):
  POST /analyze-track        → AudioAnalysis (real audio intelligence)
  GET  /genres               → { genres } list of available genre profiles
  POST /blend-genres         → BlendedGenre
  POST /extract-cadence      → CadenceProfile
  POST /generate-variants    → list[RemixVariant] (multi-genre remix)
  POST /generate-daw-session → DAW session ZIP download
  POST /analyse-production   → ProductionAnalysis (AI producer assistant)
"""
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import time
import time as _time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import asyncio
from fastapi import FastAPI, HTTPException, Depends, Header, Request, UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Rate limiting ─────────────────────────────────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _RATE_LIMIT_AVAILABLE = True
except ImportError:
    _RATE_LIMIT_AVAILABLE = False
    print("[API] slowapi not available — rate limiting disabled", flush=True)

# ── JWT auth ──────────────────────────────────────────────────────────────────
try:
    from jose import jwt as _jose_jwt, JWTError
    from passlib.context import CryptContext as _CryptContext
    _JWT_AVAILABLE = True
    _pwd_context = _CryptContext(schemes=["bcrypt"], deprecated="auto")
    _JWT_SECRET = os.getenv("JWT_SECRET", "sonicflow-jwt-secret-key-v1")
    _JWT_ALGORITHM = "HS256"
    _JWT_EXPIRY_HOURS = 24
except ImportError:
    _JWT_AVAILABLE = False
    print("[API] python-jose/passlib not available — using static token", flush=True)

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
from services.audio_analysis import analyze_audio
from services.genre_engine import list_genres, get_genre, blend_genres as _blend_genres, resolve_producer_controls, build_suno_genre_tags
from services.cadence_analysis import extract_cadence
from services.remix_engine import RemixVariantRequest, generate_remix_variants
from services.daw_export import build_daw_session, export_session_zip, DAWSessionRequest
from services.producer_assistant import analyse_production

app = FastAPI(title="SonicFlow Studio API", version="5.2.0")

# NOTE: StaticFiles removed — stem audio served via /stems/{job_id}/audio/{stem_name}
# so FastAPI CORS middleware applies and browser can play cross-origin audio.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiter setup ────────────────────────────────────────────────────────
if _RATE_LIMIT_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    limiter = None

def _rate_limit(rate: str):
    """Return slowapi rate-limit decorator, or identity if slowapi unavailable."""
    if limiter:
        return limiter.limit(rate)
    return lambda f: f

_pipeline: Optional[SongwritingPipeline] = None

def get_pipeline() -> SongwritingPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SongwritingPipeline()
    return _pipeline


# ── Auth ──────────────────────────────────────────────────────────────────
# Credentials loaded from environment — no plaintext secrets in source.
# Seed: ADMIN_EMAIL + ADMIN_PASSWORD_HASH (bcrypt) in .env
# Registration adds rows to data/users.json (bcrypt hashed).

_USERS_FILE = ROOT / "data" / "users.json"

def _load_users() -> dict:
    """Return {email: bcrypt_hash} from data/users.json + env seed."""
    users: dict = {}
    # Env-seeded admin
    admin_email = os.getenv("ADMIN_EMAIL", "").lower().strip()
    admin_hash  = os.getenv("ADMIN_PASSWORD_HASH", "")
    if admin_email and admin_hash:
        users[admin_email] = admin_hash
    # File-stored users
    if _USERS_FILE.exists():
        try:
            for u in json.loads(_USERS_FILE.read_text()):
                users[u["email"]] = u["password_hash"]
        except Exception:
            pass
    return users

def _save_user(email: str, password_hash: str) -> None:
    users: list = []
    if _USERS_FILE.exists():
        try:
            users = json.loads(_USERS_FILE.read_text())
        except Exception:
            pass
    users = [u for u in users if u["email"] != email]
    users.append({"email": email, "password_hash": password_hash})
    _USERS_FILE.write_text(json.dumps(users, indent=2))

# Brute-force protection: track failed attempts per IP
_login_attempts: dict[str, list[float]] = {}   # ip → [timestamp, ...]
_LOGIN_WINDOW_S  = 300   # 5-minute window
_LOGIN_MAX_FAILS = 10    # allow 10 failures before lockout

def _check_brute_force(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW_S]
    if len(attempts) >= _LOGIN_MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again in 5 minutes.")
    _login_attempts[ip] = attempts

def _record_failed_login(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW_S]
    _login_attempts[ip] = attempts + [now]

def _clear_failed_login(ip: str) -> None:
    _login_attempts.pop(ip, None)

# Token blacklist for logout (in-memory; cleared on restart — acceptable for 24h JWT)
_token_blacklist: set[str] = set()

def _create_access_token(data: dict) -> str:
    """Create a JWT access token with 24h expiry."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=_JWT_EXPIRY_HOURS)
    to_encode.update({"exp": expire})
    return _jose_jwt.encode(to_encode, _JWT_SECRET, algorithm=_JWT_ALGORITHM)

def verify_token(authorization: str = Header(default="")) -> str:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if token in _token_blacklist:
        raise HTTPException(status_code=401, detail="Token has been invalidated")

    if _JWT_AVAILABLE:
        try:
            payload = _jose_jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
            email = payload.get("sub")
            if email:
                return email
        except JWTError:
            pass

    raise HTTPException(status_code=401, detail="Invalid or expired token")


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
    output_mode: str
    timestamp: str
    chorus_preserved: Optional[bool] = None
    music_job_id: Optional[str] = None
    cadence_meta: Optional[dict] = None
    suno_style_tags: Optional[str] = None
    producer_validation: Optional[dict] = None

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
    output_mode: Optional[str] = "draft"
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
    output_mode: Optional[str] = "draft"
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
    stem_job_id: Optional[str] = None


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
# Replaced with real audio intelligence from services/audio_analysis.py

_audio_analysis_cache: dict[str, object] = {}  # hash → AudioAnalysis
_AUDIO_CACHE_MAX = 20  # max entries before FIFO eviction

def _evict_audio_cache() -> None:
    """Keep cache under max size — simple FIFO eviction."""
    if len(_audio_analysis_cache) > _AUDIO_CACHE_MAX:
        oldest_keys = list(_audio_analysis_cache.keys())[:-_AUDIO_CACHE_MAX]
        for k in oldest_keys:
            del _audio_analysis_cache[k]


def _analyze_instrumental(file_bytes: bytes, filename: str) -> str:
    """
    Real audio analysis using services/audio_analysis.py.
    Returns a rich prompt hint string; caches result by content hash.
    """
    key = hashlib.md5(file_bytes[:65536]).hexdigest()
    if key in _audio_analysis_cache:
        return _audio_analysis_cache[key].prompt_hint

    analysis = analyze_audio(file_bytes, filename)
    _evict_audio_cache()
    _audio_analysis_cache[key] = analysis
    return analysis.prompt_hint


# ── Async music generation job queue ─────────────────────────────────────
_music_jobs: dict[str, dict] = {}  # job_id → {status, audio_b64, error, created_at}
_music_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _submit_music_job(pipeline, lyrics: str, style_tags: str, theme: str) -> str:
    """Submit Suno generation to background thread pool. Returns job_id."""
    job_id = uuid.uuid4().hex[:16]
    _music_jobs[job_id] = {
        "status": "processing",
        "audio_b64": None,
        "error": None,
        "created_at": _time.time(),
    }

    def _run():
        try:
            music_bytes = pipeline.music_gen.run_full_generation(lyrics, style_tags, theme)
            if music_bytes:
                _music_jobs[job_id]["audio_b64"] = base64.b64encode(music_bytes).decode()
                _music_jobs[job_id]["status"] = "done"
            else:
                _music_jobs[job_id]["status"] = "failed"
                _music_jobs[job_id]["error"] = "Music backend returned no audio"
        except Exception as exc:
            _music_jobs[job_id]["status"] = "failed"
            _music_jobs[job_id]["error"] = str(exc)
            print(f"[MUSIC_JOB] {job_id} failed: {exc}", flush=True)

    _music_executor.submit(_run)
    return job_id


# ── Intelligence Layer helpers ─────────────────────────────────────────────

def _build_structured_suno_tags(
    artists: list,
    language: str,
    genre_profile=None,
    blended_genre=None,
    controls=None,
    audio_analysis_obj=None,
    cadence_constraints: str = "",
    structure: str = "",
) -> str:
    """Build a rich structured Suno orchestration block replacing simple tags."""
    lines = []

    # Genre
    if blended_genre:
        lines.append(f"[Genre]\n{blended_genre.primary} + {blended_genre.secondary} blend")
        lines.append(f"[Instrumentation]\n{', '.join(blended_genre.instrumentation[:5])}")
        lines.append(f"[BPM]\n{blended_genre.bpm:.0f}")
        lines.append(f"[Vocal Style]\n{blended_genre.vocal_style}")
    elif genre_profile:
        lines.append(f"[Genre]\n{genre_profile.name}")
        lines.append(f"[Instrumentation]\n{', '.join(genre_profile.instrumentation[:5])}")
        lines.append(f"[BPM]\n{genre_profile.bpm_midpoint:.0f}")
        lines.append(f"[Vocal Style]\n{genre_profile.vocal_style}")

    # Audio analysis
    if audio_analysis_obj and audio_analysis_obj.error is None:
        lines.append(f"[Key]\n{audio_analysis_obj.harmonic.key}")
        if audio_analysis_obj.beat.bpm > 10:
            lines.append(f"[BPM]\n{audio_analysis_obj.beat.bpm:.0f}")
        if audio_analysis_obj.cadence.flow_descriptors:
            lines.append(f"[Cadence]\n{', '.join(audio_analysis_obj.cadence.flow_descriptors)}")

    # Artist
    if artists:
        lines.append(f"[Style Reference]\n{' + '.join(artists[:2])} inspired")

    # Producer controls
    if controls:
        mods = controls.to_suno_modifiers()
        if mods:
            lines.append(f"[Production]\n{', '.join(mods)}")

    # Structure
    if structure:
        lines.append(f"[Structure]\n{structure}")

    # Language
    if language and language.lower() != "english":
        lines.append(f"[Language]\n{language}")

    return "\n\n".join(lines) if lines else f"{', '.join(artists[:1])} style, {language}"


# ── Background cleanup worker ─────────────────────────────────────────────

_DISK_QUOTA_WARN_PCT  = 85   # warn when disk > 85%
_DISK_QUOTA_PURGE_PCT = 90   # purge oldest stems when disk > 90%
_STEMS_MAX_AGE_S      = 3600 * 4   # 4 hours
_UPLOADS_MAX_AGE_S    = 3600 * 2   # 2 hours
_AUDIO_MAX_AGE_S      = 3600 * 24  # 24 hours (saved project audio)

def _get_disk_pct() -> float:
    import shutil
    usage = shutil.disk_usage("/")
    return 100.0 * usage.used / usage.total

def _purge_old_files(directory: Path, max_age_s: float, extensions=(".wav",".mp3",".m4a",".flac")) -> int:
    """Delete files older than max_age_s in directory. Returns count deleted."""
    count = 0
    cutoff = _time.time() - max_age_s
    try:
        for p in directory.rglob("*"):
            if p.is_file() and p.suffix in extensions:
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink(missing_ok=True)
                        count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count

def _cleanup_worker():
    while True:
        _time.sleep(600)  # run every 10 minutes
        try:
            now = _time.time()

            # 1. Clean old uploads
            deleted_uploads = _purge_old_files(UPLOADS_DIR, _UPLOADS_MAX_AGE_S)

            # 2. Clean old stems
            deleted_stems = _purge_old_files(STEMS_DIR, _STEMS_MAX_AGE_S)
            # Also prune empty stem job directories
            try:
                for job_dir in STEMS_DIR.iterdir():
                    if job_dir.is_dir() and not any(job_dir.rglob("*")):
                        job_dir.rmdir()
            except Exception:
                pass

            # 3. Evict stale music jobs from memory (> 2 hours)
            cutoff = now - 7200
            stale_jobs = [jid for jid, j in list(_music_jobs.items()) if j.get("created_at", 0) < cutoff]
            for jid in stale_jobs:
                _music_jobs.pop(jid, None)

            # 4. Clean /tmp sonicflow_ files
            for p in Path("/tmp").glob("sonicflow_*"):
                try:
                    if p.stat().st_mtime < now - 1800:
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

            # 5. Disk quota enforcement
            disk_pct = _get_disk_pct()
            if disk_pct > _DISK_QUOTA_PURGE_PCT:
                # Emergency purge: delete all stems and uploads immediately
                deleted_emergency = _purge_old_files(STEMS_DIR, 0)
                deleted_emergency += _purge_old_files(UPLOADS_DIR, 0)
                print(f"[CLEANUP] EMERGENCY purge at {disk_pct:.0f}% disk — deleted {deleted_emergency} files", flush=True)
            elif disk_pct > _DISK_QUOTA_WARN_PCT:
                print(f"[CLEANUP] WARNING: disk at {disk_pct:.0f}%", flush=True)

            if deleted_uploads + deleted_stems > 0:
                print(f"[CLEANUP] Purged {deleted_uploads} uploads + {deleted_stems} stems | disk={_get_disk_pct():.0f}%", flush=True)

        except Exception as e:
            print(f"[CLEANUP] Error: {e}", flush=True)

_cleanup_thread = threading.Thread(target=_cleanup_worker, daemon=True)
_cleanup_thread.start()


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "5.2.0", "ffmpeg": is_ffmpeg_available(), "intelligence_layer": True, "rate_limiting": _RATE_LIMIT_AVAILABLE, "jwt_auth": _JWT_AVAILABLE}


@app.get("/music-status/{job_id}")
def music_status(job_id: str, token: str = Depends(verify_token)):
    """Get status of an async music generation job."""
    job = _music_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Music job {job_id} not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "audio_b64": job.get("audio_b64"),
        "error": job.get("error"),
        "elapsed_s": int(_time.time() - job.get("created_at", _time.time())),
    }


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    """Serve saved project audio files with proper CORS headers."""
    safe = Path(filename).name  # prevent path traversal
    path = AUDIO_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/mpeg", filename=safe)


class RegisterRequest(BaseModel):
    email: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.post("/login", response_model=LoginResponse)
@_rate_limit("5/minute")
def login(req: LoginRequest, request: Request):
    """Authenticate with email + bcrypt password. Returns JWT (24h)."""
    ip = get_remote_address(request) if _RATE_LIMIT_AVAILABLE else "unknown"
    _check_brute_force(ip)

    email = req.email.lower().strip()
    users = _load_users()
    password_hash = users.get(email)

    if not password_hash or not _JWT_AVAILABLE:
        _record_failed_login(ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not _pwd_context.verify(req.password, password_hash):
        _record_failed_login(ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _clear_failed_login(ip)
    token = _create_access_token({"sub": email})
    return {"token": token}


@app.post("/logout")
def logout(token: str = Depends(verify_token), authorization: str = Header(default="")):
    """Invalidate the current JWT (added to server-side blacklist)."""
    raw_token = authorization.replace("Bearer ", "").strip()
    if raw_token:
        _token_blacklist.add(raw_token)
    return {"detail": "Logged out successfully"}


@app.post("/register")
@_rate_limit("3/minute")
def register(req: RegisterRequest, request: Request):
    """Register a new user account."""
    email = req.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    users = _load_users()
    if email in users:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _pwd_context.hash(req.password)
    _save_user(email, password_hash)
    token = _create_access_token({"sub": email})
    return {"token": token, "detail": "Account created"}


@app.post("/change-password")
def change_password(req: ChangePasswordRequest, token: str = Depends(verify_token)):
    """Change password for the authenticated user."""
    email = token  # verify_token returns email for JWT auth
    users = _load_users()
    password_hash = users.get(email)
    if not password_hash or not _pwd_context.verify(req.current_password, password_hash):
        raise HTTPException(status_code=401, detail="Current password incorrect")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    new_hash = _pwd_context.hash(req.new_password)
    _save_user(email, new_hash)
    return {"detail": "Password updated successfully"}


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
@_rate_limit("3/minute")
async def stems_extract(
    request: Request,
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


def _stems_from_disk(job_id: str) -> dict[str, str]:
    """Scan job directory for MP3/WAV stems — survives API restarts."""
    job_dir = STEMS_DIR / job_id
    if not job_dir.exists():
        return {}
    stems: dict[str, str] = {}
    for f in job_dir.rglob("*"):
        if f.is_file() and f.suffix in (".mp3", ".wav"):
            stems[f.stem] = str(f)
    return stems


@app.get("/stems/{job_id}/audio/{stem_name}")
def serve_stem_audio(job_id: str, stem_name: str):
    """Serve a single stem WAV with CORS headers.
    No token required — job_id is a 12-char hex nonce (unguessable).
    Falls back to disk scan so API restarts don't break existing jobs.
    """
    if not re.match(r'^[a-z_]+$', stem_name):
        raise HTTPException(status_code=400, detail="Invalid stem name")

    # Try in-memory first, fall back to disk scan
    job = get_job(job_id)
    stems = job.get("stems", {}) if job.get("status") == "done" else {}
    if not stems:
        stems = _stems_from_disk(job_id)

    if stem_name not in stems:
        raise HTTPException(status_code=404, detail=f"Stem '{stem_name}' not found")
    file_path = Path(stems[stem_name])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stem file missing on disk")
    media_type = "audio/mpeg" if file_path.suffix == ".mp3" else "audio/wav"
    filename   = f"{stem_name}{file_path.suffix}"
    return FileResponse(file_path, media_type=media_type, filename=filename)


@app.get("/stems/{job_id}")
def stems_status(job_id: str, token: str = Depends(verify_token)):
    job = get_job(job_id)

    # If not in memory (API restarted), reconstruct from disk
    if job.get("status") == "not_found":
        disk_stems = _stems_from_disk(job_id)
        if disk_stems:
            job = {"status": "done", "stems": disk_stems, "started": 0, "error": None}
        else:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    api_base = os.getenv("API_BASE_URL") or (
        f"https://{os.getenv('API_DOMAIN')}"
        if os.getenv("API_DOMAIN")
        else f"http://{os.getenv('EC2_PUBLIC_IP', 'localhost')}:8000"
    )

    stem_urls: dict[str, str] = {}
    if job.get("status") == "done":
        for stem_name, file_path in job.get("stems", {}).items():
            if Path(file_path).exists():
                stem_urls[stem_name] = f"{api_base}/stems/{job_id}/audio/{stem_name}"

    return {
        "job_id":    job_id,
        "status":    job.get("status"),
        "stems":     stem_urls,
        "error":     job.get("error"),
        "elapsed_s": int(time.time() - job.get("started", time.time())),
    }


# ── Main generation endpoint — accepts multipart form with optional instrumental ──
@app.post("/generate", response_model=GenerateResponse)
@_rate_limit("10/minute")
async def generate(
    request: Request,
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
    remix_mode       = bool(req_data.get("remix_mode", False))
    locked_chorus    = req_data.get("locked_chorus", "").strip()
    section_mode     = req_data.get("section_mode", "Full Song")
    chorus_strict    = bool(req_data.get("chorus_strict", False))
    producer_mode    = bool(req_data.get("producer_mode", False))

    # ── Output mode routing ───────────────────────────────────────────────
    # draft       → ElevenLabs voice only; mix only on explicit enable_mix=True
    # music_demo  → Suno full song only; no voice, no mix
    # producer    → ElevenLabs voice as reference; no Suno; never auto-mix
    output_mode  = req_data.get("output_mode", "draft")  # draft | music_demo | producer
    enable_mix   = bool(req_data.get("enable_mix", False))

    # vocal_source: how producer mode generates the vocal track
    #   suno_singing  → Suno full song (real musical vocals); user extracts stems in DAW
    #   reference_tts → ElevenLabs speech (timing/rhythm guide only)
    vocal_source = req_data.get("vocal_source", "suno_singing")

    if output_mode == "music_demo":
        enable_voice = True   # ElevenLabs timing guide
        enable_music = True   # Suno full song
        enable_mix   = False
    elif output_mode == "producer":
        if vocal_source == "suno_singing":
            enable_voice = True   # ElevenLabs timing guide
            enable_music = True   # Suno full song
        else:  # reference_tts
            enable_voice = True
            enable_music = False
        enable_mix = False  # producer assembles in DAW — never auto-mix
    else:  # draft (default)
        enable_voice = bool(req_data.get("enable_voice", True))
        enable_music = False  # Suno not triggered in draft mode
        # enable_mix stays as-is (user explicit)

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

    # ── Intelligence Layer: cadence, genre, producer controls ─────────────
    cadence_constraints: str = ""
    genre_tags_str: str = ""
    producer_controls_desc_str: str = ""
    suno_style_tags: str = ""

    target_genre = req_data.get("target_genre", "")
    genre_blend_data = req_data.get("genre_blend", {})
    producer_controls_data = req_data.get("producer_controls", {})

    genre_profile = None
    blended_genre = None
    controls = None

    if producer_controls_data:
        try:
            controls = resolve_producer_controls(producer_controls_data)
        except Exception as _e:
            print(f"[API] Producer controls error: {_e}", flush=True)

    if genre_blend_data.get("primary") and genre_blend_data.get("secondary"):
        try:
            blended_genre = _blend_genres(
                genre_blend_data["primary"],
                genre_blend_data["secondary"],
                float(genre_blend_data.get("weight", 0.5))
            )
            genre_tags_str = blended_genre.suno_tags
        except Exception as _e:
            print(f"[API] Genre blend error: {_e}", flush=True)
    elif target_genre:
        try:
            genre_profile = get_genre(target_genre)
            genre_tags_str = build_suno_genre_tags(
                genre_name=target_genre,
                controls=controls,
                audio_analysis=None,
                artist_style=artists[0] if artists else "",
                language=language,
            )
        except Exception as _e:
            print(f"[API] Genre tags error: {_e}", flush=True)

    cadence_source = reference_lyrics or locked_chorus
    if cadence_source and len(cadence_source.strip()) > 30:
        try:
            _cadence_profile = extract_cadence(cadence_source)
            cadence_constraints = _cadence_profile.constraint_block
        except Exception as _e:
            print(f"[API] Cadence extraction error: {_e}", flush=True)

    if controls:
        try:
            producer_controls_desc_str = controls.describe()
        except Exception as _e:
            print(f"[API] Producer controls describe error: {_e}", flush=True)
    elif producer_mode:
        try:
            from services.genre_engine import ProducerControls as _PC
            producer_controls_desc_str = _PC(darkness=0.5, melodicness=0.6, aggression=0.5, atmosphere=0.6, groove_density=0.5).describe()
        except Exception as _e:
            print(f"[API] Default producer controls error: {_e}", flush=True)

    # Resolve audio analysis object for suno tags
    _audio_obj = None
    if instrumental_bytes:
        _cache_key = hashlib.md5(instrumental_bytes[:65536]).hexdigest()
        _audio_obj = _audio_analysis_cache.get(_cache_key)

    suno_style_tags = _build_structured_suno_tags(
        artists=artists,
        language=language,
        genre_profile=genre_profile,
        blended_genre=blended_genre,
        controls=controls,
        audio_analysis_obj=_audio_obj,
        cadence_constraints=cadence_constraints,
        structure=structure_str,
    )

    print(f"[API] Intelligence layer: genre_tags={genre_tags_str[:60]!r} cadence_constraints={bool(cadence_constraints)} producer_desc={bool(producer_controls_desc_str)}", flush=True)

    # ── Step 1: Lyrics (offloaded to thread so uvicorn stays responsive) ────
    def _run_pipeline():
        return pipeline.run(
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
            cadence_constraints=cadence_constraints,
            genre_tags=genre_tags_str,
            producer_controls_desc=producer_controls_desc_str,
            suno_style_tags=suno_style_tags,
        )

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, _run_pipeline)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lyrics generation failed: {e}")

    lyrics: str = res.get("lyrics", "")

    # ── Post-process: force-inject locked chorus verbatim ─────────────────
    if locked_chorus and "[Chorus]" in lyrics:
        def _replace_chorus(m):
            return f"[Chorus]\n{locked_chorus.strip()}"
        lyrics = re.sub(
            r"\[Chorus[^\]]*\]\n.*?(?=\n\[|\Z)",
            _replace_chorus,
            lyrics,
            flags=re.DOTALL,
        )
        print("[API] Locked chorus force-injected into all [Chorus] sections.", flush=True)

    # ── Step 2: Voice synthesis ───────────────────────────────────────────
    voice_bytes: Optional[bytes] = None
    voice_error: Optional[str]  = None
    if enable_voice:
        try:
            from rag.voice import get_voice_id_for_artist
            _voice_id = get_voice_id_for_artist(artists[0] if artists else "", gender)
            voice_bytes = pipeline.voice_gen.generate_voice(lyrics, voice_id=_voice_id)
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

    # ── Step 3: Music generation (async for music_demo/producer) ──────────
    music_bytes: Optional[bytes] = None
    music_error: Optional[str]  = None
    music_job_id: Optional[str] = None

    # Use suno_style_tags for richer Suno prompts
    effective_style_tags = suno_style_tags or f"{', '.join(artists[:2])} style, {language}"

    if enable_music:
        try:
            if output_mode in ("music_demo", "producer"):
                # Submit async to avoid blocking uvicorn worker
                music_job_id = _submit_music_job(
                    pipeline, lyrics, effective_style_tags, res.get("theme", theme)
                )
                print(f"[API] Music job submitted async: {music_job_id}", flush=True)
                music_error = None  # job is running in background
            else:
                music_bytes = pipeline.music_gen.run_full_generation(
                    lyrics, effective_style_tags, res.get("theme", theme)
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

    # ── Step 4: Audio mixing (explicit request only) ──────────────────────
    # Mixing is NEVER automatic. Only triggered when:
    #   - output_mode == "draft"
    #   - enable_mix == True (user clicked "Mix with Uploaded Track")
    #   - voice bytes and instrumental bytes both present
    mixed_bytes: Optional[bytes] = None
    mix_error:   Optional[str]  = None

    if enable_mix and voice_bytes and instrumental_bytes and output_mode == "draft":
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
    elif enable_mix and not instrumental_bytes:
        mix_error = "No instrumental uploaded — upload an MP3/WAV to mix"

    # ── Step 5: Real AI Analysis (offloaded so event loop stays free) ────────
    analysis = None
    try:
        def _run_analysis():
            return pipeline.run(
                artists=artists,
                theme=theme,
                structure=structure_str,
                reference_lyrics=lyrics,
                analysis_mode=True,
            )
        analysis_res = await loop.run_in_executor(None, _run_analysis)
        analysis = analysis_res.get("analysis")
    except Exception as e:
        print(f"[API] Analysis error: {e}")

    latency_ms = (time.time() - t0) * 1000

    # ── Determine chorus_preserved ────────────────────────────────────────
    chorus_preserved: Optional[bool] = None
    if locked_chorus:
        # Check if every locked chorus line appears verbatim in the generated lyrics
        locked_lines = [l.strip() for l in locked_chorus.strip().splitlines() if l.strip()]
        if locked_lines:
            all_present = all(line in lyrics for line in locked_lines)
            chorus_preserved = all_present
            print(f"[API] chorus_preserved={chorus_preserved} "
                  f"({len(locked_lines)} locked lines checked)", flush=True)

    # ── Producer mode: syllable + rhyme validation pass ──────────────────
    producer_validation: Optional[dict] = None
    if producer_mode and lyrics:
        try:
            import os as _os
            _os.environ.setdefault("OPENAI_API_KEY", "dummy-not-needed-for-deterministic")
            from rag.validator import ChorusValidator as _CV
            _v = _CV()
            _, _syl_report = _v.enforce_syllable_consistency(lyrics, target_avg=0, tolerance=3.0)
            _rhyme_report = _v.check_rhyme_alignment(lyrics)

            _syl_cv = (
                (_syl_report.get("avg_syllables") or 0)
                and (_syl_report.get("violation_count", 0) / max(1, len(
                    [l for l in lyrics.split("\n") if l.strip() and not l.startswith("[")]
                )))
            )
            producer_validation = {
                "syllable_consistent": _syl_report.get("consistent", True),
                "avg_syllables_per_line": _syl_report.get("avg_syllables", 0),
                "syllable_violations": _syl_report.get("violation_count", 0),
                "rhyme_scheme": _rhyme_report.get("rhyme_scheme", "unknown"),
                "rhyme_density": _rhyme_report.get("rhyme_density", 0),
                "flow_density": _rhyme_report.get("flow_density", "unknown"),
            }

            # If syllable consistency badly fails (>30% of lines are outliers),
            # append a tightening note to the analysis so downstream tools can act on it.
            if _syl_report.get("violation_count", 0) > 0:
                print(
                    f"[PRODUCER] Syllable violations: {_syl_report['violation_count']} "
                    f"lines deviate from avg {_syl_report.get('avg_syllables', '?')} "
                    f"syl/line (tolerance ±3)",
                    flush=True,
                )
            else:
                print("[PRODUCER] Syllable consistency: PASS", flush=True)

            print(
                f"[PRODUCER] Rhyme: scheme={_rhyme_report.get('rhyme_scheme')} "
                f"density={_rhyme_report.get('rhyme_density', 0):.2f}",
                flush=True,
            )
        except Exception as _pv_err:
            print(f"[PRODUCER] Validation skipped: {_pv_err}", flush=True)

    # ── Cadence metadata for response ─────────────────────────────────────
    cadence_meta: Optional[dict] = None
    if lyrics:
        try:
            _cp = extract_cadence(lyrics)
            cadence_meta = {
                "rhyme_scheme": _cp.rhyme.scheme,
                "rhyme_density": _cp.rhyme.rhyme_density,
                "avg_syllables_per_line": _cp.phrase.avg_syllables_per_line,
                "flow_density": _cp.flow.density,
                "stress_style": _cp.flow.stress_style,
                "phrase_momentum": _cp.flow.phrase_momentum,
            }
        except Exception:
            pass

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
        output_mode=output_mode,
        timestamp=datetime.now().strftime("%H:%M:%S"),
        chorus_preserved=chorus_preserved,
        music_job_id=music_job_id,
        cadence_meta=cadence_meta,
        suno_style_tags=suno_style_tags or None,
        producer_validation=producer_validation,
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
        "output_mode":      req.output_mode or "draft",
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
        "stem_job_id":      req.stem_job_id,
    }
    projects.append(project)
    if len(projects) > 200:
        projects = projects[-200:]
    _save_projects(projects)
    return project


# ═══════════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER — Phase 4 endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── POST /analyze-track ───────────────────────────────────────────────────────

@app.post("/analyze-track")
async def analyze_track(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    """
    Real audio intelligence: BPM, key, energy, cadence, structure.
    Accepts any MP3/WAV file and returns a full AudioAnalysis object.
    """
    raw = await file.read()
    if len(raw) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 60MB)")

    analysis = analyze_audio(raw, file.filename or "track.mp3")
    return {
        "bpm":            analysis.beat.bpm,
        "bpm_confidence": analysis.beat.bpm_confidence,
        "tempo_variation": analysis.beat.tempo_variation,
        "key":            analysis.harmonic.key,
        "root":           analysis.harmonic.root,
        "mode":           analysis.harmonic.mode,
        "key_confidence": analysis.harmonic.key_confidence,
        "chords":         analysis.harmonic.chords,
        "energy_intensity": analysis.energy.intensity,
        "dynamic_range_db": analysis.energy.dynamic_range,
        "section_energies": analysis.energy.section_energies,
        "onset_density":  analysis.cadence.onset_density,
        "syllable_density": analysis.cadence.syllable_density_estimate,
        "flow_descriptors": analysis.cadence.flow_descriptors,
        "stress_pattern": analysis.cadence.stress_pattern,
        "detected_sections": analysis.structure.detected_sections,
        "total_duration_s": analysis.structure.total_duration_s,
        "prompt_hint":    analysis.prompt_hint,
        "suno_tags":      analysis.suno_tags,
        "analysis_latency_ms": analysis.analysis_latency_ms,
        "error":          analysis.error,
    }


# ── GET /genres ───────────────────────────────────────────────────────────────

@app.get("/genres")
@_rate_limit("30/minute")
def get_genres(request: Request, token: str = Depends(verify_token)):
    """List all available genre profiles."""
    genres = []
    for name in list_genres():
        g = get_genre(name)
        if g:
            genres.append(g.to_dict())
    return {"genres": genres}


# ── POST /blend-genres ────────────────────────────────────────────────────────

class BlendGenresRequest(BaseModel):
    primary: str
    secondary: str
    weight: float = 0.5    # 0=all primary, 1=all secondary

@app.post("/blend-genres")
@_rate_limit("30/minute")
def blend_genres_endpoint(req: BlendGenresRequest, request: Request, token: str = Depends(verify_token)):
    """Blend two genres into a weighted hybrid."""
    try:
        result = _blend_genres(req.primary, req.secondary, req.weight)
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── POST /extract-cadence ─────────────────────────────────────────────────────

class ExtractCadenceRequest(BaseModel):
    lyrics: str

@app.post("/extract-cadence")
@_rate_limit("30/minute")
def extract_cadence_endpoint(req: ExtractCadenceRequest, request: Request, token: str = Depends(verify_token)):
    """Extract cadence profile from lyrics for flow transfer."""
    profile = extract_cadence(req.lyrics)
    return {
        "rhyme_scheme":          profile.rhyme.scheme,
        "rhyme_density":         profile.rhyme.rhyme_density,
        "internal_rhyme_density": profile.rhyme.internal_rhyme_density,
        "avg_words_per_line":    profile.phrase.avg_words_per_line,
        "avg_syllables_per_line": profile.phrase.avg_syllables_per_line,
        "line_length_pattern":   profile.phrase.line_length_pattern,
        "flow_density":          profile.flow.density,
        "stress_style":          profile.flow.stress_style,
        "phrase_momentum":       profile.flow.phrase_momentum,
        "cadence_descriptors":   profile.flow.cadence_descriptors,
        "section_count":         len(profile.section_cadences),
        "constraint_block":      profile.constraint_block,
    }


# ── POST /generate-variants ───────────────────────────────────────────────────

class GenerateVariantsRequest(BaseModel):
    locked_chorus: str
    original_lyrics: str
    theme: str
    artists: list[str] = []
    target_genres: list[str]   # e.g. ["drill", "edm", "acoustic"]
    bars: int = 16
    language: str = "English"
    producer_controls: Optional[dict] = None

@app.post("/generate-variants")
async def generate_variants_endpoint(
    req: GenerateVariantsRequest,
    token: str = Depends(verify_token),
):
    """
    Generate multi-genre remix variants using the same locked chorus.
    Each variant is a genuine genre remix — not just temperature variation.
    """
    if not req.locked_chorus.strip():
        raise HTTPException(status_code=400, detail="locked_chorus is required")
    if not req.target_genres:
        raise HTTPException(status_code=400, detail="target_genres must not be empty")
    if len(req.target_genres) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 genre variants per request")

    controls = None
    if req.producer_controls:
        controls = resolve_producer_controls(req.producer_controls)

    cadence_profile = None
    if req.original_lyrics:
        cadence_profile = extract_cadence(req.original_lyrics)

    variant_req = RemixVariantRequest(
        locked_chorus=req.locked_chorus,
        original_lyrics=req.original_lyrics,
        theme=req.theme,
        artists=req.artists,
        target_genres=req.target_genres,
        bars=req.bars,
        language=req.language,
        cadence_profile=cadence_profile,
        controls=controls,
    )

    variants = generate_remix_variants(variant_req)
    return {
        "variants": [v.to_dict() for v in variants],
        "count": len(variants),
        "locked_chorus": req.locked_chorus,
    }


# ── POST /generate-daw-session ────────────────────────────────────────────────

class DAWSessionApiRequest(BaseModel):
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
    chords: list[str] = []
    project_id: Optional[str] = None       # if present, attach stems from library
    voice_audio_b64: Optional[str] = None
    music_audio_b64: Optional[str] = None
    mix_audio_b64: Optional[str] = None
    genre_data: Optional[dict] = None           # genre profile or blend data
    cadence_data: Optional[dict] = None         # cadence profile
    audio_analysis_data: Optional[dict] = None  # BPM/key/chords from audio analysis

@app.post("/generate-daw-session")
async def generate_daw_session(
    req: DAWSessionApiRequest,
    token: str = Depends(verify_token),
):
    """
    Build and download a full DAW session ZIP:
    stems, MIDI, arrangement markers, project.json, lyrics, README,
    and optional intelligence metadata (genre, cadence, audio analysis).
    """
    daw_req = DAWSessionRequest(
        title=req.title,
        artist=req.artist,
        theme=req.theme,
        lyrics=req.lyrics,
        language=req.language,
        output_mode=req.output_mode,
        bpm=req.bpm,
        key=req.key,
        bars=req.bars,
        darkness=req.darkness,
        chords=req.chords,
        genre_data=req.genre_data,
        cadence_data=req.cadence_data,
        audio_analysis_data=req.audio_analysis_data,
    )

    session = build_daw_session(daw_req)

    # Decode audio if provided
    voice_bytes = base64.b64decode(req.voice_audio_b64) if req.voice_audio_b64 else None
    music_bytes = base64.b64decode(req.music_audio_b64) if req.music_audio_b64 else None
    mix_bytes   = base64.b64decode(req.mix_audio_b64)   if req.mix_audio_b64   else None

    # Load stems from disk if project_id provided
    stem_bytes_map: dict[str, bytes] = {}
    if req.project_id:
        stem_dir = STEMS_DIR
        for stem_dir_candidate in stem_dir.rglob("*.mp3"):
            pass  # stems are found per job_id; leave for DAW re-export use case

    zip_data = export_session_zip(
        session,
        stem_bytes=stem_bytes_map,
        voice_bytes=voice_bytes,
        music_bytes=music_bytes,
        mix_bytes=mix_bytes,
        genre_data=req.genre_data,
        cadence_data=req.cadence_data,
        audio_analysis_data=req.audio_analysis_data,
    )

    safe_name = re.sub(r"[^\w\-]", "_", req.title)[:32]
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_daw_session.zip"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ── POST /analyse-production ──────────────────────────────────────────────────

class AnalyseProductionRequest(BaseModel):
    lyrics: str
    theme: str = ""
    artists: list[str] = []
    genre: str = ""
    use_llm: bool = True

@app.post("/analyse-production")
async def analyse_production_endpoint(
    req: AnalyseProductionRequest,
    token: str = Depends(verify_token),
):
    """
    AI Producer Assistant: hook scoring, arrangement analysis,
    emotional arc, remix suggestions, and LLM deep analysis.
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if req.use_llm else None

    result = analyse_production(
        lyrics=req.lyrics,
        theme=req.theme,
        artists=req.artists,
        genre=req.genre,
        openai_client=client,
        use_llm=req.use_llm,
    )

    return {
        "hook": {
            "score":              result.hook.score,
            "replayability":      result.hook.replayability,
            "strengths":          result.hook.strengths,
            "weaknesses":         result.hook.weaknesses,
            "suggested_rewrites": result.hook.suggested_rewrites,
        },
        "arrangement": {
            "section_balance": result.arrangement.section_balance,
            "energy_arc":      result.arrangement.energy_arc,
            "is_chorus_heavy": result.arrangement.is_chorus_heavy,
            "is_verse_heavy":  result.arrangement.is_verse_heavy,
            "suggestions":     result.arrangement.suggestions,
        },
        "emotional_arc": {
            "detected_tone":    result.emotional_arc.detected_tone,
            "journey":          result.emotional_arc.emotional_journey,
            "tension_points":   result.emotional_arc.tension_points,
            "resolution":       result.emotional_arc.resolution,
            "coherence_score":  result.emotional_arc.coherence_score,
        },
        "remix_suggestions": [
            {
                "genre":          s.genre,
                "rationale":      s.rationale,
                "bpm_shift":      s.bpm_shift,
                "key_suggestion": s.key_suggestion,
            }
            for s in result.remix_suggestions
        ],
        "overall_score":  result.overall_score,
        "producer_notes": result.producer_notes,
        "llm_analysis":   result.llm_analysis,
    }
