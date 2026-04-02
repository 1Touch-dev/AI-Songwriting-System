# AI Songwriting System: Technical White Paper

## _Hybrid Retrieval-Augmented Generation for Stylistic Lyric Synthesis_

---

## 1. Executive Summary

The **AI Songwriting System** is a production-grade RAG (Retrieval-Augmented Generation) pipeline designed to bridge the gap between creative songwriting and large-scale language modeling. By grounding its generation in 685 real-world pop and hip-hop songs, the system produces lyrics that maintain the consistent "voice" of an artist while conforming to modern song structures (Verse-Chorus-Bridge).

---

## 2. Quick Start Guide (For New Users)

If you are using the system for the first time, follow these three steps for an optimal result:

1.  **Select your Artist**: Choose an artist whose style you want to emulate from the dropdown.
2.  **Define a Theme**: Enter 3-5 words describing the mood (e.g., "late night drive, nostalgia").
3.  **Hit Generate**: Wait 15 seconds for the AI to search the database and compose your song.

---

## 3. Project Scope & Architecture

### 3.1 Technical Foundation

The system is built on a **Hybrid RAG** engine, which significantly outperforms standard vector-only retrieval for creative tasks:

1.  **Vector Search (70% weight)**: Captures semantic "vibe," emotional themes, and general metaphors using OpenAI's `text-embedding-3-small` model.
2.  **Keyword Search (30% weight)**: Utilizes the BM25 algorithm to ensure the artist's specific vocabulary, slang, and proper nouns are preserved.

### 3.2 Model Stack

- **Generation Engine**: `gpt-4o` (Optimised for creative variety and structure adherence).
- **Data Classifier**: `gpt-4o-mini` (Efficiently extracts themes and sections).
- **Vector Database**: FAISS (High-performance indexing and retrieval).

---

## 4. Operational Configuration (UI Settings)

The system provides intuitive controls to fine-tune the songwriting process. Understanding these "knobs" is key to getting the best results.

### 4.1 Creativity (Temperature)

- **What it is**: Controls the "randomness" or "originality" of the AI.
- **Range**: 0.5 (Conservative) to 1.0 (Experimental).
- **Recommendation**: Keep this near **0.85** for most projects. If the lyrics feel too repetitive, increase it. If they feel non-sensical, decrease it.

### 4.2 Style Strength

- **What it is**: Adjusts how much the AI "copies" the specific phrasing and rhythm of the retrieved examples.
- **Range**: 0.0 (Loose) to 1.0 (Strict).
- **Recommendation**: Use **0.70** (Moderate/Strict) if you want a clear "Artist Vibe". Use lower values (0.30) if you just want general inspiration.

### 4.3 Retrieved Examples (Top-K)

- **What it is**: The number of real-world "context chunks" (snippets of actual lyrics) fed into the AI's "short-term memory" before it writes.
- **Range**: 2 to 16.
- **Recommendation**: Set to **8** for a good balance of speed and stylistic accuracy.

### 4.4 Retrieval Quality

- **What it is**: A mathematical score (0.0 to 1.0) showing how well the system matched your "Theme" to the Artist's actual lyrics.
- **Interpretation**:
  - (High) **0.65+ (High)**: Excellent match; expect very authentic lyrics.
  - (Fair) **0.35 - 0.65 (Fair)**: Good match; result will be solid but may need "Extra Instructions".
  - (Low) **Below 0.35 (Low)**: The system struggled to find direct matches. Consider simplifying your theme.

---

## 5. Data Integrity & Composition

### 5.1 Data Acquisition

Our datasets are sourced from a combination of the **Hugging Face (`smgriffin/modern-pop-lyrics`)** dataset and real-time **Genius.com** scraping via **Apify**.

### 5.2 Dataset Metrics

- **Artist Diversity**: 33 High-Profile Artists (including Kendrick Lamar, Drake, SZA).
- **Song Count**: 685 fully labeled songs.
- **Knowledge Base**: 5,110 searchable segments (chunks).
- **Average Chunk Depth**: ~50 words (finely tuned for stylistic context injection).

---

## 6. Testing & Quality Assurance

To verify a successful deployment and see the system in action, follow this standard test case.

### 6.1 Pre-Flight Check (Sidebar)

Before starting, look at the **Index Status** in the left sidebar. Ensure these have green checkmarks:

- [OK] **Labeled Songs**: The AI has "read" and categorized the database.
- [OK] **Chunks**: The songs are broken into searchable segments.
- [OK] **FAISS Index**: The "Vector Search" engine is ready.

### 6.2 Step-by-Step Generation Example

Follow these exact steps to generate a "Kendrick Lamar" style song:

| Step  | Action              | Item / Input                         | Why we do this                                                                 |
| :---- | :------------------ | :----------------------------------- | :----------------------------------------------------------------------------- |
| **1** | **Select Artist**   | `Kendrick Lamar`                     | Defines the "Stylistic Target" (vocabulary, flow, rhyming).                    |
| **2** | **Enter Theme**     | `social justice and personal growth` | Defines the "Topic" or "Soul" of the song.                                     |
| **3** | **Set Preset**      | `Standard (V-C-V-C-B-C)`             | Defines the "Roadmap" (Verse 1 → Chorus → Verse 2 → Chorus → Bridge → Chorus). |
| **4** | **Add Detail**      | _Optional_: `mention Los Angeles`    | Adds custom constraints to make it unique.                                     |
| **5** | **Adjust settings** | `Creativity: 0.85` / `Style: 0.70`   | Balances "Originality" vs "Artist Mimicry".                                    |
| **6** | **Generate**        | Click **Generate Lyrics**            | Triggers the RAG pipeline.                                                     |

---

## 7. Glossary of Terms

- **RAG (Retrieval-Augmented Generation)**: The core technology. Instead of "guessing" style, the AI searches a database of real lyrics first, "reads" them, and then writes the new song based on those facts.
- **Chunking**: The process of breaking a full song into 3-4 smaller pieces (Verses, Choruses) so the search engine can be more precise.
- **Embeddings**: A method of turning words into mathematical "vectors" so the AI can find lyrics with the same "meaning" even if they use different words.
- **FAISS Index**: A specialized "search index" created by Meta that allows the system to search millions of lyric chunks in milliseconds.
- **Hybrid search**: Combining **Vector Search** (meaning-based) and **Keyword Search** (exact-word-based) to get the best of both worlds.

---

© 2026 AI Songwriting Team · Confidential Technical Manual
