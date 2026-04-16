'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  Music2, Mic2, Sliders, ChevronDown, ChevronRight,
  Radio, Upload, Trash2, Library, Zap, Settings,
  AlertCircle, Info, RotateCcw, Square
} from 'lucide-react'
import toast from 'react-hot-toast'
import AudioPlayer from '@/components/AudioPlayer'
import GenerationStatus, { PipelineStep } from '@/components/GenerationStatus'
import type { GenerateResult, StudioState, Language, GenMode, PerspectiveMode } from '@/lib/types'
import { generateSong, searchArtists, b64ToDownloadUrl, saveProject } from '@/lib/api'

// ── Song structures (matches Python STRUCTURES dict) ──────────────────────
const STRUCTURES: Record<string, string[]> = {
  'Verse-Chorus (Pop/Rock)': ['[Verse 1]','[Pre-Chorus]','[Chorus]','[Verse 2]','[Pre-Chorus]','[Chorus]','[Bridge]','[Chorus]'],
  'Verse-Chorus-Bridge (Standard)': ['[Verse 1]','[Chorus]','[Verse 2]','[Chorus]','[Bridge]','[Chorus]'],
  'AABA (Jazz/Classic)': ['[A Section]','[A Section]','[B Section (Bridge)]','[A Section]'],
  'Through-Composed (Narrative)': ['[Intro]','[Section 1]','[Section 2]','[Section 3]','[Outro]'],
  'Hook-Verse (Hip-Hop)': ['[Hook]','[Verse 1]','[Hook]','[Verse 2]','[Hook]','[Bridge]','[Hook]'],
  'Extended (Album Track)': ['[Intro]','[Verse 1]','[Pre-Chorus]','[Chorus]','[Verse 2]','[Pre-Chorus]','[Chorus]','[Bridge]','[Verse 3]','[Outro Chorus]'],
}

const LANGUAGES: Language[] = ['English','Spanish','French','German','Hindi','Arabic','Portuguese','Japanese','Korean','Chinese']
const GEN_MODES: GenMode[] = ['Generate New','Continue Story','Remix Style']
const PERSPECTIVES: PerspectiveMode[] = ['Same POV','Opposite Empathy','Response Verse']

const SESSION_TOKEN_KEY = 'sonicflow_token'

// ── Default state ─────────────────────────────────────────────────────────
const DEFAULT_STATE: StudioState = {
  artist: '',
  theme: '',
  refLyrics: '',
  structure: 'Verse-Chorus (Pop/Rock)',
  genMode: 'Generate New',
  perspective: 'Same POV',
  language: 'English',
  gender: 'Neutral',
  bars: 32,
  numVariants: 3,
  temperature: 0.85,
  styleStrength: 0.7,
  enableVoice: true,
  enableMusic: true,
}

const STUDIO_RESULT_KEY = 'sonicflow_last_result'
const STUDIO_HISTORY_KEY = 'sonicflow_history'

// ── Utility: build pipeline steps array ──────────────────────────────────
function buildSteps(activeStep: string, completedSteps: Set<string>, failedSteps: Set<string>): PipelineStep[] {
  const steps = [
    { id: 'lyrics',   label: 'Synthesizing Lyrical Theme' },
    { id: 'voice',    label: 'Vocal Output (ElevenLabs)' },
    { id: 'music',    label: 'Full Song (Suno AI)' },
    { id: 'analysis', label: 'AI Lyrical Analysis' },
  ]
  return steps.map(s => ({
    ...s,
    status: failedSteps.has(s.id) ? 'failed'
      : completedSteps.has(s.id) ? 'done'
      : s.id === activeStep ? 'active'
      : 'pending',
  }))
}

export default function StudioPage() {
  const router = useRouter()
  const [authChecked, setAuthChecked] = useState(false)
  const [token, setToken] = useState('')

  const [state, setState] = useState<StudioState>(DEFAULT_STATE)
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [history, setHistory] = useState<GenerateResult[]>([])
  const [running, setRunning] = useState(false)
  const [activeTab, setActiveTab] = useState<'lyrics'|'insights'|'variants'|'stats'>('lyrics')
  const [activeVariant, setActiveVariant] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [creativeOpen, setCreativeOpen] = useState(true)
  const [multimodalOpen, setMultimodalOpen] = useState(true)

  // Pipeline status
  const [pipelineStatus, setPipelineStatus] = useState<'idle'|'running'|'complete'|'error'>('idle')
  const [activeStep, setActiveStep] = useState('')
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [failedSteps, setFailedSteps] = useState<Set<string>>(new Set())

  // Artist autocomplete
  const [artistQuery, setArtistQuery] = useState('')
  const [artistSuggestions, setArtistSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const artistDebounce = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [uploadedInst, setUploadedInst] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const set = <K extends keyof StudioState>(key: K) => (val: StudioState[K]) =>
    setState(s => ({ ...s, [key]: val }))

  // ── Auth guard + restore session ─────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem(SESSION_TOKEN_KEY)
    if (!stored) {
      router.replace('/login')
      return
    }
    setToken(stored)

    // Restore last result and history from localStorage
    try {
      const savedResult = localStorage.getItem(STUDIO_RESULT_KEY)
      if (savedResult) setResult(JSON.parse(savedResult))
      const savedHistory = localStorage.getItem(STUDIO_HISTORY_KEY)
      if (savedHistory) setHistory(JSON.parse(savedHistory))
    } catch { /* ignore parse errors */ }

    // Check if navigated here from Library (open project)
    try {
      const openProject = localStorage.getItem('sonicflow_open_project')
      if (openProject) {
        const proj = JSON.parse(openProject)
        localStorage.removeItem('sonicflow_open_project')
        setArtistQuery(proj.artist || '')
        setState(s => ({
          ...s,
          artist: proj.artist || '',
          theme: proj.theme || '',
          refLyrics: proj.lyrics || '',
        }))
        toast(`Opened: ${proj.title || proj.theme || 'Project'}`, { icon: '📂' })
      }
    } catch { /* ignore */ }

    setAuthChecked(true)
  }, [router])

  // ── Artist autocomplete ──────────────────────────────────────────────
  useEffect(() => {
    if (artistQuery.length < 3) { setArtistSuggestions([]); return }
    if (artistDebounce.current) clearTimeout(artistDebounce.current)
    artistDebounce.current = setTimeout(async () => {
      try {
        const results = await searchArtists(artistQuery)
        setArtistSuggestions(results)
        setShowSuggestions(results.length > 0)
      } catch { /* ignore */ }
    }, 250)
  }, [artistQuery])

  const selectArtist = (name: string) => {
    setArtistQuery(name)
    set('artist')(name)
    setShowSuggestions(false)
  }

  // ── Main generation handler ──────────────────────────────────────────
  const generate = useCallback(async () => {
    if (!state.artist && !state.theme) {
      toast.error('Please define Artist or Theme.')
      return
    }

    // Cancel any previous in-flight request
    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setRunning(true)
    setPipelineStatus('running')
    setCompletedSteps(new Set())
    setFailedSteps(new Set())
    setActiveStep('lyrics')
    setResult(null)

    const modeMap: Record<GenMode, 'generate'|'continue'|'remix'> = {
      'Generate New': 'generate',
      'Continue Story': 'continue',
      'Remix Style': 'remix',
    }
    const perspMap: Record<PerspectiveMode, 'same'|'opposite'|'response'> = {
      'Same POV': 'same',
      'Opposite Empathy': 'opposite',
      'Response Verse': 'response',
    }

    // Declare timers outside try so catch can clear them
    const markDone = (step: string) =>
      setCompletedSteps(prev => new Set([...prev, step]))
    const nextStep = (step: string) => setActiveStep(step)

    let stepTimer: ReturnType<typeof setTimeout>
    let voiceTimer: ReturnType<typeof setTimeout>
    let musicTimer: ReturnType<typeof setTimeout>

    const clearAllTimers = () => {
      clearTimeout(stepTimer); clearTimeout(voiceTimer)
      clearTimeout(musicTimer)
    }

    try {
      const params = {
        artists: [state.artist || 'Drake'],
        theme: state.theme,
        structure: STRUCTURES[state.structure],
        language: state.language,
        gender: state.gender,
        bars: state.bars,
        reference_lyrics: state.refLyrics,
        num_variants: state.numVariants,
        temperature: state.temperature,
        style_strength: state.styleStrength,
        gen_mode: modeMap[state.genMode],
        perspective_mode: perspMap[state.perspective],
        enable_voice: state.enableVoice,
        enable_music: state.enableMusic,
      }

      // Simulate step progression while waiting for API
      stepTimer  = setTimeout(() => { markDone('lyrics'); nextStep('voice') }, 3000)
      voiceTimer = setTimeout(() => { markDone('voice'); nextStep('music') }, 8000)
      musicTimer = setTimeout(() => { markDone('music'); nextStep('analysis') }, 15000)

      const res = await generateSong(params, token, abortRef.current?.signal)

      clearAllTimers()

      // Mark failures
      const failed = new Set<string>()
      if (!res.voice_audio_b64) failed.add('voice')
      if (!res.music_audio_b64) failed.add('music')
      if (!res.analysis) failed.add('analysis')
      setFailedSteps(failed)
      setCompletedSteps(new Set(['lyrics','voice','music','analysis'].filter(s => !failed.has(s))))
      setActiveStep('')

      setResult(res)
      const newHistory = [res, ...history]
      setHistory(newHistory)
      setPipelineStatus('complete')
      setActiveTab('lyrics')
      setActiveVariant(0)
      toast.success('Production complete!')

      // Persist to localStorage so result survives navigation
      try {
        localStorage.setItem(STUDIO_RESULT_KEY, JSON.stringify(res))
        // Store history without audio blobs (too large) — just metadata
        const historyMeta = newHistory.slice(0, 20).map(h => ({
          ...h,
          voice_audio_b64: null,
          music_audio_b64: null,
          mixed_audio_b64: null,
        }))
        localStorage.setItem(STUDIO_HISTORY_KEY, JSON.stringify(historyMeta))
      } catch { /* storage full — skip */ }

      // Save to server library (metadata only, no audio)
      try {
        await saveProject(token, {
          title: res.theme || state.theme || 'Untitled',
          theme: res.theme || state.theme,
          artist: state.artist || 'Unknown',
          lyrics: res.lyrics,
          has_voice: !!res.voice_audio_b64,
          has_music: !!res.music_audio_b64,
          duration_s: 0,
        })
      } catch { /* non-critical — library sync failed silently */ }
    } catch (err: unknown) {
      clearAllTimers()
      // Distinguish user-cancelled from real errors
      const isAbort =
        (err instanceof Error && err.name === 'CanceledError') ||
        (err instanceof Error && err.name === 'AbortError') ||
        (err as { code?: string })?.code === 'ERR_CANCELED'
      if (isAbort) {
        setPipelineStatus('idle')
        setActiveStep('')
        setCompletedSteps(new Set())
        toast('Generation stopped.', { icon: '⏹' })
      } else {
        const message = err instanceof Error ? err.message : 'Generation failed'
        setPipelineStatus('error')
        toast.error(`Generation failed: ${message}`)
      }
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }, [state, token, history])

  // ── Format lyrics with section headers highlighted ────────────────────
  const formatLyrics = (text: string) => {
    return text.split('\n').map((line, i) => {
      const isSectionHeader = /^\[.+\]$/.test(line.trim())
      return (
        <span key={i}>
          {isSectionHeader
            ? <span className="lyrics-section">{line}</span>
            : <span className="text-text-primary" style={{ lineHeight: '1.9' }}>{line}</span>
          }
          {'\n'}
        </span>
      )
    })
  }

  const pipelineSteps = buildSteps(activeStep, completedSteps, failedSteps)

  const stopGeneration = () => {
    abortRef.current?.abort()
  }

  const handleLogout = () => {
    localStorage.removeItem(SESSION_TOKEN_KEY)
    router.replace('/login')
  }

  // Show nothing while auth check is in progress (avoids flash of studio)
  if (!authChecked) return null

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── SIDEBAR ─────────────────────────────────────────────────── */}
      <aside className={`
        flex-shrink-0 transition-all duration-300 overflow-y-auto
        ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}
      `}
        style={{ background: '#111111', borderRight: '1px solid rgba(255,255,255,0.04)' }}
      >
        <div className="p-5 space-y-5 min-w-72">
          {/* Logo */}
          <div className="flex items-center gap-3 pb-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #8ff5ff, #d277ff)' }}>
              <Music2 size={16} color="#0e0e0e" />
            </div>
            <div>
              <div className="font-display font-bold text-sm text-text-primary">SonicFlow</div>
              <div className="text-xs text-text-muted">Studio v3</div>
            </div>
          </div>

          {/* Nav */}
          <nav className="space-y-1">
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium"
              style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff' }}>
              <Radio size={15} /> Studio
            </div>
            <Link href="/library"
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-text-muted hover:text-text-primary hover:bg-glass transition-all">
              <Library size={15} /> Library
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-text-muted hover:text-text-primary hover:bg-glass transition-all w-full text-left">
              <Settings size={15} /> Sign Out
            </button>
          </nav>

          <div style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />

          {/* Artist Search */}
          <div>
            <label className="label">Artist</label>
            <div className="relative">
              <input
                className="input-field"
                placeholder="Type artist name..."
                value={artistQuery}
                onChange={e => { setArtistQuery(e.target.value); set('artist')(e.target.value) }}
                onFocus={() => setShowSuggestions(artistSuggestions.length > 0)}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              />
              {showSuggestions && (
                <div className="absolute z-50 w-full mt-1 rounded-xl overflow-hidden shadow-glass-lg"
                  style={{ background: '#1e1e1e', border: '1px solid rgba(255,255,255,0.08)' }}>
                  {artistSuggestions.map(s => (
                    <button
                      key={s}
                      className="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-glass hover:text-text-primary transition-colors"
                      onMouseDown={() => selectArtist(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Creative Controls */}
          <div>
            <button
              className="flex items-center justify-between w-full text-left mb-3"
              onClick={() => setCreativeOpen(o => !o)}
            >
              <span className="section-title flex items-center gap-2">
                <Sliders size={13} /> Creative Controls
              </span>
              {creativeOpen ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            </button>

            {creativeOpen && (
              <div className="space-y-4">
                <div>
                  <label className="label flex justify-between">
                    Creativity <span style={{ color: '#8ff5ff' }}>{state.temperature}</span>
                  </label>
                  <input type="range" className="w-full" min={0.5} max={1.2} step={0.05}
                    value={state.temperature}
                    onChange={e => set('temperature')(+e.target.value)} />
                </div>
                <div>
                  <label className="label flex justify-between">
                    Style Strength <span style={{ color: '#8ff5ff' }}>{state.styleStrength}</span>
                  </label>
                  <input type="range" className="w-full" min={0} max={1} step={0.05}
                    value={state.styleStrength}
                    onChange={e => set('styleStrength')(+e.target.value)} />
                </div>
                <div>
                  <label className="label">Language</label>
                  <select className="select-field" value={state.language}
                    onChange={e => set('language')(e.target.value as Language)}>
                    {LANGUAGES.map(l => <option key={l}>{l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Vocal Perspective</label>
                  <select className="select-field" value={state.gender}
                    onChange={e => set('gender')(e.target.value as StudioState['gender'])}>
                    {['Neutral','Male','Female'].map(g => <option key={g}>{g}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Song Length (Bars)</label>
                  <div className="grid grid-cols-4 gap-1.5">
                    {([4,8,16,32] as const).map(b => (
                      <button key={b}
                        onClick={() => set('bars')(b)}
                        className={`py-2 rounded-lg text-xs font-display font-semibold transition-all ${
                          state.bars === b
                            ? 'text-background'
                            : 'text-text-muted hover:text-text-primary'
                        }`}
                        style={state.bars === b ? { background: '#8ff5ff' } : { background: 'rgba(255,255,255,0.05)' }}
                      >
                        {b}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="label">Creative Variants</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {([1,3,5] as const).map(v => (
                      <button key={v}
                        onClick={() => set('numVariants')(v)}
                        className={`py-2 rounded-lg text-xs font-display font-semibold transition-all ${
                          state.numVariants === v ? 'text-background' : 'text-text-muted hover:text-text-primary'
                        }`}
                        style={state.numVariants === v ? { background: '#c3f400', color: '#0e0e0e' } : { background: 'rgba(255,255,255,0.05)' }}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Multimodal Engines */}
          <div>
            <button
              className="flex items-center justify-between w-full text-left mb-3"
              onClick={() => setMultimodalOpen(o => !o)}
            >
              <span className="section-title flex items-center gap-2">
                <Mic2 size={13} /> Multimodal Engines
              </span>
              {multimodalOpen ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            </button>

            {multimodalOpen && (
              <div className="space-y-3">
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-sm text-text-secondary">Voice Synthesis</span>
                  <div className={`relative w-10 h-5 rounded-full transition-colors ${state.enableVoice ? 'bg-primary' : 'bg-surface-3'}`}
                    onClick={() => set('enableVoice')(!state.enableVoice)}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.enableVoice ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-sm text-text-secondary">Music Production</span>
                  <div className={`relative w-10 h-5 rounded-full transition-colors ${state.enableMusic ? 'bg-primary' : 'bg-surface-3'}`}
                    onClick={() => set('enableMusic')(!state.enableMusic)}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.enableMusic ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>
                <div>
                  <label className="label">Upload Instrumental</label>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full py-2.5 rounded-xl text-xs text-text-muted border border-dashed transition-colors hover:border-primary hover:text-primary"
                    style={{ borderColor: 'rgba(255,255,255,0.12)' }}
                  >
                    <Upload size={13} className="inline mr-1.5" />
                    {uploadedInst ? uploadedInst.name : 'MP3 / WAV'}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".mp3,.wav"
                    className="hidden"
                    onChange={e => setUploadedInst(e.target.files?.[0] ?? null)}
                  />
                </div>
              </div>
            )}
          </div>

          <div style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />

          {/* Clear */}
          <button
            onClick={() => {
              setHistory([]); setResult(null); setState(DEFAULT_STATE)
              setArtistQuery(''); setPipelineStatus('idle')
              localStorage.removeItem(STUDIO_RESULT_KEY)
              localStorage.removeItem(STUDIO_HISTORY_KEY)
            }}
            className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl text-sm text-text-muted hover:text-error hover:bg-glass transition-all"
          >
            <Trash2 size={14} /> Clear Project
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ─────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center justify-between px-6 py-4"
          style={{ background: 'rgba(14,14,14,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(o => !o)}
              className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all"
            >
              <Sliders size={16} />
            </button>
            <div>
              <h1 className="font-display font-bold text-lg text-text-primary leading-none">
                Global AI Music Studio
              </h1>
              <p className="text-xs text-text-muted mt-0.5">AI Songwriting • Voice Synthesis • Music Generation</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#2ed573' }} />
            <span className="text-xs text-text-muted">System Online</span>
          </div>
        </header>

        <div className="flex gap-6 p-6">
          {/* ── LEFT: Input Panel ────────────────────────────────────── */}
          <div className="flex-1 max-w-xl space-y-5">

            {/* Theme */}
            <div className="glass-panel p-5 space-y-4">
              <h2 className="font-display font-semibold text-sm text-text-secondary uppercase tracking-widest">
                1. Theme & Creative Mode
              </h2>
              <div>
                <label className="label">Project Theme / Emotional Blueprint</label>
                <input
                  className="input-field"
                  placeholder="nostalgic late night drive in Seoul"
                  value={state.theme}
                  onChange={e => set('theme')(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Creative Process</label>
                  <select className="select-field" value={state.genMode}
                    onChange={e => set('genMode')(e.target.value as GenMode)}>
                    {GEN_MODES.map(m => <option key={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Writing Perspective</label>
                  <select className="select-field" value={state.perspective}
                    onChange={e => set('perspective')(e.target.value as PerspectiveMode)}>
                    {PERSPECTIVES.map(p => <option key={p}>{p}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* Reference Lyrics */}
            <div className="glass-panel p-5 space-y-3">
              <h2 className="font-display font-semibold text-sm text-text-secondary uppercase tracking-widest">
                2. Reference Lyrics (Context)
              </h2>
              <textarea
                className="input-field resize-none"
                rows={5}
                placeholder="Paste existing lyrics here (optional — used for Continue / Remix)..."
                value={state.refLyrics}
                onChange={e => set('refLyrics')(e.target.value)}
              />
            </div>

            {/* Structure */}
            <div className="glass-panel p-5 space-y-3">
              <h2 className="font-display font-semibold text-sm text-text-secondary uppercase tracking-widest">
                3. Structure & Preset
              </h2>
              <select className="select-field" value={state.structure}
                onChange={e => set('structure')(e.target.value)}>
                {Object.keys(STRUCTURES).map(k => <option key={k}>{k}</option>)}
              </select>
              <div className="flex flex-wrap gap-1.5">
                {STRUCTURES[state.structure].map((s, i) => (
                  <span key={i} className="px-2 py-0.5 rounded-md text-xs"
                    style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff' }}>
                    {s}
                  </span>
                ))}
              </div>
            </div>

            {/* Generate Button */}
            <div className="flex gap-3">
            <button
              onClick={generate}
              disabled={running}
              className="btn-primary flex-1 py-4 text-base flex items-center justify-center gap-2"
            >
              {running
                ? <><RotateCcw size={18} className="animate-spin" /> Producing...</>
                : <><Zap size={18} /> IGNITE PRODUCTION</>
              }
            </button>
            {running && (
              <button
                onClick={stopGeneration}
                title="Stop generation"
                className="flex-shrink-0 flex items-center justify-center gap-2 px-5 py-4 rounded-xl font-display font-semibold text-sm transition-all duration-200 hover:scale-105 active:scale-95"
                style={{
                  background: 'rgba(255,71,87,0.12)',
                  border: '1px solid rgba(255,71,87,0.3)',
                  color: '#ff4757',
                }}
              >
                <Square size={16} fill="#ff4757" />
                Stop
              </button>
            )}
            </div>

            {/* Pipeline Status */}
            <GenerationStatus
              steps={pipelineSteps}
              overallStatus={pipelineStatus}
            />
          </div>

          {/* ── RIGHT: Output Panel ───────────────────────────────────── */}
          <div className="flex-1 space-y-5">
            {!result ? (
              <div className="glass-panel p-10 text-center space-y-4">
                <div className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
                  style={{ background: 'rgba(143,245,255,0.06)' }}>
                  <Music2 size={32} style={{ color: '#8ff5ff', opacity: 0.4 }} />
                </div>
                <p className="text-text-muted text-sm">
                  Studio is ready. Define your theme on the left to begin.
                </p>
              </div>
            ) : (
              <div className="animate-slide-up space-y-5">
                <div className="flex items-center justify-between gap-3 overflow-hidden">
                  <div className="min-w-0 overflow-hidden">
                    <h2 className="font-display font-bold text-xl text-text-primary truncate">
                      {result.theme || 'Latest Project'}
                    </h2>
                    <p className="text-xs text-text-muted">{result.timestamp}</p>
                  </div>
                </div>

                {/* ── Audio Players ── */}
                <div className="glass-panel p-5 space-y-4">
                  <h3 className="section-title">Production Playback</h3>

                  {/* Debug sizes */}
                  <div className="text-xs text-text-muted font-mono">
                    VOICE: {result.voice_audio_b64 ? `${Math.round(result.voice_audio_b64.length * 0.75 / 1024)} KB` : '0'}
                    {' · '}
                    MUSIC: {result.music_audio_b64 ? `${Math.round(result.music_audio_b64.length * 0.75 / 1024)} KB` : '0'}
                  </div>

                  {/* Vocal Output — ElevenLabs TTS */}
                  {result.voice_audio_b64 ? (
                    <AudioPlayer
                      b64={result.voice_audio_b64}
                      label="Vocal Output (ElevenLabs)"
                      filename={`voice_${result.timestamp}.mp3`}
                      accentColor="#d277ff"
                    />
                  ) : (
                    <div className="flex items-center gap-2 text-error text-xs p-3 rounded-xl"
                      style={{ background: 'rgba(255,71,87,0.08)' }}>
                      <AlertCircle size={14} />
                      Vocal generation failed — check ElevenLabs API key.
                    </div>
                  )}

                  {/* Full Song Output — Suno AI (vocals + music) */}
                  {result.music_audio_b64 ? (
                    <AudioPlayer
                      b64={result.music_audio_b64}
                      label="Full Song Output (Suno AI)"
                      filename={`music_${result.timestamp}.mp3`}
                      accentColor="#c3f400"
                    />
                  ) : state.enableMusic && (
                    <div className="flex items-center gap-2 text-xs p-3 rounded-xl"
                      style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502' }}>
                      <Info size={14} />
                      Music generation failed — check Suno credits or API.
                    </div>
                  )}

                  {uploadedInst && (
                    <div className="space-y-2">
                      <span className="section-title">Uploaded Instrumental</span>
                      <audio src={URL.createObjectURL(uploadedInst)} controls className="w-full" />
                    </div>
                  )}
                </div>

                {/* ── Content Tabs ── */}
                <div className="glass-panel overflow-hidden">
                  <div className="flex border-b" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
                    {(['lyrics','insights','variants','stats'] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`flex-1 py-3 text-xs font-display font-semibold uppercase tracking-wider transition-all ${
                          activeTab === tab ? 'tab-active' : 'text-text-muted hover:text-text-secondary'
                        }`}
                      >
                        {tab === 'lyrics' ? '📝 Lyrics'
                          : tab === 'insights' ? '💡 Insights'
                          : tab === 'variants' ? '🌈 Variants'
                          : '📊 Stats'}
                      </button>
                    ))}
                  </div>

                  <div className="p-5">
                    {/* Lyrics Tab */}
                    {activeTab === 'lyrics' && (
                      <div className="whitespace-pre-wrap text-sm leading-loose font-body">
                        {formatLyrics(result.lyrics)}
                      </div>
                    )}

                    {/* Insights Tab */}
                    {activeTab === 'insights' && (
                      <div className="space-y-3">
                        <h3 className="section-title">AI Lyrical Analysis</h3>
                        {result.analysis ? (
                          <pre className="text-xs text-text-secondary overflow-auto rounded-xl p-4"
                            style={{ background: 'rgba(255,255,255,0.02)', maxHeight: '400px' }}>
                            {JSON.stringify(result.analysis, null, 2)}
                          </pre>
                        ) : (
                          <p className="text-text-muted text-sm">Analysis not available.</p>
                        )}
                      </div>
                    )}

                    {/* Variants Tab */}
                    {activeTab === 'variants' && (
                      <div className="space-y-3">
                        <div className="flex gap-2">
                          {result.versions?.map((_, i) => (
                            <button key={i}
                              onClick={() => setActiveVariant(i)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-display font-semibold transition-all ${
                                activeVariant === i ? 'text-background' : 'text-text-muted hover:text-text-primary'
                              }`}
                              style={activeVariant === i ? { background: '#c3f400' } : { background: 'rgba(255,255,255,0.05)' }}
                            >
                              Variant {String.fromCharCode(65 + i)}
                            </button>
                          ))}
                        </div>
                        {result.versions?.[activeVariant] && (
                          <>
                            <p className="text-xs text-text-muted">
                              Style Fidelity: <span style={{ color: '#8ff5ff' }}>
                                {result.versions[activeVariant].style_fidelity.toFixed(3)}
                              </span>
                            </p>
                            <div className="whitespace-pre-wrap text-sm leading-loose text-text-secondary">
                              {result.versions[activeVariant].lyrics}
                            </div>
                          </>
                        )}
                      </div>
                    )}

                    {/* Stats Tab */}
                    {activeTab === 'stats' && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="glass-panel p-4 text-center">
                            <div className="text-2xl font-display font-bold"
                              style={{ color: '#8ff5ff' }}>
                              {result.retrieval_quality.toFixed(3)}
                            </div>
                            <div className="text-xs text-text-muted mt-1">Retrieval Quality</div>
                          </div>
                          <div className="glass-panel p-4 text-center">
                            <div className="text-2xl font-display font-bold"
                              style={{ color: '#c3f400' }}>
                              {(result.latency_ms / 1000).toFixed(1)}s
                            </div>
                            <div className="text-xs text-text-muted mt-1">Latency</div>
                          </div>
                        </div>
                        <pre className="text-xs text-text-secondary overflow-auto rounded-xl p-4"
                          style={{ background: 'rgba(255,255,255,0.02)', maxHeight: '300px' }}>
                          {JSON.stringify(result.retrieval_diagnostics, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* History */}
            {history.length > 1 && (
              <div className="glass-panel p-5 space-y-3 overflow-hidden">
                <h3 className="section-title">Session History ({history.length} tracks)</h3>
                {history.slice(1, 6).map((h, i) => (
                  <button
                    key={i}
                    onClick={() => { setResult(h); setActiveTab('lyrics') }}
                    className="w-full text-left px-4 py-3 rounded-xl text-sm text-text-secondary hover:bg-glass transition-all flex items-center gap-2 overflow-hidden"
                  >
                    <span className="text-text-muted text-xs flex-shrink-0">{h.timestamp}</span>
                    <span className="truncate">{h.theme || 'Untitled'}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <footer className="px-6 py-4 text-center text-xs text-text-muted"
          style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          AI Songwriting System V3 | Production Mode | Sync: Locally + EC2
        </footer>
      </main>
    </div>
  )
}
