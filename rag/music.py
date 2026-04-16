"""
music.py — Music generation backend.

Backends:
  suno        : sunoapi.org (polling mode, full song with vocals)
  huggingface : Facebook MusicGen via HF Inference API (synchronous fallback)

Set MUSIC_BACKEND=suno or MUSIC_BACKEND=huggingface in .env.
If Suno fails after all retries, automatically falls back to HuggingFace.

Suno generates a FULL SONG (vocals + music) — not instrumental.
ElevenLabs (voice.py) generates vocal-only TTS output.
These are kept SEPARATE — no mixing is performed here.
"""
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

SUNO_BASE_URL   = "https://api.sunoapi.org"
HF_API_URL      = "https://router.huggingface.co/hf-inference/models/facebook/musicgen-small"
EC2_PUBLIC_IP   = os.getenv("EC2_PUBLIC_IP", "3.239.91.199")
CALLBACK_PORT   = int(os.getenv("SUNO_CALLBACK_PORT", "8765"))


class MusicGenerator:
    def __init__(self):
        self.suno_key = os.getenv("SUNO_API_KEY", "").strip()
        self.hf_key   = os.getenv("hf_key", "").strip()
        self.backend  = os.getenv("MUSIC_BACKEND", "suno")

        if self.backend == "suno" and not self.suno_key:
            print("[MUSIC] SUNO_API_KEY missing → falling back to HuggingFace.")
            self.backend = "huggingface"

        if self.backend == "huggingface" and not self.hf_key:
            print("[MUSIC] hf_key missing. Music generation disabled.")
            self.backend = "disabled"

        self.enabled = self.backend != "disabled"
        print(f"[MUSIC] Backend active: {self.backend}", flush=True)

    # ------------------------------------------------------------------
    # Public API — always returns bytes or None
    # ------------------------------------------------------------------
    def run_full_generation(
        self, lyrics: str, style_tags: str, title: str
    ) -> Optional[bytes]:
        if not self.enabled:
            return None

        result = None

        if self.backend == "suno":
            result = self._suno_generate(lyrics, style_tags, title, attempts=2)
            if result is None and self.hf_key:
                print("[MUSIC] Suno failed → falling back to HuggingFace.", flush=True)
                result = self._hf_generate(style_tags, title, attempts=2)

        elif self.backend == "huggingface":
            result = self._hf_generate(style_tags, title, attempts=2)

        if result:
            print(f"[MUSIC] Final audio: {len(result):,} bytes", flush=True)
        else:
            print("[MUSIC] All backends failed.", flush=True)

        return result

    # ------------------------------------------------------------------
    # Suno via sunoapi.org — polling mode (no webhook required)
    # Generates FULL SONG: vocals + music (instrumental=False)
    # ------------------------------------------------------------------
    def _suno_generate(
        self, lyrics: str, style_tags: str, title: str, attempts: int
    ) -> Optional[bytes]:
        headers = {
            "Authorization": f"Bearer {self.suno_key}",
            "Content-Type":  "application/json",
        }
        # sunoapi.org requires callBackUrl for validation even in polling mode.
        # We provide the EC2 address but rely on polling — not the webhook — for results.
        callback_url = f"http://{EC2_PUBLIC_IP}:{CALLBACK_PORT}/callback"
        payload = {
            "prompt":       lyrics[:3000],
            "tags":         style_tags[:200],
            "title":        title[:80],
            "instrumental": False,   # Full song — vocals + music
            "model":        "V4",
            "customMode":   True,
            "callBackUrl":  callback_url,
        }

        for attempt in range(1, attempts + 1):
            print(f"[MUSIC] Suno attempt {attempt}/{attempts} (polling mode)...", flush=True)
            try:
                # --- submit job ---
                resp = requests.post(
                    f"{SUNO_BASE_URL}/api/v1/generate",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                resp_data = resp.json()

                if resp_data.get("code") != 200:
                    msg = resp_data.get("msg", "unknown error")
                    print(f"[MUSIC] Suno submit error: {msg}", flush=True)
                    # Credit exhaustion is terminal — no point retrying
                    if any(kw in msg.lower() for kw in ("insufficient", "credits", "credit")):
                        print("[MUSIC] Suno credits exhausted — skipping retries.", flush=True)
                        return None
                    time.sleep(5)
                    continue

                task_id = resp_data.get("data", {}).get("taskId", "")
                if not task_id:
                    print("[MUSIC] Suno: no taskId in response.", flush=True)
                    continue

                print(f"[MUSIC] Task {task_id} submitted. Polling...", flush=True)

                # --- poll until complete (max 5 min) ---
                audio_url = self._poll_suno(task_id, headers, timeout=300)
                if not audio_url:
                    print("[MUSIC] Suno polling failed / timed out.", flush=True)
                    continue

                # --- download audio ---
                print(f"[MUSIC] Downloading audio from Suno CDN...", flush=True)
                dl = requests.get(audio_url, timeout=120)
                if dl.status_code != 200:
                    print(f"[MUSIC] Download failed: HTTP {dl.status_code}", flush=True)
                    continue

                audio_bytes = dl.content
                if len(audio_bytes) < 1000:
                    print(f"[MUSIC] Audio too small ({len(audio_bytes)} bytes) — treating as failure.", flush=True)
                    continue

                print(f"[MUSIC] Suno success: {len(audio_bytes):,} bytes", flush=True)
                return audio_bytes

            except Exception as e:
                print(f"[MUSIC] Suno attempt {attempt} exception: {e}", flush=True)
                time.sleep(5)

        return None

    # ------------------------------------------------------------------
    # Poll sunoapi.org until task succeeds.
    #
    # Actual response structure (discovered via live testing):
    #   data["data"]["status"]                              → task status
    #   data["data"]["response"]["sunoData"][n]["sourceAudioUrl"]
    #   data["data"]["response"]["sunoData"][n]["audioUrl"]
    #
    # Status values: "PENDING" → "FIRST_SUCCESS" → "SUCCESS"
    # "FIRST_SUCCESS" means ≥1 track is ready — we can use it immediately.
    # ------------------------------------------------------------------
    def _poll_suno(
        self, task_id: str, headers: dict, timeout: int = 300
    ) -> Optional[str]:
        deadline      = time.time() + timeout
        poll_interval = 10  # seconds between polls

        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{SUNO_BASE_URL}/api/v1/generate/record-info",
                    headers=headers,
                    params={"taskId": task_id},
                    timeout=15,
                )
                data = resp.json()

                if data.get("code") != 200:
                    print(f"[MUSIC] Poll error: {data.get('msg', 'unknown')}", flush=True)
                    time.sleep(poll_interval)
                    continue

                outer  = data.get("data", {})
                status = outer.get("status", "PENDING")
                print(f"[MUSIC] Polling... status={status}", flush=True)

                if status in ("FIRST_SUCCESS", "SUCCESS", "complete"):
                    # Traverse: data["data"]["response"]["sunoData"]
                    response   = outer.get("response", {})
                    suno_data  = response.get("sunoData", [])

                    for track in suno_data:
                        audio_url = (
                            track.get("sourceAudioUrl")
                            or track.get("audioUrl")
                            or track.get("streamAudioUrl")
                        )
                        if audio_url:
                            print(f"[MUSIC] Task {status}. URL acquired.", flush=True)
                            return audio_url

                    print(f"[MUSIC] {status} but no audio URL yet — continuing poll.", flush=True)

                elif status in ("FAILED", "failed"):
                    err = outer.get("errorMessage") or outer.get("errorCode", "unknown")
                    print(f"[MUSIC] Suno task failed: {err}", flush=True)
                    return None

            except Exception as e:
                print(f"[MUSIC] Poll exception: {e}", flush=True)

            time.sleep(poll_interval)

        print("[MUSIC] Suno polling timed out.", flush=True)
        return None

    # ------------------------------------------------------------------
    # HuggingFace MusicGen (synchronous fallback — instrumental only)
    # ------------------------------------------------------------------
    def _hf_generate(
        self, style_tags: str, title: str, attempts: int
    ) -> Optional[bytes]:
        prompt  = f"{style_tags}. {title}."
        headers = {"Authorization": f"Bearer {self.hf_key}"}
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 512}}

        for attempt in range(1, attempts + 1):
            try:
                print(f"[MUSIC] HuggingFace attempt {attempt}/{attempts}...", flush=True)
                resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=120)

                if resp.status_code == 200:
                    audio = resp.content
                    if len(audio) > 1000:
                        print(f"[MUSIC] HuggingFace: {len(audio):,} bytes", flush=True)
                        return audio
                    print(f"[MUSIC] HF response too small: {len(audio)} bytes", flush=True)

                elif resp.status_code == 503:
                    wait = min(float(resp.json().get("estimated_time", 20)), 30)
                    print(f"[MUSIC] HF model loading, waiting {wait:.0f}s...", flush=True)
                    time.sleep(wait)

                else:
                    print(f"[MUSIC] HF error {resp.status_code}: {resp.text[:200]}", flush=True)

            except Exception as e:
                print(f"[MUSIC] HF attempt {attempt} failed: {e}", flush=True)
                time.sleep(5)

        print("[MUSIC] HuggingFace generation exhausted.", flush=True)
        return None
