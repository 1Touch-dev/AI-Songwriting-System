import re
import sys
import os
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from utils.config import (
    CHORUS_VALIDATION_ENABLED,
    TARGET_ARTISTS,
    STYLE_STRENGTH_DEFAULT,
    GENERATION_MODEL
)
from rag.pipeline import SongwritingPipeline, STRUCTURES
from utils.genius_utils import search_genius_artists

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GLOBAL AI MUSIC PLATFORM",
    page_icon="🎼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Premium UI Styling ─────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .main { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #f8fafc; }
    
    .stButton>button { 
        width: 100%; border-radius: 12px; font-weight: 600; 
        background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%); 
        border: none; color: white; transition: all 0.3s ease;
        height: 3rem;
    }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(99, 102, 241, 0.4); }
    
    .metric-card { 
        background: rgba(30, 41, 59, 0.7); 
        padding: 20px; border-radius: 16px; 
        border: 1px solid rgba(148, 163, 184, 0.1);
        backdrop-filter: blur(10px);
    }
    
    .lyrics-container {
        background: rgba(15, 23, 42, 0.5);
        border-radius: 12px;
        padding: 25px;
        border: 1px solid rgba(99, 102, 241, 0.2);
        line-height: 1.8;
        font-size: 1.1rem;
    }
    
    .pipeline-step {
        display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
        color: #94a3b8;
    }
    .pipeline-step.active { color: #6366f1; font-weight: 600; }
    .pipeline-step.done { color: #10b981; }
</style>
""", unsafe_allow_html=True)

# ── Pipeline Instance ──────────────────────────────────────────────────────
@st.cache_resource
def get_pipeline():
    return SongwritingPipeline()

# ── Session State ──────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "selected_artist_name" not in st.session_state:
    st.session_state.selected_artist_name = ""

# ── Utility: Status Pipeline ───────────────────────────────────────────────
def handle_production_flow(pipeline, params, enable_voice, enable_music, uploaded_inst):
    with st.status("🚀 IGNITING PRODUCTION...", expanded=True) as status:
        st.write("🧠 Synthesizing Lyrical Theme...")
        # Step 1: Lyrics Generation
        res = pipeline.run(**params)
        
        st.write("✍️ Drafting Artistic Content & Enforcing Bars...")
        # Validation happens inside pipeline.run
        
        # Step 2: Voice Synthesis
        voice_audio = None
        if enable_voice:
            st.write("🎤 Vocal Synthesis (ElevenLabs)...")
            voice_audio = pipeline.voice_gen.generate_voice(res["lyrics"])
        
        # Step 3: Music Production
        music_audio = None
        if enable_music and not uploaded_inst:
            st.write("🎵 Music Production (Suno AI)...")
            music_audio = pipeline.music_gen.run_full_generation(
                res["lyrics"],
                f"{params['artists'][0]} style, {params['language']}",
                res["theme"]
            )
            if music_audio:
                st.write(f"✅ Music: {len(music_audio):,} bytes")
            else:
                st.write("⚠️ Music generation failed")

        # Step 4: LLM Analysis (AI Insights)
        # NOTE: Mixing is disabled. Voice (ElevenLabs) and Music (Suno) are independent outputs.
        st.write("🔍 Running Lyrical Analysis (AI Insights)...")
        analysis_res = pipeline.run(
            artists=params["artists"],
            theme=params["theme"],
            structure=params["structure"],
            reference_lyrics=res["lyrics"],
            analysis_mode=True
        )

        status.update(label="✅ PRODUCTION COMPLETE", state="complete", expanded=False)

    if not voice_audio:
        st.error("⚠️ Vocal Synthesis Failed. Check ElevenLabs API Key.")
    if enable_music and not uploaded_inst and not music_audio:
        st.warning("⚠️ Music generation failed — check Suno credits or API.")
    if not analysis_res.get("analysis"):
        st.warning("⚠️ AI Insights could not be completed.")

    res["_voice"] = voice_audio
    res["_music"] = music_audio
    res["_analysis"] = analysis_res.get("analysis")
    res["_timestamp"] = datetime.now().strftime("%H:%M:%S")
    return res

# ── Sidebar: Artist & Genre ────────────────────────────────────────────────
with st.sidebar:
    # Removed broken image reference
    st.title("👨‍🎨 Studio Settings")
    
    # Genius Autocomplete Logic (V3 Polish)
    query = st.text_input("Artist Search", placeholder="Type artist name...", key="artist_query_input")

    suggestions = []
    if query and len(query) >= 3:
        time.sleep(0.2)  # prevent API spam
        suggestions = search_genius_artists(query)

    if suggestions:
        # Use selectbox as it supports typing + filtering natively
        selected_artist = st.selectbox(
            "Suggestions",
            options=suggestions,
            index=0
        )
        st.session_state.selected_artist_name = selected_artist
    else:
        st.session_state.selected_artist_name = query

    st.divider()
    
    with st.expander("🎨 Creative Controls", expanded=True):
        temperature = st.slider("Creativity (Temp)", 0.5, 1.2, 0.85, 0.05)
        style_strength = st.slider("Style Strength", 0.0, 1.0, float(STYLE_STRENGTH_DEFAULT), 0.05)
        language = st.selectbox("Global Language", 
            ["English", "Spanish", "French", "German", "Hindi", "Arabic", "Portuguese", "Japanese", "Korean", "Chinese"])
        gender = st.selectbox("Vocal Perspective", ["Neutral", "Male", "Female"])
        bars = st.select_slider("Song Length (Bars)", options=[4, 8, 16, 32], value=16)
        num_variants = st.select_slider("Creative Variants", options=[1, 3, 5], value=3)

    with st.expander("🎹 Multimodal Engines", expanded=True):
        enable_voice = st.checkbox("Enable Voice Synthesis", value=True)
        enable_music = st.checkbox("Enable Music Production", value=True)
        uploaded_inst = st.file_uploader("Upload Instrumental (Voice-Only Mode)", type=["mp3", "wav"])

    st.divider()
    if st.button("🗑️ Clear Active Project"):
        st.session_state.history = []
        st.rerun()

# ── Main Project Hub ───────────────────────────────────────────────────────
st.title("🎧 Global AI Music Studio")
st.caption("AI Songwriting • Voice Synthesis • Music Generation")

col_main, col_preview = st.columns([1.2, 1], gap="large")

with col_main:
    st.subheader("1. Theme & Creative Mode")
    theme = st.text_input("Project Theme / Emotional Blueprint", placeholder="nostalgic late night drive in Seoul")
    
    r1, r2 = st.columns(2)
    gen_mode = r1.selectbox("Creative Process", ["Generate New", "Continue Story", "Remix Style"], index=0)
    perspective = r2.selectbox("Writing Perspective", ["Same POV", "Opposite Empathy", "Response Verse"], index=0)
    
    st.subheader("2. Reference Lyrics (Context)")
    ref_lyrics = st.text_area("Paste original lyrics (optional - used for Continue/Remix)", placeholder="Paste existing lyrics here...", height=150)
    
    st.subheader("3. Structure & Preset")
    s_choice = st.selectbox("Structure Flow", list(STRUCTURES.keys()), index=0)
    
    st.divider()
    if st.button("🚀 IGNITE PRODUCTION", type="primary"):
        if not st.session_state.selected_artist_name and not theme:
            st.warning("Please define Artist or Theme.")
        else:
            pipeline = get_pipeline()
            
            # Translate Mode & Perspective for Backend
            mode_map = {"Generate New": "generate", "Continue Story": "continue", "Remix Style": "remix"}
            persp_map = {"Same POV": "same", "Opposite Empathy": "opposite", "Response Verse": "response"}
            
            params = {
                "artists": [st.session_state.selected_artist_name] if st.session_state.selected_artist_name else ["Drake"],
                "theme": theme,
                "structure": STRUCTURES[s_choice],
                "language": language,
                "gender": gender,
                "bars": bars,
                "reference_lyrics": ref_lyrics,
                "num_variants": num_variants,
                "temperature": temperature,
                "style_strength": style_strength,
                "gen_mode": mode_map[gen_mode],
                "perspective_mode": persp_map[perspective]
            }
            
            res = handle_production_flow(pipeline, params, enable_voice, enable_music, uploaded_inst)
            st.session_state.history.insert(0, res)

with col_preview:
    if not st.session_state.history:
        st.info("👋 Studio is ready. Define your theme on the left to begin.")
        st.image("https://images.unsplash.com/photo-1470225620780-dba8ba36b745?q=80&w=1000", caption="Global AI Music Engine Active", use_container_width=True)
    else:
        res = st.session_state.history[0]
        st.subheader(f"✨ Latest Project: {res['_timestamp']}")
        
        # Multimodal Audio Players (independent — no mixing)
        with st.expander("🔊 Production Playback", expanded=True):
            ts = res["_timestamp"]

            # ── Debug ─────────────────────────────────────────────────
            voice = res.get("_voice")
            music = res.get("_music")
            st.write("VOICE:", len(voice) if voice else 0)
            st.write("MUSIC:", len(music) if music else 0)
            st.divider()

            # ── Vocal Output — ElevenLabs TTS ─────────────────────────
            if voice:
                st.write("🎙️ **Vocal Output (ElevenLabs)**")
                st.audio(voice, format="audio/mpeg")
                st.download_button("📥 Download Vocal", voice,
                                   file_name=f"voice_{ts}.mp3", mime="audio/mpeg",
                                   key="dl_voice")
            else:
                st.error("Vocal generation failed — check ElevenLabs API key.")

            st.divider()

            # ── Full Song Output — Suno AI (vocals + music) ───────────
            if music:
                st.write("🎵 **Full Song Output (Suno AI)**")
                st.audio(music, format="audio/mpeg")
                st.download_button("📥 Download Full Song", music,
                                   file_name=f"music_{ts}.mp3", mime="audio/mpeg",
                                   key="dl_music")
            else:
                st.warning("Music generation failed — check Suno credits or API.")

            # ── Uploaded instrumental ─────────────────────────────────
            if uploaded_inst:
                st.divider()
                st.write("🎹 **Uploaded Instrumental**")
                st.audio(uploaded_inst)

        # Tabs for Content & Analysis
        tab_lyrics, tab_analysis, tab_variants, tab_stats = st.tabs(["📝 Final Lyrics", "💡 AI Insights", "🌈 Variants", "📊 Session Stats"])
        
        with tab_lyrics:
            st.markdown(f"<div class='lyrics-container'>{re.sub(r'(\[[^\]]+\])', r'**\1**', res['lyrics']).replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

        with tab_analysis:
            st.subheader("💡 AI Insights")
            st.json(res.get("_analysis"))
        
        with tab_variants:
            v_tabs = st.tabs([f"Variant {chr(65+i)}" for i in range(len(res["versions"]))])
            for i, v_tab in enumerate(v_tabs):
                with v_tab:
                    st.caption(f"Style Fidelity Score: {res['versions'][i]['style_fidelity']:.3f}")
                    st.markdown(res["versions"][i]["lyrics"].replace("\n", "\n\n"))

        with tab_stats:
            c1, c2 = st.columns(2)
            c1.metric("Retrieval Quality", f"{res.get('retrieval_quality', 0):.3f}")
            c2.metric("Latency", f"{res.get('latency_ms', 0)/1000:.1f}s")
            st.json(res.get("retrieval_diagnostics", {}))

# ── Footer ───────────────────────────────────────────────────────────────
st.divider()
st.caption("AI Songwriting System V3 | Production Mode | Sync: Locally + EC2")
