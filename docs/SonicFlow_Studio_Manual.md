# SonicFlow Studio v3 — Complete User Manual & Reference Guide

---

## Table of Contents

1. [What is SonicFlow Studio?](#1-what-is-sonicflow-studio)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture Overview](#3-system-architecture-overview)
   - 3.1 [How the System Works — End-to-End Flow](#31-how-the-system-works--end-to-end-flow)
4. [Getting Started — Step-by-Step](#4-getting-started--step-by-step)
5. [The Sidebar — Studio Controls](#5-the-sidebar--studio-controls)
   - 5.1 [Artist Search](#51-artist-search)
   - 5.2 [Creative Controls](#52-creative-controls)
   - 5.3 [Multimodal Engines](#53-multimodal-engines)
   - 5.4 [Clear Project](#54-clear-project)
6. [Main Studio Area](#6-main-studio-area)
   - 6.1 [Theme & Creative Mode](#61-theme--creative-mode)
   - 6.2 [Reference Lyrics](#62-reference-lyrics)
   - 6.3 [Structure & Preset](#63-structure--preset)
   - 6.4 [Ignite Production Button](#64-ignite-production-button)
   - 6.5 [Pipeline Status Panel](#65-pipeline-status-panel)
7. [Production Output Panel](#7-production-output-panel)
   - 7.1 [Vocal Output (ElevenLabs)](#71-vocal-output-elevenlabs)
   - 7.2 [Full Song Output (Suno AI)](#72-full-song-output-suno-ai)
   - 7.3 [Lyrics Tab](#73-lyrics-tab)
   - 7.4 [Insights Tab](#74-insights-tab)
   - 7.5 [Variants Tab](#75-variants-tab)
   - 7.6 [Stats Tab](#76-stats-tab)
8. [Project Library](#8-project-library)
   - 8.1 [Stats Bar](#81-stats-bar)
   - 8.2 [Project Cards](#82-project-cards)
   - 8.3 [Opening a Project in Studio](#83-opening-a-project-in-studio)
   - 8.4 [Deleting a Project](#84-deleting-a-project)
   - 8.5 [Searching Projects](#85-searching-projects)
9. [Account & Sign Out](#9-account--sign-out)
10. [Complete Workflow Walkthroughs](#10-complete-workflow-walkthroughs)
    - 10.1 [Generate Your First Song](#101-generate-your-first-song)
    - 10.2 [Continue an Existing Story](#102-continue-an-existing-story)
    - 10.3 [Remix a Style](#103-remix-a-style)
    - 10.4 [Revisit a Saved Song from Library](#104-revisit-a-saved-song-from-library)
    - 10.5 [Download Audio Files](#105-download-audio-files)
11. [Glossary of Terms](#11-glossary-of-terms)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. What is SonicFlow Studio?

**SonicFlow Studio v3** is a full-stack AI-powered songwriting and music production platform. It combines large language models, vector-based lyric retrieval, text-to-speech vocal synthesis, and AI music generation into a single seamless workflow — allowing a user to go from a creative idea (a theme or emotional concept) to a fully produced song with vocals and music in one click.

### What SonicFlow Does

- **Generates original song lyrics** in the style of any real-world artist, across any language, using a Retrieval-Augmented Generation (RAG) pipeline.
- **Synthesises a vocal track** from those lyrics using ElevenLabs' Multilingual v2 voice model.
- **Generates a full song** (music + singing) using Suno AI's V4 model.
- **Saves every production** to a persistent Project Library so you can revisit, reload, or delete past tracks at any time.
- **Produces multiple creative variants** of the same lyrics so you can choose the version that resonates most.
- **Analyses** the generated lyrics for theme, tone, and creative direction using GPT-4.

### Who It Is For

SonicFlow is designed for songwriters, music producers, creative directors, content creators, and anyone who wants to explore AI-assisted music creation — without needing any prior musical training or technical knowledge.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | Next.js 14 (App Router) | Web UI, routing, server-side rendering |
| **Styling** | Tailwind CSS + custom design tokens | Obsidian Studio dark theme |
| **Fonts** | Space Grotesk (display) + Inter (body) | Typography |
| **Backend API** | FastAPI (Python) + Uvicorn | REST API server |
| **Lyrics AI** | OpenAI GPT-4o (generation) + GPT-4o-mini (analysis, labeling) | Lyric writing and analysis |
| **Lyric Retrieval** | FAISS vector index + BM25 | Hybrid semantic + keyword search over artist lyric corpus |
| **Artist Data** | Genius API + Apify scraper | Real artist lyric data used for style retrieval |
| **Voice Synthesis** | ElevenLabs Multilingual v2 | Text-to-speech vocal output |
| **Music Generation** | Suno AI v4 via sunoapi.org | Full song generation (vocals + music) |
| **Music Fallback** | HuggingFace MusicGen (facebook/musicgen-small) | Instrumental fallback if Suno fails |
| **Deployment** | AWS EC2 (Ubuntu) + systemd | Production server at 3.239.91.199 |
| **Process Manager** | systemd (sonicflow-api + sonicflow-nextjs) | Auto-restart on failure / reboot |
| **Auth** | Shared session token (Bearer) | Studio access control |
| **Storage** | File-based JSON (data/projects.json) | Project persistence |
| **HTTP Client** | Axios (frontend) + Requests (backend) | API communication |

---

## 3. System Architecture Overview

```
USER BROWSER
     │
     ▼
Next.js Frontend (port 3001)
     │  HTTPS / HTTP REST
     ▼
FastAPI Backend (port 8000)
     │
     ├──► OpenAI GPT-4o ──────────────────► Lyrics generation
     │         │
     │         └──► FAISS + BM25 index ──► Artist style retrieval
     │
     ├──► ElevenLabs API ─────────────────► Vocal audio (MP3 bytes)
     │
     ├──► Suno AI (sunoapi.org) ──────────► Full song audio (MP3 bytes)
     │         └── polling every 10s until FIRST_SUCCESS / SUCCESS
     │
     └──► data/projects.json ─────────────► Persistent project storage
```

**Data flow for one generation:**
1. User fills in theme, artist, settings → clicks **IGNITE PRODUCTION**
2. Frontend sends `POST /generate` to FastAPI with all parameters
3. FastAPI runs the RAG pipeline → GPT-4o writes lyrics
4. ElevenLabs converts lyrics to speech (vocal MP3)
5. Suno AI generates a full song from lyrics + style tags (full song MP3)
6. Both audio files are base64-encoded and returned to the browser
7. Frontend decodes them into playable audio blobs
8. Project metadata (no audio — metadata only) is saved to `POST /projects`

---

### 3.1 How the System Works — End-to-End Flow

This section shows exactly what happens from the moment you click **IGNITE PRODUCTION** to when you hear your song.

```
STEP 1 — USER INPUT
    Browser (Next.js)
        Artist name(s), Theme, Structure, Language, Bars, Creativity,
        Style Strength, Enable Voice toggle, Enable Music toggle
            |
            | POST /generate  (Bearer token auth)
            v

STEP 2 — FASTAPI BACKEND receives request
            |
            v

STEP 3 — RAG LYRICS PIPELINE (rag/pipeline.py)
    a) Query Expansion
           GPT-4o-mini expands theme into multiple search queries
    b) Hybrid Retrieval
           FAISS vector search  +  BM25 keyword search
           -> Merge, de-duplicate, re-rank results
           -> Top-K chunks of real artist lyrics fetched
    c) Prompt Assembly (rag/prompt_builder.py)
           System prompt with style guide + output template
           User prompt with theme, structure, bars constraint
           Retrieved lyric chunks as style context
    d) Lyrics Generation
           GPT-4o generates song lyrics matching artist style
           Bars validator enforces exact line count
           Chorus validator checks repetition / hook presence
    e) Parallel Variant Generation
           3 variants generated in parallel threads
           Fidelity scoring picks best version
            |
            | lyrics string produced
            v

STEP 4a — VOCAL SYNTHESIS  (independent, parallel with Step 4b)
    ElevenLabs Multilingual v2
        Input  : full lyrics text
        Output : MP3 audio bytes  (TTS — reads lyrics aloud)
        -> Returned as voice_audio_b64 in JSON response

STEP 4b — FULL SONG GENERATION  (independent, parallel with Step 4a)
    Suno AI v4  via  sunoapi.org
        Input  : lyrics + style tags (artist name, language)
        Step 1 : POST /api/v1/generate  ->  taskId returned
        Step 2 : Poll GET /api/v1/generate/record-info?taskId=...
                 every 10 seconds until status = FIRST_SUCCESS or SUCCESS
        Step 3 : Extract sourceAudioUrl from sunoData[0]
        Step 4 : Download MP3 bytes from URL
        -> Returned as music_audio_b64 in JSON response
    Fallback  : HuggingFace MusicGen (instrumental only)
                if Suno fails or times out

STEP 5 — ANALYSIS  (post-generation)
    GPT-4o-mini re-reads generated lyrics
        -> Produces structured analysis:
           theme, tone, emotional arc, hook quality, suggestions
        -> Returned in analysis field of JSON response

STEP 6 — RESPONSE ASSEMBLED
    FastAPI returns JSON:
        lyrics            (full text)
        versions[]        (3 lyric variants with fidelity scores)
        voice_audio_b64   (base64 MP3 — ElevenLabs vocal)
        music_audio_b64   (base64 MP3 — Suno full song)
        analysis          (GPT-4o-mini creative insights)
        retrieval_quality (0.0 – 1.0 score)
        latency_ms        (total pipeline time)
            |
            | HTTP response back to browser
            v

STEP 7 — FRONTEND RENDERS OUTPUT (Next.js)
    Decodes base64 -> Blob URLs -> <audio> elements
    Renders lyrics, variants, insights, stats tabs
    Shows VOICE KB and MUSIC KB debug readout

STEP 8 — AUTO-SAVE TO LIBRARY
    Frontend calls POST /projects with metadata
    Backend writes to data/projects.json
    Project appears in Library page instantly
```

#### Key Design Decisions

- **No mixing**: ElevenLabs (pure TTS vocal) and Suno AI (full AI song with its own vocals) are two independent outputs. They are NOT combined or mixed — each serves a different purpose.
- **Polling not webhook**: Suno's webhook delivery is unreliable in hosted environments. The system uses active polling every 10s with a 5-minute timeout.
- **Base64 transport**: Audio bytes are base64-encoded in the JSON response so no separate CDN or file storage is needed — audio lives only in the browser session.
- **Bars enforcement at two layers**: The prompt explicitly requests the exact bar count. A post-processing validator (`rag/validator.py`) then trims or pads to match, counting only lyrical lines (section headers like `[Verse 1]` are NOT counted).
- **Library persistence**: Only metadata is stored server-side (no audio files). Audio is regenerated if needed. This keeps storage costs near zero.

---

## 4. Getting Started — Step-by-Step

### Step 1 — Open the Application

Navigate to:
```
http://3.239.91.199:3001
```
(or `http://localhost:3001` if running locally)

You will be redirected to the **Login** page automatically.

### Step 2 — Log In

| Field | Value |
|---|---|
| Email | `admin@studio.com` |
| Password | `admins` |

Click **Sign In**. You will be taken to the main **Studio** page.

### Step 3 — Set Your Artist

In the left sidebar under **ARTIST**, type the name of an artist whose style you want the lyrics to imitate (e.g., `Drake`, `Taylor Swift`, `Sabrina Carpenter`). Suggestions from the Genius database will appear — click one to select it.

### Step 4 — Enter Your Theme

In the main area under **1. THEME & CREATIVE MODE**, type a short emotional or conceptual description into the **Project Theme** field. This is the creative seed for the entire song.

Examples:
- `nostalgic late night drive in Seoul`
- `falling in love in a foreign city`
- `heartbreak at 3am`

### Step 5 — Adjust Settings (Optional)

Tune the sidebar controls to your preference (see Section 5 for full details). For a first generation, the defaults work well.

### Step 6 — Choose Structure

In **3. STRUCTURE & PRESET**, pick a song structure from the dropdown. The default **Verse-Chorus (Pop/Rock)** is a good starting point.

### Step 7 — Generate

Click the **IGNITE PRODUCTION** button. The pipeline status panel will appear and update in real time:
- 🧠 Synthesizing Lyrical Theme
- 🎤 Vocal Output (ElevenLabs)
- 🎵 Full Song (Suno AI)
- 🔍 AI Lyrical Analysis

Generation takes **2–8 minutes** depending on Suno AI queue time.

### Step 8 — Review Your Output

Once complete:
- Listen to **Vocal Output** (ElevenLabs TTS reading the lyrics)
- Listen to **Full Song Output** (Suno AI full song with vocals and music)
- Read the full lyrics in the **📝 Lyrics** tab
- Explore variants in the **🌈 Variants** tab
- Check creative direction in **💡 Insights**

### Step 9 — Save and Revisit

Your project is **automatically saved** to the Library after every successful generation. Navigate to **Library** (sidebar or header) to see all past projects and click any card to re-open it in Studio.

---

## 5. The Sidebar — Studio Controls

The left sidebar contains all creative controls. It can be collapsed/expanded using the **Sliders** icon in the top header.

---

### 5.1 Artist Search

**What it is:** A search field powered by the Genius API that finds real artists in the system's database.

**How to use:**
1. Type at least 3 characters of an artist's name
2. A dropdown of matching suggestions appears
3. Click a suggestion to select it — the field populates with the exact artist name

**What it affects:** The entire RAG retrieval pipeline. The system searches its vector index of real lyrics from this artist and uses those as stylistic examples when generating your lyrics. The more songs indexed for an artist, the better the stylistic fidelity.

**Tip:** If no suggestions appear, type the full name and press Enter — the name will still be used even without an autocomplete match.

**Built-in style fingerprints available for:** Drake, Kendrick Lamar, J. Cole, Travis Scott, The Weeknd, Taylor Swift, Billie Eilish, SZA, Frank Ocean, Ariana Grande, Bad Bunny, Tyler the Creator, Doja Cat, Childish Gambino, Post Malone, Lil Wayne, Nicki Minaj, Cardi B, Brent Faiyaz, PinkPantheress, Morgan Wallen, Coldplay, Imagine Dragons.

---

### 5.2 Creative Controls

#### Creativity (Temperature)
**Range:** 0.5 → 1.2 | **Default:** 0.85

**What it is:** Controls how "adventurous" the AI is when writing lyrics. This maps directly to the GPT model's temperature parameter.

| Value | Effect |
|---|---|
| 0.5 – 0.6 | Very conservative. Safe, predictable rhymes. Less original. |
| 0.7 – 0.9 | Balanced. Creative but coherent. **Recommended range.** |
| 1.0 – 1.2 | Very adventurous. Unexpected imagery, occasionally abstract or surprising. May reduce coherence at extremes. |

**How to tweak:** Drag the slider left for safer output, right for more experimental writing. Start at 0.85 and increase if lyrics feel too generic.

---

#### Style Strength
**Range:** 0.0 → 1.0 | **Default:** 0.7

**What it is:** Controls how closely the AI imitates the selected artist's specific vocabulary, rhyme scheme, and cadence.

| Value | Behaviour |
|---|---|
| 0.0 – 0.39 | Loose Inspiration Mode — uses artist only as a starting point. Original creative voice takes over. |
| 0.4 – 0.74 | Moderate Style Mode — captures overall feel, flow, and vocabulary without rigid imitation. |
| 0.75 – 1.0 | Strict Imitation Mode — mirrors the artist's exact vocabulary, slang, cadence, and recurring motifs as closely as possible. |

**How to tweak:** Higher = more authentic to the chosen artist's voice. Lower = more original, less derivative. For ghostwriting in an artist's style, use 0.8+. For inspiration only, use 0.4–0.6.

---

#### Language
**Options:** English, Spanish, French, German, Hindi, Arabic, Portuguese, Japanese, Korean, Chinese

**What it is:** The language in which the lyrics are written.

**How it works:** The AI is instructed to write exclusively in the chosen language. For non-English languages, a vocabulary cross-language normalization boost is applied to style fidelity scoring since artist corpora are primarily English.

**Special note:** Artists like Bad Bunny naturally support Spanish/Spanglish. Choosing Spanish with a Spanish-speaking artist gives the best results.

---

#### Vocal Perspective
**Options:** Neutral | Male | Female

**What it is:** Sets the grammatical and emotional point-of-view gender of the lyrics (e.g., "she" vs "he" references, pronoun choices, emotional framing).

**How to tweak:** Use **Neutral** for gender-agnostic writing, **Male/Female** when the narrative explicitly involves a specific gender perspective. This is not voice pitch — it's lyrical POV only.

---

#### Song Length (Bars)
**Options:** 4 | 8 | 16 | 32

**What it is:** The total number of lyrical lines (bars) in the generated song. One bar = one lyrical line. Section headers like `[Verse 1]` and `[Chorus]` do **not** count as bars.

| Setting | Total Lines | Typical Use |
|---|---|---|
| 4 bars | 4 lyrical lines | Hook or snippet only |
| 8 bars | 8 lyrical lines | Short demo or single verse + chorus |
| 16 bars | 16 lyrical lines | Standard single (verse + chorus + verse + chorus) |
| 32 bars | 32 lyrical lines | Full song with intro, multiple verses, bridge, outro |

**How the bars are distributed:** Lines are allocated proportionally across sections. Verses receive approximately twice the lines of choruses/bridges. For example, with 32 bars on a standard structure:
- Verse 1: ~8 lines
- Pre-Chorus: ~4 lines
- Chorus: ~4 lines
- Verse 2: ~8 lines
- Pre-Chorus: ~4 lines
- Bridge: ~4 lines

**Tip:** Use 32 bars for a complete production-ready song. Use 8–16 bars for quick experimentation.

---

#### Creative Variants
**Options:** 1 | 3 | 5

**What it is:** How many alternative versions of the lyrics the AI generates in parallel. All variants share the same theme, artist, and settings — but differ in specific word choices, metaphors, and phrasing.

| Setting | Behaviour |
|---|---|
| 1 | One version generated. Fastest. |
| 3 | Three versions generated in parallel. The highest-scoring one is shown as "best". All three accessible in Variants tab. |
| 5 | Five versions. Most coverage of the creative space. Slightly slower. |

**Scoring:** Each variant is scored on **Style Fidelity** — a Jaccard similarity score measuring vocabulary overlap with the retrieved artist lyric chunks. The highest-scoring variant becomes the primary output.

**How to tweak:** Use 3–5 variants when you want to explore options and pick the best. Use 1 variant when you've already found a style that works and want speed.

---

### 5.3 Multimodal Engines

#### Voice Synthesis Toggle
**Default:** ON

**What it is:** When enabled, ElevenLabs Multilingual v2 converts the generated lyrics into a spoken/sung vocal audio track (MP3). This is a text-to-speech reading of the lyrics — not a singing AI.

**Turn off when:** You only want to evaluate the lyrics or Suno music without the ElevenLabs vocal track. Disabling speeds up generation.

**Output:** Appears as **Vocal Output (ElevenLabs)** in the playback panel.

---

#### Music Production Toggle
**Default:** ON

**What it is:** When enabled, Suno AI v4 generates a full AI song from the lyrics and style tags — including AI-generated vocals and backing music. This is a complete song, not just an instrumental.

**Turn off when:** You only want lyrics or ElevenLabs vocal without Suno's full song generation. Disabling significantly speeds up generation.

**Output:** Appears as **Full Song Output (Suno AI)** in the playback panel.

**Note on credits:** Suno generation consumes credits from your sunoapi.org account. If credits are exhausted, the system automatically falls back to HuggingFace MusicGen (instrumental only).

---

#### Upload Instrumental
**Accepted formats:** MP3, WAV

**What it is:** Allows you to provide your own instrumental backing track. This is displayed as a separate audio player in the output panel alongside the generated content.

**How to use:** Click **MP3 / WAV**, select a file from your device. The file name will appear on the button. After generation, your instrumental appears in the playback area.

---

### 5.4 Clear Project

**What it does:** Resets the entire Studio to its default state:
- Clears the current result from the output panel
- Clears the session history from the bottom of the right panel
- Resets all input fields to defaults
- Removes the saved result from browser localStorage (so it won't be restored on next visit)

**Note:** This does **not** delete anything from the Project Library — those are stored server-side and persist independently.

---

## 6. Main Studio Area

### 6.1 Theme & Creative Mode

#### Project Theme / Emotional Blueprint
**What it is:** The creative seed for the entire song. This is a free-text description of what the song should be about — emotionally, narratively, or conceptually.

**Examples:**
- `nostalgic late night drive in Seoul`
- `the feeling after a breakup in summer`
- `ambition in a city that doesn't care about you`
- `finding peace after years of anxiety`

**Tips:**
- Be specific and sensory — "a rainy Tuesday in a café with an old playlist" produces richer results than "sadness".
- You can reference places, times of day, seasons, relationships, or feelings.
- The theme directly shapes what the AI retrieves from the lyric database and what it writes.

---

#### Creative Process
**Options:** Generate New | Continue Story | Remix Style

| Mode | What it does |
|---|---|
| **Generate New** | Creates a completely fresh song from your theme and artist style. Default mode. |
| **Continue Story** | Extends the narrative from lyrics you provide in the Reference Lyrics box. Maintains exact tone and flow of the original. |
| **Remix Style** | Takes the core theme of your reference lyrics and rewrites it with entirely new wording, metaphors, and stylistic variations. A new "take" on the same song. |

**When to use Continue Story:** Paste the first verse of a song you've started (or previously generated) into Reference Lyrics, then click Continue Story — the AI writes the next section seamlessly.

**When to use Remix Style:** You have a lyric you like but want to explore a different angle or fresher language. It keeps the emotional DNA and discards the specific words.

---

#### Writing Perspective
**Options:** Same POV | Opposite Empathy | Response Verse

| Perspective | What it does |
|---|---|
| **Same POV** | Writes from the primary point of view of the theme — the narrator speaking their own experience. Default. |
| **Opposite Empathy** | Flips the emotional perspective. If the theme is regret, it writes from a place of defiance or indifference. |
| **Response Verse** | Treats the reference lyrics as a message received, and writes a reply from another character's perspective. |

**Tip:** **Response Verse** is powerful for creating dialogue-based songs or duets. Write a verse from one character's POV, then use Response Verse to write the reply.

---

### 6.2 Reference Lyrics (Context)

**What it is:** An optional text area where you paste existing lyrics — either lyrics you've written yourself, a previous generation from SonicFlow, or any other text.

**Used by:** Continue Story and Remix Style modes. In Generate New mode, reference lyrics are still available to the AI as context but don't dominate the output.

**How to use:** Simply paste the lyrics here (plain text, with or without section headers). The AI reads these as stylistic and narrative context.

---

### 6.3 Structure & Preset

**What it is:** The "blueprint" of your song — defines how many sections there are and in what order they appear.

**Available structures:**

| Structure | Sections | Best for |
|---|---|---|
| **Verse-Chorus (Pop/Rock)** | V1, Pre-C, C, V2, Pre-C, C, Bridge, C | Pop singles, most commercial formats |
| **Verse-Chorus-Bridge (Standard)** | V1, C, V2, C, Bridge, C | Classic songwriting format |
| **AABA (Jazz/Classic)** | A, A, B (Bridge), A | Jazz standards, classic pop |
| **Through-Composed (Narrative)** | Intro, S1, S2, S3, Outro | Storytelling, spoken word, cinematic |
| **Hook-Verse (Hip-Hop)** | Hook, V1, Hook, V2, Hook, Bridge, Hook | Hip-hop, trap, rap formats |
| **Extended (Album Track)** | Intro, V1, Pre-C, C, V2, Pre-C, C, Bridge, V3, Outro Chorus | Album tracks, extended productions |

**The section preview** (coloured tags below the dropdown) shows every section in the selected structure, in order. This helps you visualise the song layout before generating.

**How bars map to sections:** When you select a structure and a bar count, the system distributes the total bars proportionally across sections. Verses receive roughly twice the lines of choruses.

---

### 6.4 Ignite Production Button

The large primary button that starts the full generation pipeline.

**Disabled when:** A generation is already running.

**The Stop button:** While generation is in progress, a red **Stop** button appears to the right of the main button. Clicking it immediately cancels the in-flight request. Any partially completed steps are discarded.

---

### 6.5 Pipeline Status Panel

Appears as soon as generation starts. Shows the real-time status of each pipeline step:

| Step | Icon | What's happening |
|---|---|---|
| **Synthesizing Lyrical Theme** | 🧠 | RAG retrieval + GPT-4o generating lyrics |
| **Vocal Output (ElevenLabs)** | 🎤 | ElevenLabs converting lyrics to speech |
| **Full Song (Suno AI)** | 🎵 | Suno AI generating the full song |
| **AI Lyrical Analysis** | 🔍 | GPT analysis of the generated lyrics |

**Status indicators:**
- Grey circle = pending (not yet started)
- Spinning cyan = currently running
- Green checkmark = completed successfully
- Red circle = step failed (generation continues with other steps)

---

## 7. Production Output Panel

The right-hand panel shows all outputs from the most recent generation.

---

### 7.1 Vocal Output (ElevenLabs)

**What it is:** An MP3 audio file of the lyrics read aloud by ElevenLabs' Multilingual v2 voice model. This is an expressive text-to-speech rendering — not a singing voice. It gives you a feel for the rhythm and flow of the lyrics as spoken word.

**Controls:**
- **Play/Pause** — starts or pauses playback
- **Seek bar** — click anywhere to jump to that timestamp
- **Mute** — silences without stopping
- **Download** — saves the vocal MP3 to your device as `voice_HH:MM:SS.mp3`

**If it shows "Vocal generation failed":** Check that the ElevenLabs API key in `.env` is valid and has credits.

**Debug readout:** Below the section title, a small line shows `VOICE: X KB` — the size of the audio file received. A healthy generation is typically 200 KB – 2 MB.

---

### 7.2 Full Song Output (Suno AI)

**What it is:** A complete AI-generated song produced by Suno AI v4 — includes AI vocals singing the lyrics and a full musical arrangement (beat, melody, harmony). This is the main music output.

**Controls:** Same as Vocal Output — Play/Pause, seek, mute, Download (`music_HH:MM:SS.mp3`).

**If it shows "Music generation failed — check Suno credits or API":** This means either:
- Your sunoapi.org account has no remaining credits (top up at sunoapi.org)
- The Suno API returned an error (check EC2 logs with `journalctl -u sonicflow-api`)
- The system fell back to HuggingFace MusicGen (instrumental only, no vocals)

**Debug readout:** Shows `MUSIC: X KB`. A typical Suno song is 3–8 MB.

---

### 7.3 Lyrics Tab (📝)

Displays the full generated lyrics with section headers highlighted in a distinct style.

- Section headers (`[Verse 1]`, `[Chorus]`, etc.) appear in neon cyan
- Lyrical lines appear in the primary text colour
- The text is selectable and copyable

---

### 7.4 Insights Tab (💡)

Displays the AI Lyrical Analysis — a GPT-4o breakdown of the generated lyrics:

| Field | Meaning |
|---|---|
| **theme** | The core emotional/narrative theme identified in the lyrics |
| **tone** | The emotional atmosphere and mood of the piece |
| **ideas** | 2–3 creative suggestions for where the song could go next |
| **opposite_perspective** | A brief description of what the opposite emotional angle would be |
| **continuation** | How the narrative could logically continue |

**Use this for:** Creative direction, deciding whether to continue or remix, understanding what the AI "heard" in your theme.

---

### 7.5 Variants Tab (🌈)

Shows all generated lyric versions side by side.

- **Variant A, B, C…** — buttons switch between versions
- **Style Fidelity score** — a 0–1 score measuring how closely this variant's vocabulary matches the retrieved artist style examples. Higher = more authentic to the artist.
- The variant shown in the Lyrics tab is always the highest-scoring one.

**How to use:** If the primary lyrics don't feel right, switch to Variant B or C — a different set of metaphors and phrasings may suit your vision better.

---

### 7.6 Stats Tab (📊)

Shows technical metadata from the generation:

| Metric | Meaning |
|---|---|
| **Retrieval Quality** | 0–1 score. Mean hybrid similarity score across all retrieved lyric chunks. Higher = better artist style data found. |
| **Latency** | Total generation time in seconds (includes all pipeline steps). |
| **Retrieval Diagnostics** | Full breakdown: retrieval path used, number of chunks retrieved, top similarity scores, query type (emotional vs specific), expanded queries used. |

**Retrieval Quality guide:**
- 0.7+ — Excellent match. The system found strong stylistic examples for this artist.
- 0.4–0.7 — Moderate match. Artist data exists but may be limited.
- Below 0.4 — Weak match. Few or no examples found for this artist; style fingerprints are used as the primary guide.

---

## 8. Project Library

The Library stores metadata for every successfully generated project. Navigate to it via the **Library** link in the sidebar or by clicking **Library** in the header.

**URL:** `/library`

---

### 8.1 Stats Bar

Three cards at the top of the library:

| Card | Meaning |
|---|---|
| **Total Tracks** | Total number of saved projects |
| **With Voice** | Projects where ElevenLabs vocal generation succeeded |
| **With Music** | Projects where Suno AI music generation succeeded |

These update immediately when projects are deleted.

---

### 8.2 Project Cards

Each saved project appears as a card showing:

| Field | Meaning |
|---|---|
| **Artist — Title** | The artist selected and the project title (derived from the theme) |
| **Theme** | The project theme / emotional blueprint |
| **Timestamp** | Date and time the project was created |
| **Lyrics Preview** | First ~200 characters of lyrical content (section headers stripped) |
| **Voice tag** | Purple badge — ElevenLabs vocal was generated successfully |
| **Music tag** | Lime badge — Suno AI full song was generated successfully |
| **Duration** | Audio duration if recorded (in MM:SS format) |

---

### 8.3 Opening a Project in Studio

**How to:** Click anywhere on the project card. An **"Open in Studio →"** hint appears on hover.

**What happens:**
1. The project's `artist`, `theme`, and `lyrics` are written to browser localStorage
2. You are navigated to the Studio page (`/`)
3. The Studio reads the stored data and pre-fills:
   - **Artist field** — populated with the project's artist
   - **Theme field** — populated with the project's theme
   - **Reference Lyrics** — populated with the full lyrics text
4. A toast notification confirms: `"Opened: <project title>"`

**Use this to:** Re-read a previously generated song, continue its story (switch Creative Process to "Continue Story"), remix it (switch to "Remix Style"), or simply use it as context for a new generation.

**Note:** Audio files are not stored server-side (only metadata is saved). To re-listen to audio from a previous session in the **same browser session**, the audio is kept in memory until you click Clear Project or close the tab.

---

### 8.4 Deleting a Project

Each project card has a built-in **two-step delete** to prevent accidental deletion.

**How to delete:**

1. **Hover** over the project card → a faint trash icon (🗑) appears on the right side
2. **Click the trash icon** → the icon is replaced with a red **"Confirm"** button and a grey **✕** cancel button
3. **Click "Confirm"** → the project fades out (indicating deletion in progress) and disappears from the list
4. **Click ✕** at any point to cancel and return to normal

**What is deleted:** The project's metadata entry in `data/projects.json` on the server. The action is permanent — there is no undo.

**What is NOT deleted:** Any audio files you downloaded to your device. The deletion only affects the library listing.

---

### 8.5 Searching Projects

Use the **Search** input in the library header to filter projects in real time.

**Searches across:** Title, artist name, and theme text.

**How to use:** Type any part of a title, artist name, or theme. The list filters instantly. Clear the search field to see all projects again.

---

## 9. Account & Sign Out

The **Sign Out** button is in the sidebar navigation (Settings icon).

**What it does:** Removes your session token from the browser's localStorage and redirects you to the Login page. All unsaved audio in the current session is lost.

**Session persistence:** Your session token is stored in localStorage. If you close and reopen the browser, you remain logged in until you explicitly Sign Out.

**Credentials:**
- Email: `admin@studio.com`
- Password: `admins`

---

## 10. Complete Workflow Walkthroughs

### 10.1 Generate Your First Song

**Goal:** Create a full song from scratch in Drake's style about loneliness.

1. Log in at `http://3.239.91.199:3001`
2. In the **Artist** field, type `Drake` and select from suggestions
3. Set **Creativity** to `0.85`, **Style Strength** to `0.8`
4. Set **Language** to `English`, **Vocal Perspective** to `Male`
5. Set **Song Length** to `32` bars
6. Set **Creative Variants** to `3`
7. Make sure **Voice Synthesis** and **Music Production** are both ON
8. In **Project Theme**, type: `late night success, empty apartment`
9. Leave Reference Lyrics blank
10. Select **Verse-Chorus (Pop/Rock)** structure
11. Select **Generate New** Creative Process, **Same POV** perspective
12. Click **IGNITE PRODUCTION**
13. Wait for the pipeline to complete (2–8 minutes)
14. Listen to **Full Song Output** and read lyrics in the **📝 Lyrics** tab
15. If you prefer a different version, check **🌈 Variants** tab
16. The project is automatically saved to Library

---

### 10.2 Continue an Existing Story

**Goal:** Take a previously generated verse and write the next section.

1. Open the Studio and find your previous lyrics (from Library, or from the session history at the bottom of the right panel)
2. Copy the lyrics you want to continue from
3. Paste them into the **Reference Lyrics** box (Section 2)
4. Change **Creative Process** to `Continue Story`
5. Keep the same artist and theme, or adjust the theme to reflect where the story goes next
6. Click **IGNITE PRODUCTION**
7. The AI will write the continuation maintaining the same tone, flow, and vocabulary

---

### 10.3 Remix a Style

**Goal:** Take an existing song concept and rewrite it with a fresh angle.

1. Paste the lyrics to be remixed into **Reference Lyrics**
2. Set **Creative Process** to `Remix Style`
3. Optionally change the artist to explore how a different artist would approach the same theme
4. Click **IGNITE PRODUCTION**
5. The AI rewrites the core ideas with entirely new phrasing, metaphors, and structure

---

### 10.4 Revisit a Saved Song from Library

**Goal:** Re-read or continue a project from a past session.

1. Click **Library** in the sidebar
2. Use the **Search** bar to find the project by title, artist, or theme
3. Click the project card
4. You are taken back to Studio with the artist, theme, and lyrics pre-filled
5. Read the lyrics in the **Reference Lyrics** box, or click **IGNITE PRODUCTION** to generate a continuation or remix

---

### 10.5 Download Audio Files

**Goal:** Save the generated audio to your device.

1. After a successful generation, locate the **Vocal Output** or **Full Song Output** player in the output panel
2. Click the **Download** button (arrow icon) on the audio player
3. The file saves to your device:
   - Vocal: `voice_HH:MM:SS.mp3`
   - Full Song: `music_HH:MM:SS.mp3`

**Tip:** Download immediately after generation — audio blobs are held in browser memory and are cleared if you refresh, close the tab, or click Clear Project.

---

## 11. Glossary of Terms

| Term | Definition |
|---|---|
| **Bars** | In music, a "bar" is a unit of rhythm. In SonicFlow, 1 bar = 1 lyrical line. Setting "32 bars" means the song will have 32 lyrical lines total (not counting section headers). |
| **RAG** | Retrieval-Augmented Generation. The system retrieves real lyric examples from a database and gives them to the AI as context, resulting in more stylistically authentic output than pure generation. |
| **FAISS** | Facebook AI Similarity Search. A vector database that enables fast semantic search over millions of lyric chunks. |
| **BM25** | Best Match 25. A classical keyword-based search algorithm. Combined with FAISS for hybrid retrieval. |
| **Style Fidelity** | A 0–1 score measuring how closely a generated lyric variant's vocabulary overlaps with the retrieved artist examples. |
| **Retrieval Quality** | A 0–1 score for how well the FAISS index matched the query. High = strong artist data; low = sparse data for this artist. |
| **Temperature** | An AI model parameter (0–2) controlling output randomness. Higher = more creative/unpredictable. In SonicFlow this is labelled "Creativity". |
| **ElevenLabs** | An AI voice synthesis platform. Converts text to expressive speech. Used here to read the generated lyrics aloud. |
| **Suno AI** | An AI music generation model capable of producing complete songs with AI vocals and musical arrangement from a text prompt. |
| **HuggingFace MusicGen** | An open-source AI model by Meta that generates instrumental audio from a text prompt. Used as fallback when Suno is unavailable. |
| **Base64 (b64)** | An encoding format used to transfer binary audio data (MP3 bytes) through JSON APIs. The browser decodes it back into playable audio. |
| **Session Token** | A shared authentication credential stored in localStorage. Required for all API calls. Clears on Sign Out. |
| **sunoapi.org** | A third-party API wrapper that provides programmatic access to Suno AI's music generation via REST endpoints. |
| **Vocal Stem** | An audio track containing only vocals, no music. In SonicFlow, the ElevenLabs output is sometimes referred to as the vocal stem. |
| **Full Song** | The Suno AI output — a complete song with both AI-sung vocals and a musical arrangement. Not an instrumental. |
| **systemd** | A Linux service manager used on the EC2 server to keep SonicFlow's API and Next.js frontend running as background services that auto-restart on failure. |
| **localStorage** | Browser-level storage (per device, per browser). Used to persist your session token, most recent studio result, and session history across page navigations. |

---

## 12. Troubleshooting

### "Music generation failed — check Suno credits or API"
- **Cause:** Suno API credits are exhausted or the API key is invalid.
- **Fix:** Log in to [sunoapi.org](https://sunoapi.org) and top up credits. The system will automatically retry with HuggingFace MusicGen as fallback.

### "Vocal generation failed — check ElevenLabs API key"
- **Cause:** The ElevenLabs API key is missing, invalid, or out of character credits.
- **Fix:** Check `ELEVENLABS_API_KEY` in the server's `.env` file. Log in to ElevenLabs and verify remaining credits.

### Generation is taking very long (> 10 minutes)
- **Cause:** Suno AI is experiencing high queue times.
- **Fix:** Wait it out (Suno can take up to 5 minutes per song). Alternatively, disable **Music Production** in the sidebar to skip Suno and generate lyrics + vocal only, which completes in under 30 seconds.

### The Library shows "Network Error"
- **Cause:** The browser cannot reach the FastAPI backend on port 8000.
- **Fix:** Ensure the EC2 security group allows inbound traffic on port 8000 from your IP. Check that `NEXT_PUBLIC_API_URL` is set to the EC2 public IP (not `localhost`).

### Lyrics are too short / too long
- **Cause:** The bar count and structure don't match expectations.
- **Fix:** Increase **Song Length** to 32 bars for a full song. The system strictly enforces the bar count: section headers are not counted, only lyrical lines.

### Style doesn't feel like the artist
- **Cause 1:** Style Strength is too low. Increase to 0.8+.
- **Cause 2:** The artist has limited data in the index. Try increasing Creative Variants to 5 and checking the Stats tab — if Retrieval Quality is below 0.4, the index has sparse data for this artist.

### "Invalid or missing token" error
- **Cause:** Your session has expired or localStorage was cleared.
- **Fix:** Sign in again at `/login` with `admin@studio.com` / `admins`.

### The Stop button doesn't immediately cancel audio
- **Note:** The Stop button cancels the HTTP request to the backend. However, Suno AI continues processing server-side. The audio will not appear in the UI, but the Suno credit has been consumed. To avoid wasted credits, only stop if the lyrics step is still running.

---

*SonicFlow Studio v3 — AI Songwriting System*
*Branch: feature/final-production-hardening | Deployment: EC2 3.239.91.199 | API Version: 3.0.0*
