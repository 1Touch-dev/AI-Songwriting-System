"""
Shared configuration: target artists, paths, constants.
"""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
INDEX_DIR = DATA_DIR / "faiss_index"
CACHE_DIR = DATA_DIR / "cache"
LOGS_DIR = ROOT_DIR / "logs"
EVAL_DIR = ROOT_DIR / "evaluation"

for _d in (RAW_DIR, PROCESSED_DIR, INDEX_DIR, CACHE_DIR, LOGS_DIR, EVAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── File paths ─────────────────────────────────────────────────────────────
CLEANED_SONGS_PATH = PROCESSED_DIR / "cleaned_songs.jsonl"
LABELED_SONGS_PATH = PROCESSED_DIR / "labeled_songs.jsonl"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"
FAISS_INDEX_PATH = INDEX_DIR / "lyrics.index"
FAISS_META_PATH = INDEX_DIR / "lyrics_meta.jsonl"
EMBED_CACHE_PATH = CACHE_DIR / "embeddings.pkl"
GEN_LOG_PATH = LOGS_DIR / "generation_logs.jsonl"
EVAL_RESULTS_PATH = EVAL_DIR / "results.json"

# ── Target artists (~75 diverse artists) ──────────────────────────────────
TARGET_ARTISTS = [
    # Hip-Hop / Rap
    "Drake", "Kendrick Lamar", "J. Cole", "Travis Scott", "Future",
    "Lil Wayne", "Nicki Minaj", "Cardi B", "Post Malone", "21 Savage",
    "Juice WRLD", "Roddy Ricch", "DaBaby", "Lil Baby", "Gunna",
    "Tyler the Creator", "A$AP Rocky", "Childish Gambino", "Logic", "Big Sean",
    # Pop
    "Taylor Swift", "Ariana Grande", "Billie Eilish", "Dua Lipa", "The Weeknd",
    "Harry Styles", "Olivia Rodrigo", "Doja Cat", "SZA", "Lizzo",
    "Justin Bieber", "Ed Sheeran", "Shawn Mendes", "Camila Cabello", "Halsey",
    "Selena Gomez", "Katy Perry", "Lady Gaga", "Beyonce", "Rihanna",
    # R&B / Soul
    "Bruno Mars", "John Legend", "Frank Ocean", "H.E.R.", "Daniel Caesar",
    "Khalid", "Summer Walker", "6lack", "Giveon", "Lucky Daye",
    # Rock / Alternative
    "Imagine Dragons", "Twenty One Pilots", "Panic! at the Disco",
    "Fall Out Boy", "Paramore", "Linkin Park", "Green Day", "Coldplay",
    "Radiohead", "Arctic Monkeys",
    # Country
    "Morgan Wallen", "Luke Combs", "Kane Brown", "Chris Stapleton", "Zac Brown Band",
    # Latin
    "Bad Bunny", "J Balvin", "Ozuna", "Daddy Yankee", "Maluma",
    # Electronic / Dance
    "Marshmello", "Kygo", "Calvin Harris", "Diplo", "Skrillex",
]

# ── Artist → genre mapping for fallback retrieval ─────────────────────────
ARTIST_GENRE_MAP: dict[str, str] = {
    "Drake": "hip-hop", "Kendrick Lamar": "hip-hop", "J. Cole": "hip-hop",
    "Travis Scott": "hip-hop", "Future": "hip-hop", "Lil Wayne": "hip-hop",
    "Nicki Minaj": "hip-hop", "Cardi B": "hip-hop", "Post Malone": "hip-hop",
    "21 Savage": "hip-hop", "Juice WRLD": "hip-hop", "Roddy Ricch": "hip-hop",
    "DaBaby": "hip-hop", "Lil Baby": "hip-hop", "Gunna": "hip-hop",
    "Tyler the Creator": "hip-hop", "A$AP Rocky": "hip-hop",
    "Childish Gambino": "hip-hop", "Logic": "hip-hop", "Big Sean": "hip-hop",
    "Taylor Swift": "pop", "Ariana Grande": "pop", "Billie Eilish": "pop",
    "Dua Lipa": "pop", "Harry Styles": "pop", "Olivia Rodrigo": "pop",
    "Doja Cat": "pop", "Lizzo": "pop", "Justin Bieber": "pop",
    "Ed Sheeran": "pop", "Shawn Mendes": "pop", "Camila Cabello": "pop",
    "Halsey": "pop", "Selena Gomez": "pop", "Katy Perry": "pop",
    "Lady Gaga": "pop", "Beyonce": "pop", "Rihanna": "pop",
    "The Weeknd": "r&b", "SZA": "r&b", "Bruno Mars": "r&b",
    "John Legend": "r&b", "Frank Ocean": "r&b", "H.E.R.": "r&b",
    "Daniel Caesar": "r&b", "Khalid": "r&b", "Summer Walker": "r&b",
    "6lack": "r&b", "Giveon": "r&b", "Lucky Daye": "r&b",
    "Imagine Dragons": "rock", "Twenty One Pilots": "rock",
    "Panic! at the Disco": "rock", "Fall Out Boy": "rock",
    "Paramore": "rock", "Linkin Park": "rock", "Green Day": "rock",
    "Coldplay": "rock", "Radiohead": "rock", "Arctic Monkeys": "rock",
    "Morgan Wallen": "country", "Luke Combs": "country",
    "Kane Brown": "country", "Chris Stapleton": "country",
    "Zac Brown Band": "country",
    "Bad Bunny": "latin", "J Balvin": "latin", "Ozuna": "latin",
    "Daddy Yankee": "latin", "Maluma": "latin",
    "Marshmello": "electronic", "Kygo": "electronic",
    "Calvin Harris": "electronic", "Diplo": "electronic", "Skrillex": "electronic",
}

# ── Songs per artist ────────────────────────────────────────────────────────
SONGS_PER_ARTIST = 25

# ── Model config ─────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
GENERATION_MODEL = "gpt-4.1"           # best quality for lyric generation
LABELING_MODEL = "gpt-4.1-mini"        # sufficient for structured JSON extraction

# ── Generation settings ───────────────────────────────────────────────────
GENERATION_TEMPERATURE = 0.85      # default; UI can override
GENERATION_MAX_TOKENS = 1200

# ── RAG retrieval ─────────────────────────────────────────────────────────
TOP_K = 8                          # default number of chunks to retrieve
FALLBACK_TOP_K = 16                # used when artist-filtered results are sparse
MIN_CHUNKS_THRESHOLD = 3           # below this → trigger genre fallback
MAX_RETRY_ATTEMPTS = 3             # generation retries on failure

# ── Hybrid retrieval (vector + BM25 keyword) ───────────────────────────────
VECTOR_WEIGHT = 0.70               # weight for FAISS cosine similarity score
BM25_WEIGHT = 0.30                 # weight for BM25 keyword score
BM25_K1 = 1.5                      # BM25 term frequency saturation
BM25_B = 0.75                      # BM25 length normalisation

# ── LLM reranking (optional, off by default — costs API credits) ───────────
RERANK_ENABLED = False             # set True to enable LLM re-ranking
RERANK_CANDIDATE_N = 12            # retrieve this many, re-rank, keep TOP_K
RERANK_MODEL = "gpt-4.1-nano"           # simple ranking task — nano is sufficient

# ── Prompt versioning ──────────────────────────────────────────────────────
PROMPT_VERSION = "v3"              # bump when prompt template changes

# ── Style strength ─────────────────────────────────────────────────────────
STYLE_STRENGTH_DEFAULT = 0.7       # 0.0 = loose inspiration, 1.0 = strict imitation

# ── Evaluation ────────────────────────────────────────────────────────────
EVAL_DETAILED_RESULTS_PATH = EVAL_DIR / "detailed_results.json"
EVAL_JUDGE_MODEL = "gpt-4.1-mini"   # model used for LLM-as-judge scoring
