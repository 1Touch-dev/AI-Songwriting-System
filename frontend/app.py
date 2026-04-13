"""
AI Songwriting System – Streamlit Frontend (Global V2)
======================================================
Features:
- Multimodal: ElevenLabs Voice & Suno Music Integration
- Advanced Control: Gender, Bars, Multi-variant Generation
- Artistic Analysis: Intelligent thematic breakdown
- Production Hub: Version management & Style fidelity tracking
"""

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
    CHUNKS_PATH,
    FAISS_INDEX_PATH,
    LABELED_SONGS_PATH,
    RAW_DIR,
    RERANK_ENABLED,
    STYLE_STRENGTH_DEFAULT,
    TARGET_ARTISTS,
)
from rag.pipeline import SongwritingPipeline, STRUCTURES

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Music System V2",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for Premium Look ─────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: 600; }
    .stDownloadButton>button { width: 100%; border-radius: 8px; }
    .metric-card { background-color: #1e2130; padding: 15px; border-radius: 12px; border: 1px solid #3d4455; }
    .hook-badge { background-color: #1db95422; border-left: 5px solid #1db954; padding: 15px; border-radius: 8px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ── Pipeline cache ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Initializing AI Music Engines...")
def get_pipeline() -> SongwritingPipeline:
    return SongwritingPipeline()

# ── Session state ──────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ── Helper Functions ───────────────────────────────────────────────────────
def _quality_bar(score: float, label: str = "") -> None:
    pct = int(score * 100)
    colour = "#e74c3c" if score < 0.35 else "#f39c12" if score < 0.65 else "#27ae60"
    st.markdown(
        f"<div style='font-size:12px;margin-bottom:2px;'>{label}</div>"
        f"<div style='background:#3d4455;border-radius:4px;height:8px;'>"
        f"<div style='background:{colour};width:{pct}%;height:8px;border-radius:4px;'></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

def _extract_hook(lyrics: str) -> str:
    chorus_match = re.search(r"\[[Cc]horus.*?\]\n(.*?)\n", lyrics, re.S)
    if chorus_match:
        lines = [l.strip() for l in chorus_match.group(1).split("\n") if l.strip()]
        if lines: return lines[0].strip('.,?! "')
    return ""

# ── Sidebar Settings ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Engine Controls")
    
    with st.expander("🎨 Style & Creativity", expanded=True):
        temperature = st.slider("Creativity (Temp)", 0.5, 1.0, 0.85, 0.05)
        style_strength = st.slider("Style Strength", 0.0, 1.0, float(STYLE_STRENGTH_DEFAULT), 0.05)
        top_k = st.slider("Context Depth (Top-k)", 2, 16, 8)
    
    with st.expander("🌍 Global Settings", expanded=True):
        language = st.selectbox("Language", ["English", "Spanish", "French", "German", "Japanese"], index=0)
        gender = st.selectbox("Perspective / Gender", ["Neutral", "Male", "Female", "Non-binary"], index=0)
        bars = st.slider("Target Lines/Bars", 4, 32, 16)
        num_variants = st.select_slider("Generation Count", options=[1, 3, 5], value=3)

    st.divider()
    debug_mode = st.checkbox("Debug Mode")
    if st.button("🗑️ Reset History"):
        st.session_state.history = []
        st.rerun()

# ── Main Application ───────────────────────────────────────────────────────
st.title("🎶 Global AI Music System")
st.caption("Lyrics Generation · Voice Synthesis · Music Production · Multi-Language Support")

left_col, right_col = st.columns([1, 1], gap="large")

with left_col:
    st.subheader("1. Artist Selection")
    
    def get_all_artists():
        artists = list(TARGET_ARTISTS)
        if RAW_DIR.exists():
            for f in RAW_DIR.glob("*.json"):
                name = f.stem.replace("_", " ").title()
                if name not in artists: artists.append(name)
        return sorted(list(set(artists)))

    available_artists = get_all_artists()
    selected_artists = st.multiselect("Select Artists (Mix up to 4)", available_artists, default=["Drake"], max_selections=4)
    new_artist = st.text_input("OR Add Artist (Genius Ingest)", placeholder="e.g. Brent Faiyaz")
    
    if new_artist.strip():
        if new_artist.strip() not in selected_artists:
            selected_artists = [new_artist.strip()]

    st.subheader("2. Theme & Emotion")
    theme = st.text_input("Main Topic / Mood", placeholder="late night in Tokyo with espresso regrets")
    
    st.subheader("3. Structure & Mode")
    s_choice = st.selectbox("Structure Preset", list(STRUCTURES.keys()), index=0)
    structure = STRUCTURES[s_choice]
    gen_mode = st.selectbox("Generation Mode", ["Full Song", "Verse Only", "Chorus Only", "Hook Generator", "Bridge"], index=0)
    
    st.subheader("4. Extra Constraints")
    extra = st.text_area("Specific Requests", placeholder="mention Los Angeles, use internal rhymes", height=80)

    st.divider()
    gen1, gen2 = st.columns(2)
    with gen1:
        submit = st.button("🎵 Generate Song", type="primary")
    with gen2:
        analyze = st.button("🧠 Analyze Theme")

with right_col:
    st.subheader("Generation Output")
    
    # ── Handle Logic ───────────────────────────────────────────────────────
    if submit or analyze:
        if not selected_artists: st.error("Select artist first."); st.stop()
        if not theme.strip(): st.error("Enter theme."); st.stop()
            
        pipeline = get_pipeline()
        is_analysis = analyze
        
        with st.status("Engine processing...", expanded=True) as status:
            # Dynamic ingestion support
            import importlib.util
            spec = importlib.util.spec_from_file_location("ingest", "scripts/01_build_dataset.py")
            ingester_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ingester_mod)
            
            for artist in selected_artists:
                if artist not in TARGET_ARTISTS:
                    st.write(f"🔍 Ingesting '{artist}'...")
                    if ingester_mod.ingest_dynamic_artist(artist):
                        import subprocess
                        st.write("🏷️ Labeling...")
                        subprocess.run([sys.executable, "scripts/02_label_songs.py"])
                        st.write("🏗️ Indexing...")
                        subprocess.run([sys.executable, "scripts/03_build_index.py", "--append", "--artist", artist])
                        pipeline.retriever.reload()
            
            st.write("⚡ Runnning Lyrical Pipeline...")
            result = pipeline.run(
                artists=selected_artists, theme=theme.strip(), structure=structure,
                language=language, gender=gender, bars=bars, num_variants=num_variants,
                top_k=top_k, temperature=temperature, style_strength=style_strength,
                mode=gen_mode, analysis_mode=is_analysis
            )
            status.update(label="✅ Ready!", state="complete")
        
        result["_timestamp"] = datetime.now().strftime("%H:%M:%S")
        st.session_state.history.insert(0, result)

    # ── Render Result ─────────────────────────────────────────────────────
    if st.session_state.history:
        cur = st.session_state.history[0]
        
        if "analysis" in cur:
            st.info("🧠 Artistic Analysis")
            st.markdown(cur["analysis"])
        else:
            # Metadata Row
            m1, m2, m3 = st.columns([2, 2, 1])
            m1.markdown(f"**Artists:** {' & '.join(cur['artists'])}")
            m2.markdown(f"**Theme:** {cur['theme']}")
            m3.caption(f"⏱ {cur['latency_ms']/1000:.1f}s")
            
            # Metric Cards
            rq = cur.get("retrieval_quality", 0.0)
            vs = cur.get("versions", [])
            avg_fidelity = sum(v["style_fidelity"] for v in vs) / max(1, len(vs))
            
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Style Grounding", f"{rq:.3f}")
            with c2: st.metric("Style Fidelity", f"{avg_fidelity:.3f}")
            with c3: st.metric("Model Version", cur.get("prompt_version","v2"))
            
            st.divider()
            
            # Versions Tab
            tab_labels = [f"🏆 Version {chr(65+i)} (Best)" if i==0 else f"Version {chr(65+i)}" for i in range(len(vs))]
            verse_tabs = st.tabs(tab_labels)
            
            for i, tab in enumerate(verse_tabs):
                with tab:
                    tab_lyr = vs[i]["lyrics"]
                    h = _extract_hook(tab_lyr)
                    if h: st.markdown(f"<div class='hook-badge'>🎯 <b>Hook:</b> <i>\"{h}\"</i></div>", unsafe_allow_html=True)
                    
                    st.markdown(re.sub(r"(\[[^\]]+\])", r"**\1**", tab_lyr))
                    st.download_button("⬇️ Download TXT", tab_lyr, file_name=f"lyrics_v{i}.txt", key=f"dl_{i}_{cur['_timestamp']}")

            # Multimodal Section
            st.divider()
            st.subheader("🎹 Multimodal Hub")
            m_voice, m_music, m_eval = st.tabs(["🎙️ Voice (ElevenLabs)", "🎸 Music (Suno)", "📈 Eval"])
            
            with m_voice:
                v1, v2 = st.columns([2, 1])
                voice_id = v1.selectbox("Voice Engine", ["Charlie (Neutral)", "Freya (Female)", "Thomas (Male)"], key="v_sel")
                v_map = {"Charlie (Neutral)": "JBFqnCBsd6RMkjVDRZzb", "Freya (Female)": "jsCq9z77P79qInv6idm6", "Thomas (Male)": "GBv7mTt0atIp3Br8iCZE"}
                if v2.button("🎤 Generate", key="btn_v"):
                    with st.spinner("Synthesizing..."):
                        audio = get_pipeline().voice_gen.generate_voice(cur["lyrics"], voice_id=v_map[voice_id])
                        if audio: st.audio(audio, format="audio/mp3")
                        else: st.error("Failed.")

            with m_music:
                s1, s2 = st.columns([2, 1])
                style_tags = s1.text_input("Suno Style Tags", value=f"{cur['artists'][0]} style, radio-ready")
                if s2.button("🎹 Produce", key="btn_m"):
                    with st.status("Generating Suno track...") as s:
                        urls = get_pipeline().music_gen.run_full_generation(cur["lyrics"], style_tags, f"AI-Song-{cur['_timestamp']}")
                        if urls: 
                            for u in urls: st.audio(u)
                            s.update(label="Complete!", state="complete")
                        else: st.error("Failed.")
    else:
        st.info("👈 Use the controls to generate your first AI song demo.")

# ── Footer ───────────────────────────────────────────────────────────────
if debug_mode and st.session_state.history:
    st.divider()
    st.expander("🔍 Diagnostics").json(st.session_state.history[0])
