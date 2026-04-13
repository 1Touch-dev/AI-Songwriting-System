import os
import sys
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure we can import from local directories
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag.pipeline import SongwritingPipeline, STRUCTURES
from utils.genius_utils import search_genius_artists
from utils.config import (
    STYLE_STRENGTH_DEFAULT,
    TOP_K,
    GENERATION_TEMPERATURE,
    PROMPT_VERSION
)

load_dotenv()

app = FastAPI(
    title="Global AI Music Studio API",
    description="Backend API for AI Songwriting, Voice Synthesis, and Music Generation.",
    version="3.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify Vercel domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton pipeline instance
pipeline = SongwritingPipeline()

# --- Models ---

class GenerateRequest(BaseModel):
    artists: List[str]
    theme: str
    structure: str
    language: str = "English"
    gender: str = "Neutral"
    bars: int = 16
    reference_lyrics: str = ""
    num_variants: int = 1
    top_k: int = TOP_K
    temperature: float = GENERATION_TEMPERATURE
    extra_instructions: str = ""
    style_strength: float = STYLE_STRENGTH_DEFAULT
    mode: str = "Full Song"
    gen_mode: str = "generate"
    perspective_mode: str = "same"

class VoiceRequest(BaseModel):
    text: str
    voice_id: str = "JBFqnCBsd6RMkjVDRZzb"

class MusicRequest(BaseModel):
    lyrics: str
    style_tags: str
    title: str

# --- Endpoints ---

@app.get("/")
async def root():
    return {"status": "online", "version": PROMPT_VERSION}

@app.get("/search-artists")
async def search_artists(q: str = Query(..., min_length=3)):
    """Search for artists via Genius API."""
    try:
        results = search_genius_artists(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/structures")
async def get_structures():
    """Return available song structure presets."""
    return {"structures": STRUCTURES}

@app.post("/generate")
async def generate_lyrics(req: GenerateRequest):
    """Run the RAG songwriting pipeline."""
    try:
        result = pipeline.run(
            artists=req.artists,
            theme=req.theme,
            structure=req.structure,
            language=req.language,
            gender=req.gender,
            bars=req.bars,
            reference_lyrics=req.reference_lyrics,
            num_variants=req.num_variants,
            top_k=req.top_k,
            temperature=req.temperature,
            extra_instructions=req.extra_instructions,
            style_strength=req.style_strength,
            mode=req.mode,
            gen_mode=req.gen_mode,
            perspective_mode=req.perspective_mode
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-voice")
async def generate_voice(req: VoiceRequest):
    """Synthesize voice using ElevenLabs."""
    try:
        audio_bytes = pipeline.voice_gen.generate_voice(req.text, voice_id=req.voice_id)
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Voice synthesis failed.")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-music")
async def generate_music(req: MusicRequest):
    """Generate backing track using Suno AI (via Apify)."""
    try:
        urls = pipeline.music_gen.run_full_generation(
            lyrics=req.lyrics,
            style_tags=req.style_tags,
            title=req.title
        )
        return {"audio_urls": urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
