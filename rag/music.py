"""
music.py — Music generation backend.

Backends:
  suno        : sunoapi.org webhook (requires EC2 port 8765 open)
  huggingface : Facebook MusicGen via HF Inference API (synchronous fallback)

Set MUSIC_BACKEND=suno or MUSIC_BACKEND=huggingface in .env.
If Suno fails after all retries, automatically falls back to HuggingFace.
"""
import json
import os
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

SUNO_BASE_URL   = "https://api.sunoapi.org"
HF_API_URL      = "https://router.huggingface.co/hf-inference/models/facebook/musicgen-small"
CALLBACK_PORT   = int(os.getenv("SUNO_CALLBACK_PORT", "8765"))
EC2_PUBLIC_IP   = os.getenv("EC2_PUBLIC_IP", "3.239.91.199")


# ---------------------------------------------------------------------------
# Webhook handler (thread-safe via class-level lock)
# ---------------------------------------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    _lock   = threading.Lock()
    _result: dict = {}
    _event  = threading.Event()

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._result.clear()
            cls._event.clear()

    @classmethod
    def get_result(cls) -> dict:
        with cls._lock:
            return dict(cls._result)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            data   = json.loads(body.decode("utf-8"))
            with _CallbackHandler._lock:
                _CallbackHandler._result.update(data)
            _CallbackHandler._event.set()
            print(f"[MUSIC] Callback received. Keys: {list(data.keys())}", flush=True)
        except Exception as e:
            print(f"[MUSIC] Callback parse error: {e}", flush=True)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # suppress HTTP logs


# ---------------------------------------------------------------------------
# Reusable server with SO_REUSEADDR to avoid port conflicts
# ---------------------------------------------------------------------------
class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


# ---------------------------------------------------------------------------
# MusicGenerator
# ---------------------------------------------------------------------------
class MusicGenerator:
    def __init__(self):
        self.suno_key  = os.getenv("SUNO_API_KEY", "").strip()
        self.hf_key    = os.getenv("hf_key", "").strip()
        self.backend   = os.getenv("MUSIC_BACKEND", "suno")

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
    # Suno via sunoapi.org webhook
    # ------------------------------------------------------------------
    def _suno_generate(
        self, lyrics: str, style_tags: str, title: str, attempts: int
    ) -> Optional[bytes]:

        callback_url = f"http://{EC2_PUBLIC_IP}:{CALLBACK_PORT}/callback"
        api_headers  = {
            "Authorization": f"Bearer {self.suno_key}",
            "Content-Type":  "application/json",
        }
        payload = {
            "prompt":       lyrics[:3000],
            "tags":         style_tags[:200],
            "title":        title[:80],
            "instrumental": False,
            "model":        "V4",
            "customMode":   True,
            "callBackUrl":  callback_url,
        }

        for attempt in range(1, attempts + 1):
            print(f"[MUSIC] Suno attempt {attempt}/{attempts}...", flush=True)
            server = None
            try:
                # --- start webhook server ---
                _CallbackHandler.reset()
                server = _ReusableTCPServer(("0.0.0.0", CALLBACK_PORT), _CallbackHandler)
                srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
                srv_thread.start()

                # --- submit to sunoapi.org ---
                resp = requests.post(
                    f"{SUNO_BASE_URL}/api/v1/generate",
                    headers=api_headers,
                    json=payload,
                    timeout=30,
                )
                resp_data = resp.json()

                if resp_data.get("code") != 200:
                    print(f"[MUSIC] Suno submit error: {resp_data.get('msg')}", flush=True)
                    continue

                task_id = resp_data.get("data", {}).get("taskId", "?")
                print(f"[MUSIC] Task {task_id} queued. Waiting for callback (max 300s)...", flush=True)

                # --- wait for webhook callback ---
                got_callback = _CallbackHandler._event.wait(timeout=300)

                if not got_callback:
                    print("[MUSIC] Callback timeout — port 8765 not reached by sunoapi.org.", flush=True)
                    continue

                # --- parse callback ---
                result = _CallbackHandler.get_result()
                # Structure: {"code":200, "data":{"callbackType":"complete","data":[{...}]}}
                inner  = result.get("data", {})
                tracks = inner.get("data", []) if isinstance(inner, dict) else []

                audio_url = None
                for track in tracks:
                    # Prefer CDN URL (more stable) over temp URL
                    audio_url = (
                        track.get("source_audio_url")
                        or track.get("audio_url")
                    )
                    if audio_url:
                        print(f"[MUSIC] Audio URL: {audio_url}", flush=True)
                        break

                if not audio_url:
                    print(f"[MUSIC] No audio_url in callback. Data keys: {list(inner.keys())}", flush=True)
                    continue

                # --- download audio ---
                dl = requests.get(audio_url, timeout=60)
                if dl.status_code != 200:
                    print(f"[MUSIC] Download failed: HTTP {dl.status_code}", flush=True)
                    continue

                audio_bytes = dl.content
                if len(audio_bytes) < 1000:
                    print(f"[MUSIC] Downloaded audio too small: {len(audio_bytes)} bytes", flush=True)
                    continue

                print(f"[MUSIC] Suno success: {len(audio_bytes):,} bytes", flush=True)
                return audio_bytes

            except Exception as e:
                print(f"[MUSIC] Suno attempt {attempt} exception: {e}", flush=True)
                time.sleep(5)

            finally:
                if server:
                    server.shutdown()

        return None

    # ------------------------------------------------------------------
    # HuggingFace MusicGen (synchronous fallback)
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
                    print(f"[MUSIC] HF response too small: {len(audio)} bytes")

                elif resp.status_code == 503:
                    wait = min(float(resp.json().get("estimated_time", 20)), 30)
                    print(f"[MUSIC] HF model loading, waiting {wait:.0f}s...")
                    time.sleep(wait)

                else:
                    print(f"[MUSIC] HF error {resp.status_code}: {resp.text[:200]}")

            except Exception as e:
                print(f"[MUSIC] HF attempt {attempt} failed: {e}")
                time.sleep(5)

        print("[MUSIC] HuggingFace generation exhausted.")
        return None
