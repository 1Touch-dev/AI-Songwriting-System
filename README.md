# Global AI Music Studio: SaaS Production Platform

Welcome to the Global AI Music Studio. This repository contains a professional, decoupled AI Songwriting and Production platform built for scale.

## Architecture
- **Frontend**: Next.js 14 (App Router), Tailwind CSS, TypeScript, shadcn/ui.
- **Backend**: FastAPI (Python 3.12), OpenAI (GPT-4o), ElevenLabs, Suno AI.
- **Authentication**: Custom JWT with Stateless Tokens.
- **Database**: Local SQLite (`backend/users.db`) for Auth and History.

## Repository Structure
- `/backend`: The core engine and FastAPI service with JWT protection.
- `/frontend-nextjs`: The modern SaaS dashboard with integrated Auth flows.
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
- `JWT_SECRET_KEY` (Required for Backend Auth)
