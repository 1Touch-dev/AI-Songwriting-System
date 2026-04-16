# SonicFlow Studio v3

An AI-powered, full-stack music production platform. Enter a theme and an artist style — get back a complete song with vocals and music in one click.

**Live at:** `http://3.239.91.199:3001`  |  **API:** `http://3.239.91.199:8000`

---

## What It Does

1. Writes original song lyrics in the style of any real-world artist using a RAG pipeline (FAISS + BM25 retrieval → GPT-4o generation).
2. Synthesises a vocal track from those lyrics via ElevenLabs Multilingual v2.
3. Generates a full AI song (music + singing) via Suno AI v4.
4. Saves every production to a persistent Project Library — browse, reload, or delete past tracks from the Library page.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 14 (App Router) + Tailwind CSS |
| **Backend** | FastAPI + Uvicorn (Python 3.11) |
| **Lyrics AI** | OpenAI GPT-4o |
| **Lyric Retrieval** | FAISS vector index + BM25 hybrid search |
| **Voice Synthesis** | ElevenLabs Multilingual v2 |
| **Music Generation** | Suno AI v4 via sunoapi.org |
| **Music Fallback** | HuggingFace MusicGen (facebook/musicgen-small) |
| **Deployment** | AWS EC2 (Ubuntu) + systemd |
| **Storage** | File-based JSON (`data/projects.json`) |

---

## Credentials

| Field | Value |
|---|---|
| URL | `http://3.239.91.199:3001` |
| Email | `admin@studio.com` |
| Password | `admins` |

---

## Quick Start (Local)

```bash
# 1. Activate venv
source venv/bin/activate

# 2. Start the API (port 8000)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start the frontend (port 3001)
cd frontend-nextjs
npm run dev -- --port 3001

# 4. Open http://localhost:3001
```

---

## Project Structure

```
.
├── api/
│   └── main.py                  # FastAPI backend — all REST endpoints
├── rag/
│   ├── pipeline.py              # End-to-end RAG orchestrator
│   ├── prompt_builder.py        # GPT-4o prompt assembly + output template
│   ├── retriever.py             # FAISS + BM25 hybrid retrieval
│   ├── generator.py             # OpenAI generation wrapper
│   ├── music.py                 # Suno AI + HuggingFace music generation
│   ├── voice.py                 # ElevenLabs voice synthesis
│   └── validator.py             # Bars enforcer + chorus validator
├── frontend-nextjs/
│   ├── app/
│   │   ├── page.tsx             # Main Studio page
│   │   ├── library/page.tsx     # Project Library
│   │   └── login/page.tsx       # Auth
│   ├── lib/
│   │   ├── api.ts               # Axios client + API calls
│   │   └── types.ts             # TypeScript types
│   └── components/
│       └── GenerationStatus.tsx # Real-time pipeline status panel
├── frontend/
│   └── app.py                   # Legacy Streamlit UI (kept for reference)
├── scripts/
│   ├── 01_build_dataset.py      # Download + clean artist lyrics from Genius
│   ├── 02_label_songs.py        # LLM-label structure + theme per song
│   └── 03_build_index.py        # Build FAISS + BM25 index
├── utils/
│   ├── genius_utils.py          # Genius API artist search
│   └── config.py                # Paths and constants
├── data/
│   ├── faiss_index/             # FAISS binary index + metadata
│   ├── projects.json            # Saved projects (created at runtime)
│   └── processed/               # Cleaned + labeled lyric chunks
├── docs/
│   ├── SonicFlow_Studio_Manual.md   # Full user manual (Markdown)
│   └── SonicFlow_Studio_Manual.pdf  # Full user manual (PDF)
└── .env                         # API keys (never commit)
```

---

## Environment Variables (`.env`)

```bash
OPENAI_API_KEY=...
ELEVENLABS_API_KEY=...
SUNO_API_KEY=...
GENIUS_ACCESS_TOKEN=...
EC2_PUBLIC_IP=3.239.91.199
```

---

## EC2 Deployment

Services are managed by systemd. SSH into the server then:

```bash
# Check service status
sudo systemctl status sonicflow-api
sudo systemctl status sonicflow-nextjs

# Restart services
sudo systemctl restart sonicflow-api
sudo systemctl restart sonicflow-nextjs

# View live logs
journalctl -u sonicflow-api -f
journalctl -u sonicflow-nextjs -f

# Pull latest code and restart
cd ~/AI-Songwriting-System
git pull
sudo systemctl restart sonicflow-api
cd frontend-nextjs && npm run build
sudo systemctl restart sonicflow-nextjs
```

---

## Building the FAISS Index (one-time setup)

```bash
# Step 1 — Download and clean lyrics (~20 min)
python scripts/01_build_dataset.py

# Step 2 — LLM-label structure + theme (~30–60 min, ~$5–20 OpenAI cost)
python scripts/02_label_songs.py

# Step 3 — Build FAISS + BM25 index (~10–20 min)
python scripts/03_build_index.py
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/login` | Authenticate → returns Bearer token |
| `POST` | `/generate` | Run full pipeline → lyrics + audio (base64) |
| `GET` | `/artists/search?q=...` | Autocomplete artist names |
| `GET` | `/projects` | List all saved projects (newest first) |
| `POST` | `/projects` | Save a new project |
| `DELETE` | `/projects/{id}` | Delete a project |
| `GET` | `/health` | Health check |

---

## Documentation

The full user manual is in `docs/`:

- `docs/SonicFlow_Studio_Manual.md` — Markdown version
- `docs/SonicFlow_Studio_Manual.pdf` — PDF version

Covers: every UI control, how each setting works, step-by-step walkthroughs, system architecture, end-to-end flow diagram, glossary, and troubleshooting.

---

## Branch

`feature/final-production-hardening`
