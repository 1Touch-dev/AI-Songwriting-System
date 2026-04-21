"""
stem_extractor.py — Audio stem separation using Demucs (Meta AI).

Model : htdemucs  (drums / bass / other / vocals)
Mode  : background-threaded job with polling
Output: WAV files on disk, served as static files via FastAPI

Uses subprocess `python -m demucs` for compatibility across demucs versions.
"""
from __future__ import annotations

import sys
import subprocess
import time
import uuid
import threading
import traceback
from pathlib import Path

ROOT_DIR  = Path(__file__).resolve().parent.parent
STEMS_DIR = ROOT_DIR / "data" / "stems"
STEMS_DIR.mkdir(parents=True, exist_ok=True)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

DEFAULT_MODEL = "htdemucs"


def extract_stems_async(file_path: str) -> str:
    job_id  = uuid.uuid4().hex[:12]
    job_dir = STEMS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    with _jobs_lock:
        _jobs[job_id] = {
            "status":    "processing",
            "started":   time.time(),
            "file_path": file_path,
            "job_dir":   str(job_dir),
            "stems":     {},
            "error":     None,
        }
    t = threading.Thread(target=_run_extraction, args=(job_id, file_path, str(job_dir)), daemon=True)
    t.start()
    return job_id


def get_job(job_id: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(job_id, {"status": "not_found"}))


def cleanup_old_jobs(max_age_seconds: int = 3600) -> int:
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


def _run_extraction(job_id: str, file_path: str, job_dir: str):
    try:
        print(f"[STEMS] Job {job_id}: running demucs on {file_path}...", flush=True)
        cmd = [
            sys.executable, "-m", "demucs",
            "--name", DEFAULT_MODEL,
            "--out",  job_dir,
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"demucs exited {result.returncode}: {result.stderr[-500:]}")

        audio_name = Path(file_path).stem
        stem_dir   = Path(job_dir) / DEFAULT_MODEL / audio_name
        if not stem_dir.exists():
            stem_dir = Path(job_dir) / audio_name

        stems: dict[str, str] = {}
        for wav in stem_dir.glob("*.wav"):
            stems[wav.stem] = str(wav)
            print(f"[STEMS] Job {job_id}: found {wav.name}", flush=True)

        if not stems:
            raise RuntimeError(f"No WAV files found under {stem_dir}")

        _update_job(job_id, status="done", stems=stems, completed=time.time())
        print(f"[STEMS] Job {job_id}: done — {list(stems.keys())}", flush=True)

    except subprocess.TimeoutExpired:
        _update_job(job_id, status="failed", error="Demucs timed out after 10 minutes")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[STEMS] Job {job_id}: FAILED — {err}", flush=True)
        traceback.print_exc()
        _update_job(job_id, status="failed", error=err)


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
