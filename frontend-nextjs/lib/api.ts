import axios from 'axios'
import type { GenerateParams, GenerateResult, GlobalArtists, CadenceMeta } from './types'

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 600_000,
})

export async function login(email: string, password: string): Promise<{ token: string }> {
  const res = await client.post('/login', { email, password })
  return res.data
}

/**
 * Generate lyrics + audio. Sends multipart/form-data so an optional
 * instrumental file can be included alongside the JSON params.
 */
export async function generateSong(
  params: GenerateParams,
  token: string,
  signal?: AbortSignal,
  instrumentalFile?: File | null,
): Promise<GenerateResult> {
  const form = new FormData()
  form.append('payload', JSON.stringify(params))
  if (instrumentalFile) {
    form.append('instrumental', instrumentalFile, instrumentalFile.name)
  }
  const res = await client.post('/generate', form, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  return res.data
}

export async function searchArtists(query: string): Promise<string[]> {
  const res = await client.get('/artists/search', { params: { q: query } })
  return res.data.results ?? []
}

export async function getGlobalArtists(language?: string): Promise<GlobalArtists> {
  const res = await client.get('/global-artists', {
    params: language ? { language } : {},
    timeout: 5_000,
  })
  return res.data.artists ?? {}
}

export async function getProjects(token: string): Promise<import('./types').Project[]> {
  const res = await client.get('/projects', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data.projects ?? []
}

export interface SaveProjectPayload {
  title: string
  theme: string
  artist: string
  lyrics: string
  has_voice: boolean
  has_music: boolean
  has_mix?: boolean
  duration_s?: number
  voice_audio_b64?: string | null
  music_audio_b64?: string | null
  mixed_audio_b64?: string | null
  language?: string | null
  bars?: number | null
  structure?: string | null
  output_mode?: string | null
  gen_mode?: string | null
  perspective_mode?: string | null
  gender?: string | null
  style_strength?: number | null
  temperature?: number | null
  chorus_strict?: boolean | null
  producer_mode?: boolean | null
  section_mode?: string | null
  ref_lyrics?: string | null
  analysis?: Record<string, unknown> | null
  stem_job_id?: string | null
}

export async function saveProject(
  token: string,
  data: SaveProjectPayload,
): Promise<import('./types').Project> {
  const res = await client.post('/projects', data, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 30_000,
  })
  return res.data
}

export function audioUrl(path: string | null): string | null {
  if (!path) return null
  if (path.startsWith('http')) return path
  return `${BASE_URL}${path}`
}

export async function deleteProject(token: string, projectId: string): Promise<void> {
  await client.delete(`/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function b64ToAudioUrl(b64: string): string {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'audio/mpeg' })
  return URL.createObjectURL(blob)
}

export function b64ToDownloadUrl(b64: string, filename: string): void {
  const url = b64ToAudioUrl(b64)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function extractChorus(
  token: string,
  lyrics: string
): Promise<{ chorus: string; found: boolean }> {
  const res = await client.post('/chorus/extract', { lyrics }, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 20_000,
  })
  return res.data
}

export async function extractStems(
  token: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<{ job_id: string; status: string; filename: string; size_kb: number }> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post('/stems/extract', form, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 60_000,
    onUploadProgress: e => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
  return res.data
}

export async function getStemStatus(
  token: string,
  jobId: string
): Promise<import('./types').StemJob> {
  const res = await client.get(`/stems/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 10_000,
  })
  return res.data
}

// ── Intelligence Layer API ────────────────────────────────────────────────────

export async function analyzeTrack(
  token: string,
  file: File,
): Promise<import('./types').AudioAnalysisResult> {
  const form = new FormData()
  form.append('file', file, file.name)
  const res = await client.post('/analyze-track', form, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 60_000,
  })
  return res.data
}

export async function getGenres(token: string): Promise<import('./types').GenreProfile[]> {
  const res = await client.get('/genres', {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 5_000,
  })
  return res.data.genres ?? []
}

export async function blendGenres(
  token: string,
  primary: string,
  secondary: string,
  weight: number,
) {
  const res = await client.post('/blend-genres', { primary, secondary, weight }, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 5_000,
  })
  return res.data
}

export async function extractCadence(
  token: string,
  lyrics: string,
): Promise<import('./types').CadenceProfile> {
  const res = await client.post('/extract-cadence', { lyrics }, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 10_000,
  })
  return res.data
}

export async function generateRemixVariants(
  token: string,
  params: {
    locked_chorus: string
    original_lyrics: string
    theme: string
    artists: string[]
    target_genres: string[]
    bars: number
    language: string
    producer_controls?: import('./types').ProducerControls
  },
): Promise<{ variants: import('./types').RemixVariant[]; count: number }> {
  const res = await client.post('/generate-variants', params, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 300_000,
  })
  return res.data
}

export async function downloadDAWSession(
  token: string,
  params: {
    title: string
    artist: string
    theme: string
    lyrics: string
    language?: string
    bpm?: number
    key?: string
    bars?: number
    darkness?: number
    chords?: string[]
    voice_audio_b64?: string | null
    music_audio_b64?: string | null
    mix_audio_b64?: string | null
  },
): Promise<Blob> {
  const res = await client.post('/generate-daw-session', params, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 60_000,
    responseType: 'blob',
  })
  return res.data
}

export async function analyseProduction(
  token: string,
  lyrics: string,
  theme: string,
  artists: string[],
  useLlm = true,
): Promise<import('./types').ProductionAnalysis> {
  const res = await client.post('/analyse-production',
    { lyrics, theme, artists, use_llm: useLlm },
    { headers: { Authorization: `Bearer ${token}` }, timeout: 30_000 },
  )
  return res.data
}

export async function getMusicJobStatus(
  token: string,
  jobId: string,
): Promise<{ job_id: string; status: string; audio_b64: string | null; error: string | null; elapsed_s: number }> {
  const res = await client.get(`/music-status/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 10_000,
  })
  return res.data
}
