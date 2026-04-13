# Setup Guide: Global AI Music Studio

## Local Development Setup

### 1. Prerequisites
- python 3.12+
- node 20+
- npm or yarn

### 2. Backend Installation
1. Navigate to `/backend`.
2. Create venv: `python3 -m venv venv`.
3. Activate: `source venv/bin/activate`.
4. Install: `pip install -r requirements.txt`.
5. Environment: Ensure `.env` contains all API keys.

### 3. Frontend Installation
1. Navigate to `/frontend-nextjs`.
2. Install: `npm install`.
3. Environment: Create `.env.local` with:
   - `NEXT_PUBLIC_API_URL=http://localhost:8000`
   - `NEXT_PUBLIC_SUPABASE_URL=your_url`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY=your_key`
4. Run: `npm run dev`.

---

## EC2 Deployment Guide

### 1. Repository Sync
From local:
```bash
git add .
git commit -m "feat: SaaS transformation"
git push origin feature/nextjs-saas-ui
```

On EC2:
```bash
git pull origin feature/nextjs-saas-ui
```

### 2. Backend Service (EC2)
1. Navigate to `/backend`.
2. Update venv: `venv/bin/pip install -r requirements.txt`.
3. Run with Uvicorn (background):
```bash
pkill -f uvicorn
nohup venv/bin/uvicorn api:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
```

### 3. Frontend Service (Vercel)
1. Push `/frontend-nextjs` folder content or use a monorepo config.
2. Link to GitHub.
3. Configure environment variables in Vercel Dashboard.
4. Deploy!
