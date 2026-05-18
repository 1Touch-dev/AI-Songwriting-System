export type OutputMode = 'draft' | 'music_demo' | 'producer'

export interface GenreBlend {
  primary: string
  secondary: string
  weight: number  // 0=all primary, 1=all secondary
}

export interface ProducerControlsInput {
  darkness: number
  melodicness: number
  aggression: number
  atmosphere: number
  groove_density: number
}

export interface CadenceMeta {
  source?: string
  rhyme_scheme: string
  rhyme_density: number
  avg_syllables_per_line: number
  flow_density: string
  stress_style: string
  phrase_momentum: string
}

export interface GenerateParams {
  artists: string[]
  theme: string
  structure: string[]
  language: string
  gender: string
  bars: number
  reference_lyrics: string
  num_variants: number
  temperature: number
  style_strength: number
  gen_mode: 'generate' | 'continue' | 'remix'
  perspective_mode: 'same' | 'opposite' | 'response'
  output_mode: OutputMode      // draft | music_demo | producer
  enable_mix: boolean          // explicit request to mix vocal + uploaded instrumental
  remix_mode: boolean
  locked_chorus: string
  section_mode: string         // 'Full Song' | 'Verse Only'
  chorus_strict: boolean
  producer_mode: boolean
  // Intelligence Layer
  target_genre?: string
  genre_blend?: GenreBlend
  producer_controls?: ProducerControlsInput
}

export interface StemJob {
  job_id: string
  status: 'processing' | 'done' | 'failed' | 'not_found'
  stems: Record<string, string>
  error: string | null
  elapsed_s: number
}

export interface LyricVariant {
  lyrics: string
  style_fidelity: number
}

export interface AudioMetadata {
  bpm: number
  key: string
}

export interface GenerateResult {
  lyrics: string
  theme: string
  versions: LyricVariant[]
  retrieval_quality: number
  latency_ms: number
  retrieval_diagnostics: Record<string, unknown>
  analysis: Record<string, unknown> | null
  voice_audio_b64: string | null
  music_audio_b64: string | null
  mixed_audio_b64: string | null
  voice_error: string | null
  music_error: string | null
  mix_error: string | null
  locked_chorus: string | null
  instrumental_hint: string | null
  output_mode: string
  timestamp: string
  audio_metadata: AudioMetadata | null
  chorus_preserved: boolean | null
  music_job_id?: string | null
  cadence_meta?: CadenceMeta | null
  suno_style_tags?: string | null
}

export interface Project {
  id: string
  title: string
  theme: string
  artist: string
  lyrics: string
  timestamp: string
  duration_s: number
  has_voice: boolean
  has_music: boolean
  has_mix: boolean
  voice_url: string | null
  music_url: string | null
  mix_url: string | null
  // Generation inputs
  language: string | null
  bars: number | null
  structure: string | null
  gen_mode: string | null
  perspective_mode: string | null
  gender: string | null
  style_strength: number | null
  temperature: number | null
  chorus_strict: boolean | null
  producer_mode: boolean | null
  section_mode: string | null
  ref_lyrics: string | null
  analysis: Record<string, unknown> | null
  stem_job_id: string | null
  stems: Record<string, string> | null
}

export type GenMode = 'Generate New' | 'Continue Story' | 'Remix Style'
export type PerspectiveMode = 'Same POV' | 'Opposite Empathy' | 'Response Verse'
export type SectionMode = 'Full Song' | 'Verse Only'
export type ProducerVocalSource = 'suno_singing' | 'reference_tts'
export type Language =
  | 'English' | 'Spanish' | 'French' | 'German'
  | 'Hindi' | 'Arabic' | 'Portuguese' | 'Japanese'
  | 'Korean' | 'Chinese'

export interface StudioState {
  artist: string
  theme: string
  refLyrics: string
  structure: string
  genMode: GenMode
  perspective: PerspectiveMode
  language: Language
  gender: 'Neutral' | 'Male' | 'Female'
  bars: 4 | 8 | 16 | 32
  numVariants: 1 | 3 | 5
  temperature: number
  styleStrength: number
  outputMode: OutputMode
  enableMix: boolean           // explicit mix request (Draft mode only)
  producerVocalSource: ProducerVocalSource
  sectionMode: SectionMode
  chorusStrict: boolean
  producerMode: boolean
  fastMode: boolean
}

// Global artist data from /global-artists
export type GlobalArtists = Record<string, Record<string, string[]>>

// ── Intelligence Layer types ──────────────────────────────────────────────────

export interface AudioAnalysisResult {
  bpm: number
  bpm_confidence: number
  tempo_variation: string
  key: string
  root: string
  mode: string
  key_confidence: number
  chords: string[]
  energy_intensity: string
  dynamic_range_db: number
  section_energies: number[]
  onset_density: number
  syllable_density: number
  flow_descriptors: string[]
  stress_pattern: string
  detected_sections: string[]
  total_duration_s: number
  prompt_hint: string
  suno_tags: string
  analysis_latency_ms: number
  error: string | null
}

export interface GenreProfile {
  name: string
  tempo_range: [number, number]
  groove: string
  instrumentation: string[]
  energy_curve: string
  vocal_style: string
  prompt_tokens: string[]
  darkness: number
  melodicness: number
  aggression: number
  atmosphere: number
  groove_density: number
}

export interface ProducerControls {
  darkness: number
  melodicness: number
  aggression: number
  atmosphere: number
  groove_density: number
}

export interface RemixVariant {
  genre: string
  lyrics: string
  locked_chorus: string
  suno_tags: string
  style_notes: string
  instrumentation: string[]
  bpm_target: number
  cadence_match_score: number
}

export interface CadenceProfile {
  rhyme_scheme: string
  rhyme_density: number
  avg_words_per_line: number
  avg_syllables_per_line: number
  line_length_pattern: string
  flow_density: string
  stress_style: string
  phrase_momentum: string
  cadence_descriptors: string[]
  constraint_block: string
}

export interface ProductionAnalysis {
  hook: {
    score: number
    replayability: number
    strengths: string[]
    weaknesses: string[]
    suggested_rewrites: string[]
  }
  arrangement: {
    section_balance: Record<string, number>
    energy_arc: string
    is_chorus_heavy: boolean
    is_verse_heavy: boolean
    suggestions: string[]
  }
  emotional_arc: {
    detected_tone: string
    journey: string[]
    tension_points: string[]
    resolution: string
    coherence_score: number
  }
  remix_suggestions: Array<{
    genre: string
    rationale: string
    bpm_shift: string
    key_suggestion: string
  }>
  overall_score: number
  producer_notes: string[]
  llm_analysis: Record<string, unknown> | null
}
