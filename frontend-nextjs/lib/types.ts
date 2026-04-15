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
  voice_audio_b64: string | null   // base64-encoded MP3
  music_audio_b64: string | null
  mixed_audio_b64: string | null
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
}

export type GenMode = 'Generate New' | 'Continue Story' | 'Remix Style'
export type PerspectiveMode = 'Same POV' | 'Opposite Empathy' | 'Response Verse'
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
}
