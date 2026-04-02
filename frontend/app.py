"""
AI Songwriting System – Streamlit Frontend  (v3)
================================================
New in v3:
  - Style Strength slider (0.0 → 1.0) passed to pipeline
  - Debug Mode toggle: reveals full prompt, retrieval scores, diagnostics
  - Retrieval Quality indicator (coloured gauge bar)
  - Retrieval path label (artist / genre / full_corpus)
  - LLM Re-ranking badge in context panel
  - Chunk score breakdown: vector vs keyword contributions

Run: streamlit run frontend/app.py
"""

import re
import sys
from datetime import datetime
from pathlib import Path

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
    page_title="AI Songwriting System",
    page_icon="🎵",
    layout="wide",
)

# ── Pipeline cache ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading RAG pipeline…")
def get_pipeline() -> SongwritingPipeline:
    return SongwritingPipeline()

# ── Session state defaults ─────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []

# ── Helper: colour gauge ───────────────────────────────────────────────────
def _quality_bar(score: float, label: str = "") -> None:
    """Render a coloured horizontal bar for a 0-1 score."""
    pct = int(score * 100)
    colour = "#e74c3c" if score < 0.35 else "#f39c12" if score < 0.65 else "#27ae60"
    st.markdown(
        f"<div style='font-size:12px;margin-bottom:2px;'>{label}</div>"
        f"<div style='background:#e0e0e0;border-radius:4px;height:8px;'>"
        f"<div style='background:{colour};width:{pct}%;height:8px;border-radius:4px;'></div>"
        f"</div>"
        f"<div style='font-size:11px;color:#555;margin-top:2px;'>{score:.3f}</div>",
        unsafe_allow_html=True,
    )

def _extract_hook(lyrics: str) -> str:
    """Extract a catchy hook phrase from the chorus."""
    # Look for [Chorus] sections
    chorus_match = re.search(r"\[[Cc]horus.*?\]\n(.*?)\n", lyrics, re.S)
    if chorus_match:
        lines = [l.strip() for l in chorus_match.group(1).split("\n") if l.strip()]
        if lines:
            # Often the first line of the chorus is the hook
            raw_hook = lines[0]
            # Clean up common punctuation and make catchy
            return raw_hook.strip('.,?! "')
    return ""

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    temperature = st.slider(
        "Creativity (temperature)", 0.5, 1.0, 0.85, 0.05,
        help="Higher = more creative / unpredictable",
    )
    style_strength = st.slider(
        "Style Strength",
        min_value=0.0, max_value=1.0,
        value=float(STYLE_STRENGTH_DEFAULT), step=0.05,
        help=(
            "0.0 = loose inspiration from the artist's style\n"
            "1.0 = strict imitation of vocabulary and flow"
        ),
    )
    top_k = st.slider(
        "Retrieved examples (top-k)", 2, 16, 8,
        help="How many lyric chunks to use as style context",
    )
    language = st.selectbox("Language", ["English", "Spanish"], index=0)

    st.divider()
    show_context = st.checkbox("Show retrieved context", value=False)
    debug_mode   = st.checkbox(
        "Debug mode",
        value=False,
        help="Show prompt text, retrieval diagnostics, and score breakdowns",
    )

    st.divider()

    # Index status
    st.subheader("Index Status")
    def _st(p: Path) -> str:
        return "✅" if p.exists() else "❌"
    st.write(f"{_st(LABELED_SONGS_PATH)} Labeled songs")
    st.write(f"{_st(CHUNKS_PATH)} Chunks")
    st.write(f"{_st(FAISS_INDEX_PATH)} FAISS index")
    if RERANK_ENABLED:
        st.info("LLM re-ranking is ON", icon="🔁")

    if not FAISS_INDEX_PATH.exists():
        st.warning(
            "```bash\npython scripts/01_build_dataset.py\n"
            "python scripts/02_label_songs.py\n"
            "python scripts/03_build_index.py\n```"
        )

    st.divider()
    if st.session_state.history:
        if st.button("🗑️ Clear history", use_container_width=True):
            st.session_state.history = []
            st.rerun()
    st.caption("OpenAI · FAISS · BM25 · LangChain")

# ── Main layout ────────────────────────────────────────────────────────────
st.title("🎵 AI Songwriting System")
st.markdown(
    "Generate original lyrics in any artist's style — "
    "powered by **Hybrid RAG** (vector + BM25 + optional LLM re-ranking)."
)

col_left, col_right = st.columns([1, 1], gap="large")

# ── LEFT: controls ─────────────────────────────────────────────────────────
with col_left:
    # ── Demo Mode ──────────────────────────────────────────────────────────
    st.subheader("⚡ Quick Demo Presets")
    d1, d2, d3 = st.columns(3)
    with d1:
        if st.button("Drake 💔", use_container_width=True, help="Theme: Heartbreak"):
            st.session_state.demo_artist = ["Drake"]
            st.session_state.demo_theme = "heartbreak"
            st.rerun()
    with d2:
        if st.button("SZA 🌊", use_container_width=True, help="Theme: Emotional Vulnerability"):
            st.session_state.demo_artist = ["SZA"]
            st.session_state.demo_theme = "emotional vulnerability"
            st.rerun()
    with d3:
        if st.button("Mixed 🔥", use_container_width=True, help="Theme: Late Night Regret"):
            st.session_state.demo_artist = ["Drake", "SZA"]
            st.session_state.demo_theme = "late night regret"
            st.rerun()
            
    st.divider()
    # 1. Artist(s)
    st.subheader("1. Artist(s)")
    
    # Dynamically discover available artists from data/raw/
    def get_available_artists():
        # Core targets
        artists = list(TARGET_ARTISTS)
        # Dynamically ingested ones
        if RAW_DIR.exists():
            for f in RAW_DIR.glob("*.json"):
                name = f.stem.replace("_", " ").title()
                if name not in artists:
                    artists.append(name)
        return sorted(list(set(artists)))

    available_artists = get_available_artists()
    default_artists = st.session_state.get("demo_artist", ["Drake", "SZA"])
    
    multi = st.toggle("Mix multiple artists", value=len(default_artists)>1)
    
    if multi:
        selected_artists = st.multiselect(
            "Select 2–4 artists",
            available_artists,
            default=[a for a in default_artists if a in available_artists],
            max_selections=4,
        )
    else:
        # Single artist mode
        idx = available_artists.index(default_artists[0]) if default_artists[0] in available_artists else 0
        selected_artists = [st.selectbox(
            "Select an artist", available_artists, index=idx
        )]
    
    new_artist = st.text_input("OR Add New Artist (Ingest from Genius)", placeholder="e.g. Frank Ocean")
    if new_artist.strip():
        # If the user typed a name manually, we prioritize it
        artist_to_add = new_artist.strip()
        if artist_to_add not in selected_artists:
            selected_artists = [artist_to_add]

    st.subheader("2. Theme")
    default_theme = st.session_state.get("demo_theme", "heartbreak and moving on")
    theme = st.text_input(
        "Theme / emotion",
        placeholder="e.g. heartbreak, self-confidence, summer love, nostalgia",
        value=default_theme,
    )

    st.subheader("3. Structure")
    structure_choice = st.selectbox("Preset", list(STRUCTURES.keys()), index=0)
    custom_structure = st.text_input(
        "Or custom", placeholder="Intro → Verse 1 → Chorus → Verse 2 → Chorus → Outro",
    )
    structure = custom_structure.strip() or STRUCTURES[structure_choice]
    
    st.subheader("Generation mode")
    gen_mode = st.selectbox(
        "Mode",
        ["Full Song", "Verse Only", "Chorus Only", "Hook Generator", "Bridge"],
        index=0,
        help="Select section-specific generation or full song."
    )
    st.caption(f"`{structure}` (Mode: {gen_mode})")

    st.subheader("4. Extra Instructions (optional)")
    extra = st.text_area(
        "Specific requests",
        placeholder="e.g. mention Los Angeles, heavy internal rhymes, melancholic tone",
        height=72,
    )

    generate_btn = st.button(
        "🎶 Generate Lyrics", type="primary", use_container_width=True,
        disabled=not FAISS_INDEX_PATH.exists(),
    )

# ── RIGHT: output ──────────────────────────────────────────────────────────
with col_right:
    st.subheader("Generated Lyrics")

    if generate_btn:
        if not selected_artists:
            st.error("Select at least one artist.")
            st.stop()
        if not theme.strip():
            st.error("Enter a theme.")
            st.stop()

        try:
            pipeline = get_pipeline()
        except FileNotFoundError as exc:
            st.error(f"**Index missing.** Run the pipeline scripts first.\n\n`{exc}`")
            st.stop()

        with st.spinner("Retrieving examples and generating lyrics…"):
            try:
                # ── Dynamic Ingestion Logic ──────────────────────────────
                import importlib.util
                def _get_ingester():
                    spec = importlib.util.spec_from_file_location("ingest", "scripts/01_build_dataset.py")
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
                
                ingester = _get_ingester()
                
                for artist in selected_artists:
                    if artist not in TARGET_ARTISTS:
                        # 1. Fetch
                        with st.status(f"Adding '{artist}' to system...", expanded=True) as status:
                            st.write(f"🔍 Fetching songs from Genius for '{artist}'...")
                            success = ingester.ingest_dynamic_artist(artist)
                            if success:
                                # 2. Label
                                st.write(f"🏷️ Labeling and analyzing lyrics...")
                                import subprocess
                                subprocess.run([sys.executable, "scripts/02_label_songs.py"])
                                
                                # 3. Index
                                st.write(f"🏗️ Building search index (appending vectors)...")
                                subprocess.run([sys.executable, "scripts/03_build_index.py", "--append", "--artist", artist])
                                
                                # 4. REFRESH IN-MEMORY STATE
                                st.write(f"🔄 Refreshing system memory...")
                                pipeline.retriever.reload()
                                
                                status.update(label=f"✅ '{artist}' ready for generation!", state="complete", expanded=False)
                            else:
                                status.update(label=f"❌ Failed to find artist '{artist}'.", state="error")
                                st.error(f"Could not find or ingest '{artist}' on Genius. Try a different name.")
                                st.stop()

                result = pipeline.run(
                    artists=selected_artists,
                    theme=theme.strip(),
                    structure=structure,
                    language=language,
                    top_k=top_k,
                    temperature=temperature,
                    extra_instructions=extra.strip(),
                    style_strength=style_strength,
                    mode=gen_mode,
                )
            except RuntimeError as exc:
                st.error(
                    f"**Generation failed.** Check your OpenAI key and quota.\n\n`{exc}`"
                )
                st.stop()
            except Exception as exc:
                st.error(f"Unexpected error: `{exc}`")
                st.stop()

        result["mode"] = gen_mode
        result["_timestamp"] = datetime.now().strftime("%H:%M:%S")
        st.session_state.history = [result] + st.session_state.history[:9]

    # ── Display most recent result ────────────────────────────────────────
    if st.session_state.history:
        cur = st.session_state.history[0]
        artist_label = " + ".join(cur["artists"])
        diag = cur.get("retrieval_diagnostics", {})
        rq   = cur.get("retrieval_quality", 0.0)

        # Meta row
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            st.markdown(f"**Style:** {artist_label}")
        with c2:
            st.markdown(f"**Theme:** {cur['theme']}")
        with c3:
            lat = cur.get("latency_ms", 0)
            st.caption(f"⏱ {lat/1000:.1f}s")

        # Retrieval quality bar
        path_badge = {
            "artist":      "🟢 Artist",
            "genre":       "🟡 Genre fallback",
            "full_corpus": "🔴 Corpus fallback",
        }.get(diag.get("path",""), "⚪ Unknown")

        st.markdown(
            f"<span style='font-size:12px'>"
            f"Retrieval: {path_badge} · {diag.get('n_chunks',0)} chunks"
            f"</span>",
            unsafe_allow_html=True,
        )
        _quality_bar(rq, f"Style Grounding ({rq:.3f})")

        # Fallback warning
        if cur.get("retrieval_fallback"):
            st.warning(
                f"Retrieval fell back to **{diag.get('path','unknown')}** search. "
                "Build more artist data for better results.",
                icon="⚠️",
            )

        # Style strength badge
        ss = cur.get("style_strength", STYLE_STRENGTH_DEFAULT)
        tier = "strict" if ss >= 0.75 else "moderate" if ss >= 0.40 else "loose"
        st.caption(
            f"Structure: `{cur['structure']}`  ·  "
            f"Style strength: {ss:.2f} ({tier})  ·  "
            f"Prompt: {cur.get('prompt_version','?')}"
        )
        # Better metric display to avoid "0...." truncation
        # Style Grounding (Hardened Color thresholds)
        if rq >= 0.7:
            rq_color = "🟢 Strong"
        elif rq >= 0.4:
            rq_color = "🟡 Moderate"
        else:
            rq_color = "🔴 Weak"
        
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f"<div style='font-size:0.9rem; color:gray;'>Style Grounding</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='font-size:1.2rem; font-weight:bold;'>{rq:.3f}</span> <span style='font-size:0.8rem;'>{rq_color}</span>", unsafe_allow_html=True)
        
        with m2:
            st.markdown(f"<div style='font-size:0.9rem; color:gray;'>Style Fidelity</div>", unsafe_allow_html=True)
            avg_fidelity = sum(v.get('style_fidelity', 0) for v in cur.get('versions', [])) / max(1, len(cur.get('versions', [])))
            st.markdown(f"<span style='font-size:1.2rem; font-weight:bold;'>{avg_fidelity:.3f}</span>", unsafe_allow_html=True)
        
        with m3:
            st.markdown(f"<div style='font-size:0.9rem; color:gray;'>Latency</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='font-size:1.2rem; font-weight:bold;'>{(cur.get('latency_ms', 0)/1000):.2f}s</span>", unsafe_allow_html=True)
            
        with m4:
            st.markdown(f"<div style='font-size:0.9rem; color:gray;'>Artists</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='font-size:1.2rem; font-weight:bold;'>{len(cur['artists'])} sel.</span>", unsafe_allow_html=True)
        st.divider()

        # ── Lyrics Versions Tabs ──────────────────────────────────────────
        versions_data = cur.get("versions", [])
        if not versions_data:
            st.error("No versions generated.")
            st.stop()
            
        # Determine labels for tabs, marking Best Version
        tab_labels = []
        for i, v in enumerate(versions_data):
            label = f"Version {chr(65+i)}"
            if i == 0: # Pipeline sorts by fidelity, so 0 is best
                label = f"🏆 {label} (Best)"
            tab_labels.append(label)
            
        tabs = st.tabs(tab_labels)
        
        for i, tab in enumerate(tabs):
            tab_lyr = versions_data[i]["lyrics"]
            fidelity = versions_data[i]["style_fidelity"]
            
            with tab:
                hook = _extract_hook(tab_lyr)
                
                # Prominent Hook Display
                if hook:
                    st.markdown(
                        f"<div style='background-color:#1db95422; border-left: 5px solid #1db954; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>"
                        f"<span style='font-size: 0.9em; color: #1db954; font-weight: bold; text-transform: uppercase;'>🎯 Catchy Hook Identified</span><br/>"
                        f"<span style='font-size: 1.4em; font-weight: bold; font-style: italic;'>\"{hook}\"</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                # Version Specific Controls
                b1, b2, b3 = st.columns([1, 1, 2])
                with b1:
                    btn_key = f"improve_hook_{i}_{cur.get('_timestamp','')}"
                    if st.button("✨ Improve Hook", key=btn_key, use_container_width=True):
                        with st.spinner("Polishing chorus..."):
                            improved = get_pipeline().improve_hook_only(tab_lyr)
                            # Update this version in history
                            cur["versions"][i]["lyrics"] = improved
                            st.rerun()
                with b2:
                    st.caption(f"Fidelity: {fidelity:.2f}")
                
                # Hook Quality Score (Always Visible for Hook Generator)
                if cur.get('mode') == 'Hook Generator' and 'hook_score' in versions_data[i]:
                    hs = versions_data[i]["hook_score"]
                    hs_color = "🟢" if hs >= 0.8 else "🟡" if hs >= 0.6 else "🔴"
                    st.markdown(f"**🎯 Hook Quality: {hs_color} {hs:.2f}**")
                    
                    # Detailed breakdown for debug (moved to sub-section)
                    if debug_mode:
                        with st.expander(f"📊 Score Breakdown ({hs:.2f})"):
                            v_lines = _extract_hook(tab_lyr).split(" / ") if " / " in _extract_hook(tab_lyr) else tab_lyr.split("\n")
                            from rag.validator import repetition_score, unique_word_ratio, keyword_strength_score
                            st.write(f"- **Repetition Pattern:** {repetition_score(v_lines):.2f}")
                            st.write(f"- **Variation Ratio:** {unique_word_ratio(v_lines):.2f}")
                            st.write(f"- **Concrete Grounding:** {keyword_strength_score(v_lines):.2f}")
                            if hs < 0.5:
                                st.warning("Score penalized for excessive repetition or low variation.")
                
                st.divider()
                        
                lyrics_md = re.sub(r"(\[[^\]]+\])", r"**\1**", tab_lyr)
                st.markdown(lyrics_md)

                # Download + Copy
                dl_col, cp_col = st.columns(2)
                with dl_col:
                    st.download_button(
                        "⬇️ Download (.txt)", tab_lyr,
                        file_name=f"lyrics_v{chr(65+i)}_{artist_label.replace(' + ','_').replace(' ','_')}.txt",
                        mime="text/plain", use_container_width=True,
                        key=f"dl_btn_{i}_{cur.get('_timestamp','')}"
                    )
                with cp_col:
                    with st.expander("📋 Copy raw text"):
                        st.code(tab_lyr, language=None)


        # ── Retrieved context ─────────────────────────────────────────────
        if show_context and cur.get("context"):
            st.divider()
            st.subheader(f"Retrieved Context ({len(cur['context'])} chunks)")
            max_s = max((c.get("score",0) for c in cur["context"]), default=1.0) or 1.0

            for i, chunk in enumerate(cur["context"], 1):
                hs  = chunk.get("score",         0.0)
                vs  = chunk.get("vector_score",  0.0)
                ks  = chunk.get("keyword_score", 0.0)
                fb  = f" · *{chunk['fallback']} fallback*" if chunk.get("fallback") else ""
                rp  = chunk.get("retrieval_path", "")
                hdr = f"{i}. **{chunk['artist']}** – {chunk['song']} [{chunk.get('section','')}]{fb}"
                with st.expander(hdr):
                    bar_pct = int((hs / max_s) * 100)
                    st.markdown(
                        f"<div style='background:#e0e0e0;border-radius:4px;height:6px;'>"
                        f"<div style='background:#1DB954;width:{bar_pct}%;height:6px;border-radius:4px;'>"
                        f"</div></div>",
                        unsafe_allow_html=True,
                    )
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1: st.metric("Hybrid",  f"{hs:.3f}")
                    with sc2: st.metric("Vector",  f"{vs:.3f}")
                    with sc3: st.metric("Keyword", f"{ks:.3f}")
                    st.caption(
                        f"Path: {rp}  ·  Theme: {chunk.get('theme','N/A')}  ·  "
                        f"Genre: {chunk.get('genre','N/A')}"
                    )
                    st.text(chunk.get("text",""))

        # ── Debug panel ───────────────────────────────────────────────────
        if debug_mode:
            st.divider()
            st.subheader("🔍 Debug Information")

            with st.expander("Retrieval Diagnostics"):
                st.json(diag)

            with st.expander("Full Prompt (System)"):
                st.text(cur.get("_system_prompt", "(not stored — re-generate to see)"))

            with st.expander("All Retrieved Chunk Scores"):
                rows = [
                    {
                        "artist": c["artist"], "song": c["song"],
                        "section": c.get("section",""),
                        "hybrid": c.get("score",0),
                        "vector": c.get("vector_score",0),
                        "keyword": c.get("keyword_score",0),
                        "path": c.get("retrieval_path",""),
                    }
                    for c in cur.get("context",[])
                ]
                st.dataframe(rows, use_container_width=True)

    else:
        st.info("Configure options on the left and click **Generate Lyrics**.")

# ── History panel ──────────────────────────────────────────────────────────
if len(st.session_state.history) > 1:
    st.divider()
    st.subheader(f"History ({len(st.session_state.history)} generations)")
    for i, rec in enumerate(st.session_state.history[1:], 2):
        al  = " + ".join(rec["artists"])
        ts  = rec.get("_timestamp","")
        rq2 = rec.get("retrieval_quality", 0.0)
        with st.expander(
            f"{i}. {al} — {rec['theme'][:45]}  "
            f"[{ts}]  RQ={rq2:.2f}"
        ):
            st.markdown(re.sub(r"(\[[^\]]+\])", r"**\1**", rec["lyrics"]))
            st.download_button(
                "⬇️ Download", rec["lyrics"],
                file_name=f"lyrics_{i}_{al.replace(' + ','_').replace(' ','_')}.txt",
                mime="text/plain",
                key=f"dl_{i}_{ts}",
            )
