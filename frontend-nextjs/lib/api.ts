import axios from 'axios'
import type { GenerateParams, GenerateResult } from './types'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 600_000,  // 10 min — Suno webhook can take up to 5 min
})

export async function login(email: string, password: string): Promise<{ token: string }> {
  const res = await client.post('/login', { email, password })
  return res.data
}

export async function generateSong(
  params: GenerateParams,
  token: string,
  signal?: AbortSignal
): Promise<GenerateResult> {
  const res = await client.post('/generate', params, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  return res.data
}

export async function searchArtists(query: string): Promise<string[]> {
  const res = await client.get('/artists/search', { params: { q: query } })
  return res.data.results ?? []
}

export async function getProjects(token: string): Promise<import('./types').Project[]> {
  const res = await client.get('/projects', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data.projects ?? []
}

export async function saveProject(
  token: string,
  data: {
    title: string
    theme: string
    artist: string
    lyrics: string
    has_voice: boolean
    has_music: boolean
    duration_s?: number
  }
): Promise<import('./types').Project> {
  const res = await client.post('/projects', data, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data
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
