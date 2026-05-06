"""
stem_extractor.py — Audio stem separation using Demucs (Meta AI).

Model : htdemucs  (drums / bass / other / vocals)
Mode  : background-threaded job with polling
Output: MP3 files on disk (converted from WAV to save ~10x disk space)

Uses subprocess `python -m demucs` for compatibility across demucs versions.
"""
from __future__ import annotations

import os
import sys
import shutil
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
_demucs_sem = threading.Semaphore(1)  # only one demucs process at a time (RAM constraint)

DEFAULT_MODEL   = "htdemucs"
STEM_MAX_AGE_S  = 4 * 3600  # auto-delete stems older than 4 hours


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


def cleanup_old_jobs(max_age_seconds: int = STEM_MAX_AGE_S) -> int:
    cutoff = time.time() - max_age_seconds
    removed = 0
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j.get("started", 0) < cutoff]
        for jid in stale:
            job_dir = Path(_jobs[jid].get("job_dir", ""))
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
            del _jobs[jid]
            removed += 1

    # Also sweep disk for orphaned stem dirs not tracked in memory
    try:
        cutoff_disk = time.time() - max_age_seconds
        for stem_dir in STEMS_DIR.iterdir():
            if stem_dir.is_dir() and stem_dir.stat().st_mtime < cutoff_disk:
                shutil.rmtree(stem_dir, ignore_errors=True)
                removed += 1
    except Exception:
        pass

    return removed


def _run_extraction(job_id: str, file_path: str, job_dir: str):
    acquired = _demucs_sem.acquire(timeout=1800)  # wait up to 30 min for a slot
    if not acquired:
        _update_job(job_id, status="failed", error="Timed out waiting for an available extraction slot")
        return
    try:
        _check_disk_space(min_gb=1.5)

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

        wav_stems: dict[str, str] = {}
        for wav in stem_dir.glob("*.wav"):
            wav_stems[wav.stem] = str(wav)
            print(f"[STEMS] Job {job_id}: found {wav.name}", flush=True)

        if not wav_stems:
            raise RuntimeError(f"No WAV files found under {stem_dir}")

        # Normalize loudness then convert WAV → MP3 (saves ~10x disk space)
        mp3_stems: dict[str, str] = {}
        for stem_name, wav_path in wav_stems.items():
            print(f"[STEMS] Job {job_id}: encoding {stem_name} → MP3...", flush=True)
            mp3_path = wav_path.replace(".wav", ".mp3")
            ok = _wav_to_mp3(wav_path, mp3_path)
            if ok:
                mp3_stems[stem_name] = mp3_path
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            else:
                # Keep WAV as fallback if ffmpeg MP3 conversion fails
                mp3_stems[stem_name] = wav_path

        _update_job(job_id, status="done", stems=mp3_stems, completed=time.time())
        print(f"[STEMS] Job {job_id}: done — {list(mp3_stems.keys())}", flush=True)

        # Async cleanup of old jobs to keep disk healthy
        threading.Thread(target=cleanup_old_jobs, daemon=True).start()

    except subprocess.TimeoutExpired:
        _update_job(job_id, status="failed", error="Demucs timed out after 10 minutes")
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[STEMS] Job {job_id}: FAILED — {err}", flush=True)
        traceback.print_exc()
        _update_job(job_id, status="failed", error=err)
    finally:
        _demucs_sem.release()


def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: str = "256k") -> bool:
    """Convert WAV → MP3 with loudness normalization via ffmpeg. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", wav_path,
                "-af", "loudnorm=I=-14:LRA=11:TP=-1",
                "-codec:a", "libmp3lame", "-b:a", bitrate,
                mp3_path,
            ],
            capture_output=True,
            timeout=180,
        )
        if result.returncode == 0 and Path(mp3_path).exists():
            return True
        print(f"[STEMS] MP3 encode failed for {wav_path}: {result.stderr[-200:]}", flush=True)
        return False
    except Exception as e:
        print(f"[STEMS] MP3 encode error for {wav_path}: {e}", flush=True)
        return False


def _check_disk_space(min_gb: float = 1.5) -> None:
    """Raise if free disk space is below threshold, after attempting cleanup."""
    stat = shutil.disk_usage(str(STEMS_DIR))
    free_gb = stat.free / (1024 ** 3)
    if free_gb < min_gb:
        print(f"[STEMS] Low disk ({free_gb:.1f} GB free) — running cleanup...", flush=True)
        cleanup_old_jobs(max_age_seconds=1800)  # aggressively clean jobs > 30 min
        stat = shutil.disk_usage(str(STEMS_DIR))
        free_gb = stat.free / (1024 ** 3)
        if free_gb < 0.5:
            raise RuntimeError(
                f"Insufficient disk space ({free_gb:.1f} GB free). "
                "Please free up space on the server."
            )


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)
