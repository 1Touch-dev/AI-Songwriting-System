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
  enable_voice: boolean
  enable_music: boolean
  remix_mode: boolean
  locked_chorus: string
  section_mode: string         // 'Full Song' | 'Verse Only'
  chorus_strict: boolean       // natural vs strict 3-line hook
  producer_mode: boolean       // producer mode toggle
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
  timestamp: string
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
}

export type GenMode = 'Generate New' | 'Continue Story' | 'Remix Style'
export type PerspectiveMode = 'Same POV' | 'Opposite Empathy' | 'Response Verse'
export type SectionMode = 'Full Song' | 'Verse Only'
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
  enableVoice: boolean
  enableMusic: boolean
  sectionMode: SectionMode
  chorusStrict: boolean
  producerMode: boolean
  fastMode: boolean
}

// Global artist data from /global-artists
export type GlobalArtists = Record<string, Record<string, string[]>>
