import os
import sys
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Response, Query, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from sqlalchemy.orm import Session

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

# Custom Auth Modules
from database import get_db, init_db
from models import User, Song
from auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    get_current_user
)

load_dotenv()

app = FastAPI(
    title="Global AI Music Studio API",
    description="Backend API with Custom JWT Auth for AI Songwriting.",
    version="3.1.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton pipeline instance — initialized on startup, not at import time
pipeline: SongwritingPipeline = None

@app.on_event("startup")
def on_startup():
    global pipeline
    init_db()
    pipeline = SongwritingPipeline()

# --- Pydantic Models ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

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

class SongSaveRequest(BaseModel):
    theme: str
    artists: List[str]
    lyrics: str
    audio_url: Optional[str] = None
    music_url: Optional[str] = None

# --- Auth Endpoints ---

@app.post("/auth/signup", response_model=UserResponse)
async def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user_in.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# --- Song History Endpoints ---

@app.post("/songs/save")
async def save_song(req: SongSaveRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_song = Song(
        user_id=current_user.id,
        theme=req.theme,
        artists=",".join(req.artists),
        lyrics=req.lyrics,
        audio_url=req.audio_url,
        music_url=req.music_url
    )
    db.add(new_song)
    db.commit()
    return {"status": "success", "song_id": new_song.id}

@app.get("/songs")
async def get_songs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    songs = db.query(Song).filter(Song.user_id == current_user.id).order_by(Song.created_at.desc()).all()
    return songs

# --- Work Endpoints (Protected) ---

@app.get("/search-artists")
async def search_artists(q: str = Query(..., min_length=3), current_user: User = Depends(get_current_user)):
    try:
        results = search_genius_artists(q)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate")
async def generate_lyrics(req: GenerateRequest, current_user: User = Depends(get_current_user)):
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
async def generate_voice(req: VoiceRequest, current_user: User = Depends(get_current_user)):
    try:
        audio_bytes = pipeline.voice_gen.generate_voice(req.text, voice_id=req.voice_id)
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="Voice synthesis failed.")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-music")
async def generate_music(req: MusicRequest, current_user: User = Depends(get_current_user)):
    try:
        urls = pipeline.music_gen.run_full_generation(
            lyrics=req.lyrics,
            style_tags=req.style_tags,
            title=req.title
        )
        return {"audio_urls": urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Public Endpoints ---

@app.get("/health")
async def health():
    return {"status": "online", "version": PROMPT_VERSION}

@app.get("/structures")
async def get_structures():
    return {"structures": STRUCTURES}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
