import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# sunoapi.org is async/webhook-only.
# To enable it:
#   1. Open port 8765 TCP inbound in the EC2 security group
#   2. Set SUNO_API_KEY and SUNO_ENABLED=true in .env
#   3. Swap the backend constant below to "suno"
#
# Current backend: HuggingFace MusicGen (synchronous, no webhook needed).
# ---------------------------------------------------------------------------

MUSIC_BACKEND = os.getenv("MUSIC_BACKEND", "huggingface")  # "huggingface" or "suno"

HF_API_URL = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
SUNO_BASE_URL = "https://api.sunoapi.org"


class MusicGenerator:
    """
    Music generation backend.
    - huggingface: Facebook MusicGen via HF Inference API (default, synchronous)
    - suno: sunoapi.org (requires port 8765 open on EC2 for webhook)
    """

    def __init__(self):
        self.hf_key = os.getenv("hf_key", "").strip()
        self.suno_key = os.getenv("SUNO_API_KEY", "").strip()
        self.backend = MUSIC_BACKEND

        if self.backend == "suno" and not self.suno_key:
            print("[MUSIC] SUNO_API_KEY missing, falling back to HuggingFace.")
            self.backend = "huggingface"

        if self.backend == "huggingface" and not self.hf_key:
            print("[MUSIC] hf_key missing. Music generation disabled.")
            self.backend = "disabled"

        self.enabled = self.backend != "disabled"
        print(f"[MUSIC] Backend: {self.backend}")

    # ------------------------------------------------------------------
    # Public API — returns audio BYTES (not a URL)
    # ------------------------------------------------------------------
    def run_full_generation(self, lyrics: str, style_tags: str, title: str, attempts: int = 2) -> Optional[bytes]:
        if not self.enabled:
            return None

        if self.backend == "huggingface":
            return self._hf_generate(style_tags, title, attempts)
        if self.backend == "suno":
            return self._suno_generate(lyrics, style_tags, title, attempts)
        return None

    # ------------------------------------------------------------------
    # HuggingFace MusicGen (synchronous)
    # ------------------------------------------------------------------
    def _hf_generate(self, style_tags: str, title: str, attempts: int) -> Optional[bytes]:
        prompt = f"{style_tags}. {title}."
        headers = {"Authorization": f"Bearer {self.hf_key}"}
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 512}}

        for attempt in range(1, attempts + 1):
            try:
                print(f"[MUSIC] HuggingFace MusicGen attempt {attempt}/{attempts}...")
                resp = requests.post(HF_API_URL, headers=headers, json=payload, timeout=120)

                if resp.status_code == 200:
                    audio = resp.content
                    if len(audio) > 1000:
                        print(f"[MUSIC] Generated {len(audio)} bytes of audio.")
                        return audio
                    print(f"[MUSIC] Response too small ({len(audio)} bytes), retrying...")

                elif resp.status_code == 503:
                    wait = resp.json().get("estimated_time", 20)
                    print(f"[MUSIC] Model loading, waiting {wait}s...")
                    time.sleep(min(float(wait), 30))

                else:
                    print(f"[MUSIC] HF error {resp.status_code}: {resp.text[:200]}")

            except Exception as e:
                print(f"[MUSIC] HF attempt {attempt} failed: {e}")
                time.sleep(5)

        print("[MUSIC] HuggingFace generation exhausted.")
        return None

    # ------------------------------------------------------------------
    # sunoapi.org (webhook-based — requires port 8765 open in EC2 SG)
    # ------------------------------------------------------------------
    def _suno_generate(self, lyrics: str, style_tags: str, title: str, attempts: int) -> Optional[bytes]:
        import threading
        import json
        from http.server import HTTPServer, BaseHTTPRequestHandler

        EC2_IP = os.getenv("EC2_PUBLIC_IP", "3.239.91.199")
        CALLBACK_PORT = 8765
        callback_url = f"http://{EC2_IP}:{CALLBACK_PORT}/callback"

        class Handler(BaseHTTPRequestHandler):
            result = {}
            event = threading.Event()

            def do_POST(self):
                try:
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    Handler.result.update(json.loads(body.decode()))
                    Handler.event.set()
                except Exception:
                    pass
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        headers = {"Authorization": f"Bearer {self.suno_key}", "Content-Type": "application/json"}
        payload = {
            "prompt": lyrics[:3000],
            "tags": style_tags[:200],
            "title": title[:80],
            "instrumental": False,
            "model": "V4",
            "customMode": True,
            "callBackUrl": callback_url,
        }

        for attempt in range(1, attempts + 1):
            try:
                Handler.result.clear()
                Handler.event.clear()

                server = HTTPServer(("0.0.0.0", CALLBACK_PORT), Handler)
                t = threading.Thread(target=server.serve_forever, daemon=True)
                t.start()

                try:
                    resp = requests.post(f"{SUNO_BASE_URL}/api/v1/generate",
                                         headers=headers, json=payload, timeout=30)
                    data = resp.json()
                    if data.get("code") != 200:
                        print(f"[MUSIC] Suno API error: {data.get('msg')}")
                        continue

                    print(f"[MUSIC] Task queued: {data.get('data', {}).get('taskId')}. Waiting for callback...")
                    got = Handler.event.wait(timeout=300)

                    if got:
                        # Callback structure: {"code":200,"data":{"callbackType":"complete","data":[{"audio_url":...}]}}
                        inner = Handler.result.get("data", {})
                        tracks = inner.get("data", []) if isinstance(inner, dict) else []
                        audio_url = None
                        for track in tracks:
                            audio_url = track.get("audio_url") or track.get("source_audio_url")
                            if audio_url:
                                break
                        if audio_url:
                            print(f"[MUSIC] Downloading from {audio_url}")
                            r = requests.get(audio_url, timeout=60)
                            if r.status_code == 200 and len(r.content) > 1000:
                                print(f"[MUSIC] Suno success: {len(r.content)} bytes")
                                return r.content
                        else:
                            print(f"[MUSIC] Callback received but no audio_url found. Keys: {list(Handler.result.keys())}")
                    else:
                        print("[MUSIC] Callback timed out. Check port 8765 in EC2 security group.")

                finally:
                    server.shutdown()

            except Exception as e:
                print(f"[MUSIC] Suno attempt {attempt} error: {e}")
                time.sleep(5)

        return None
