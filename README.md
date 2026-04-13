# Global AI Music Studio: SaaS Production Platform

Welcome to the Global AI Music Studio. This repository contains a professional, decoupled AI Songwriting and Production platform built for scale.

## Architecture
- **Frontend**: Next.js 14 (App Router), Tailwind CSS, TypeScript, shadcn/ui.
- **Backend**: FastAPI (Python 3.12), OpenAI (GPT-4o), ElevenLabs, Suno AI.
- **Persistence**: Supabase (Auth & PostgreSQL).

## Repository Structure
- `/backend`: The core engine and FastAPI service.
- `/frontend-nextjs`: The modern SaaS dashboard.
- `/docs`: Detailed setup and deployment guides.

## Quick Start (Local)

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend-nextjs
npm install
npm run dev
```

## Environment Variables
Required in both `/backend/.env` and `/frontend-nextjs/.env`:
- `OPENAI_API_KEY`
- `GENIUS_ACCESS_TOKEN`
- `ELEVENLABS_API_KEY`
- `APIFY_API_TOKEN`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
