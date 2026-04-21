"""
stem_extractor.py — Audio stem separation using Demucs (Meta AI).

Model : htdemucs  (drums / bass / other / vocals)
Mode  : background-threaded job with polling
Output: WAV files on disk, served as static files via FastAPI

Job lifecycle:
  processing → done | failed

Stems are stored at:
  data/stems/{job_id}/{stem_name}.wav

Accessible via FastAPI StaticFiles at:
  /static/stems/{job_id}/{stem_name}.wav
"""
from __future__ import annotations

import os
import time
import uuid
import threading
import traceback
from pathlib import Path
from typing import Optional

ROOT_DIR  = Path(__file__).resolve().parent.parent
STEMS_DIR = ROOT_DIR / "data" / "stems"
STEMS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job registry (suitable for single-process deployments)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

STEM_NAMES = ["vocals", "drums", "bass", "other"]
DEFAULT_MODEL = "htdemucs"


# ── Public API ────────────────────────────────────────────────────────────

def extract_stems_async(file_path: str) -> str:
    """
    Start background stem extraction.
    Returns job_id immediately; poll get_job(job_id) for status.
    """
    job_id = uuid.uuid4().hex[:12]
    job_dir = STEMS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "processing",
            "started": time.time(),
            "file_path": file_path,
            "job_dir": str(job_dir),
            "stems": {},
            "error": None,
        }

    t = threading.Thread(
        target=_run_extraction,
        args=(job_id, file_path, str(job_dir)),
        daemon=True,
    )
    t.start()
    return job_id


def get_job(job_id: str) -> dict:
    """Return job status dict (or {"status": "not_found"})."""
    with _jobs_lock:
        return dict(_jobs.get(job_id, {"status": "not_found"}))


def cleanup_old_jobs(max_age_seconds: int = 3600):
    """Remove jobs older than max_age_seconds from memory and disk."""
    cutoff = time.time() - max_age_seconds
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j.get("started", 0) < cutoff]
        for jid in stale:
            job_dir = Path(_jobs[jid].get("job_dir", ""))
            if job_dir.exists():
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)
            del _jobs[jid]
    return len(stale)


# ── Background worker ─────────────────────────────────────────────────────

def _run_extraction(job_id: str, file_path: str, job_dir: str):
    try:
        _update_job(job_id, status="processing")
        print(f"[STEMS] Job {job_id}: loading Demucs ({DEFAULT_MODEL})...", flush=True)

        from demucs.api import Separator
        separator = Separator(DEFAULT_MODEL)

        print(f"[STEMS] Job {job_id}: separating {file_path}...", flush=True)
        origin, separated = separator.separate_audio_file(file_path)

        stems: dict[str, str] = {}
        sr = separator.samplerate

        try:
            import torchaudio
            for stem_name, tensor in separated.items():
                out_path = str(Path(job_dir) / f"{stem_name}.wav")
                torchaudio.save(out_path, tensor.cpu(), sr)
                stems[stem_name] = out_path
                print(f"[STEMS] Job {job_id}: saved {stem_name}.wav", flush=True)
        except ImportError:
            # Fallback: use demucs save_audio if torchaudio unavailable
            from demucs.audio import save_audio
            for stem_name, tensor in separated.items():
                out_path = str(Path(job_dir) / f"{stem_name}.wav")
                save_audio(tensor, out_path, sr)
                stems[stem_name] = out_path

        _update_job(job_id, status="done", stems=stems, completed=time.time())
        print(f"[STEMS] Job {job_id}: done. Stems: {list(stems.keys())}", flush=True)

    except ImportError as e:
        err = f"Demucs not installed: {e}. Run: pip install demucs"
        print(f"[STEMS] Job {job_id}: {err}", flush=True)
        _update_job(job_id, status="failed", error=err)

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[STEMS] Job {job_id}: failed — {err}", flush=True)
        traceback.print_exc()
        _update_job(job_id, status="failed", error=err)


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
