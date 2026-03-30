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
    st.subheader("1. Artist(s)")
    multi = st.toggle("Mix multiple artists", value=False)
    if multi:
        selected_artists = st.multiselect(
            "Select 2–4 artists",
            sorted(TARGET_ARTISTS), default=["Drake","SZA"], max_selections=4,
        )
    else:
        selected_artists = [st.selectbox(
            "Select an artist", sorted(TARGET_ARTISTS),
            index=sorted(TARGET_ARTISTS).index("Drake"),
        )]

    st.subheader("2. Theme")
    theme = st.text_input(
        "Theme / emotion",
        placeholder="e.g. heartbreak, self-confidence, summer love, nostalgia",
        value="heartbreak and moving on",
    )

    st.subheader("3. Structure")
    structure_choice = st.selectbox("Preset", list(STRUCTURES.keys()), index=0)
    custom_structure = st.text_input(
        "Or custom", placeholder="Intro → Verse 1 → Chorus → Verse 2 → Chorus → Outro",
    )
    structure = custom_structure.strip() or STRUCTURES[structure_choice]
    st.caption(f"`{structure}`")

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
                result = pipeline.run(
                    artists=selected_artists,
                    theme=theme.strip(),
                    structure=structure,
                    language=language,
                    top_k=top_k,
                    temperature=temperature,
                    extra_instructions=extra.strip(),
                    style_strength=style_strength,
                )
            except RuntimeError as exc:
                st.error(
                    f"**Generation failed.** Check your OpenAI key and quota.\n\n`{exc}`"
                )
                st.stop()
            except Exception as exc:
                st.error(f"Unexpected error: `{exc}`")
                st.stop()

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
        _quality_bar(rq, f"Retrieval Quality ({rq:.3f})")

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
        st.divider()

        # Lyrics
        lyrics_md = re.sub(r"(\[[^\]]+\])", r"**\1**", cur["lyrics"])
        st.markdown(lyrics_md)

        # Download + Copy
        dl_col, cp_col = st.columns(2)
        with dl_col:
            st.download_button(
                "⬇️ Download (.txt)", cur["lyrics"],
                file_name=f"lyrics_{artist_label.replace(' + ','_').replace(' ','_')}.txt",
                mime="text/plain", use_container_width=True,
            )
        with cp_col:
            with st.expander("📋 Copy raw text"):
                st.code(cur["lyrics"], language=None)

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
