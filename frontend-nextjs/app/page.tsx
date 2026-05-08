'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  Music2, Mic2, Sliders, ChevronDown, ChevronRight,
  Radio, Upload, Trash2, Library, Zap, Settings,
  AlertCircle, Info, RotateCcw, Square, Lock, Loader2,
  Scissors, Globe, Layers, Wand2, Download, Blend
} from 'lucide-react'
import toast from 'react-hot-toast'
import AudioPlayer from '@/components/AudioPlayer'
import GenerationStatus, { PipelineStep } from '@/components/GenerationStatus'
import StemPlayer from '@/components/StemPlayer'
import type {
  GenerateResult, StudioState, Language, GenMode, PerspectiveMode,
  SectionMode, GlobalArtists, OutputMode, ProducerVocalSource
} from '@/lib/types'
import {
  generateSong, searchArtists, b64ToDownloadUrl, saveProject,
  extractChorus, extractStems, getStemStatus, getGlobalArtists,
  analyzeTrack, generateRemixVariants, downloadDAWSession, logout
} from '@/lib/api'
import type { AudioAnalysisResult, RemixVariant } from '@/lib/types'

// ── Song structures ───────────────────────────────────────────────────────
const STRUCTURES: Record<string, string[]> = {
  'Verse-Chorus (Pop/Rock)':        ['[Verse 1]','[Pre-Chorus]','[Chorus]','[Verse 2]','[Pre-Chorus]','[Chorus]','[Bridge]','[Chorus]'],
  'Verse-Chorus-Bridge (Standard)': ['[Verse 1]','[Chorus]','[Verse 2]','[Chorus]','[Bridge]','[Chorus]'],
  'AABA (Jazz/Classic)':            ['[A Section]','[A Section]','[B Section (Bridge)]','[A Section]'],
  'Through-Composed (Narrative)':   ['[Intro]','[Section 1]','[Section 2]','[Section 3]','[Outro]'],
  'Hook-Verse (Hip-Hop)':           ['[Hook]','[Verse 1]','[Hook]','[Verse 2]','[Hook]','[Bridge]','[Hook]'],
  'Extended (Album Track)':         ['[Intro]','[Verse 1]','[Pre-Chorus]','[Chorus]','[Verse 2]','[Pre-Chorus]','[Chorus]','[Bridge]','[Verse 3]','[Outro Chorus]'],
  'Verse Only':                     ['[Verse 1]','[Verse 2]','[Verse 3]'],
}

const LANGUAGES: Language[] = [
  'English','Spanish','French','German','Hindi','Arabic','Portuguese','Japanese','Korean','Chinese'
]
const GEN_MODES:    GenMode[]         = ['Generate New','Continue Story','Remix Style']
const PERSPECTIVES: PerspectiveMode[] = ['Same POV','Opposite Empathy','Response Verse']
const SECTION_MODES: SectionMode[]    = ['Full Song','Verse Only']

const SESSION_TOKEN_KEY = 'sonicflow_token'
const STUDIO_RESULT_KEY = 'sonicflow_last_result'
const STUDIO_HISTORY_KEY = 'sonicflow_history'

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
  outputMode: 'draft',
  enableMix: false,
  producerVocalSource: 'suno_singing',
  sectionMode: 'Full Song',
  chorusStrict: false,
  producerMode: false,
  fastMode: false,
}

const OUTPUT_MODE_CONFIG = {
  draft: {
    label: 'Draft Mode',
    sub: 'Voice Demo (ElevenLabs)',
    color: '#d277ff',
    icon: <Mic2 size={12} />,
    desc: 'Quick vocal preview of your lyrics',
  },
  music_demo: {
    label: 'Music Demo Mode',
    sub: 'Full Song (Suno AI)',
    color: '#c3f400',
    icon: <Music2 size={12} />,
    desc: 'Complete song with vocals + instruments',
  },
  producer: {
    label: 'Producer Remix',
    sub: 'Stems + DAW Export',
    color: '#ffa502',
    icon: <Layers size={12} />,
    desc: 'No auto-mix — vocals + stems exported for your DAW session',
  },
} as const

function buildSteps(
  activeStep: string,
  completedSteps: Set<string>,
  failedSteps: Set<string>,
  outputMode: OutputMode,
  producerVocalSource: ProducerVocalSource,
): PipelineStep[] {
  const producerUsesSuno = outputMode === 'producer' && producerVocalSource === 'suno_singing'
  const allSteps = [
    { id: 'lyrics',   label: 'Synthesizing Lyrics',                  show: true },
    { id: 'voice',    label: 'Timing Guide Vocal (ElevenLabs)',       show: outputMode === 'draft' || (outputMode === 'producer' && !producerUsesSuno) },
    { id: 'music',    label: outputMode === 'producer' ? 'AI Song with Vocals (Suno)' : 'Full Song (Suno AI)', show: outputMode === 'music_demo' || producerUsesSuno },
    { id: 'mix',      label: 'Quick Demo Mix',                        show: outputMode === 'draft' },
    { id: 'analysis', label: 'AI Analysis',                           show: true },
  ]
  return allSteps
    .filter(s => s.show)
    .map(s => ({
      id: s.id,
      label: s.label,
      status: failedSteps.has(s.id) ? 'failed'
        : completedSteps.has(s.id) ? 'done'
        : s.id === activeStep ? 'active'
        : 'pending',
    }))
}

// ── Global Artist Picker component ────────────────────────────────────────
function GlobalArtistPicker({
  onSelect,
  currentLanguage,
}: {
  onSelect: (artist: string) => void
  currentLanguage: Language
}) {
  const [data, setData] = useState<GlobalArtists>({})
  const [open, setOpen] = useState(false)
  const [selectedLang, setSelectedLang] = useState<string>(currentLanguage)
  const [selectedGenre, setSelectedGenre] = useState<string>('')
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getGlobalArtists().then(setData).catch(() => {})
  }, [])

  // Sync language with parent selector
  useEffect(() => {
    setSelectedLang(currentLanguage)
    setSelectedGenre('')
  }, [currentLanguage])

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const langs = Object.keys(data)
  const genres = selectedLang && data[selectedLang] ? Object.keys(data[selectedLang]) : []
  const artists: string[] = selectedLang && selectedGenre && data[selectedLang]?.[selectedGenre]
    ? data[selectedLang][selectedGenre]
    : []

  // Flat search across all artists in current language
  const searchResults: { artist: string; genre: string }[] = search.length >= 2
    ? Object.entries(data[selectedLang] ?? {}).flatMap(([genre, list]) =>
        (list as string[])
          .filter(a => a.toLowerCase().includes(search.toLowerCase()))
          .map(a => ({ artist: a, genre }))
      ).slice(0, 8)
    : []

  if (langs.length === 0) return null

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all"
        style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff', border: '1px solid rgba(143,245,255,0.15)' }}
        title="Browse global artists"
      >
        <Globe size={11} /> Browse
      </button>

      {open && (
        <div className="absolute left-0 top-8 z-50 w-72 rounded-2xl shadow-glass-lg overflow-hidden"
          style={{ background: '#1a1a1a', border: '1px solid rgba(255,255,255,0.08)' }}>

          <div className="p-3 space-y-2">
            {/* Search */}
            <input
              className="input-field text-xs py-2"
              placeholder="Search artist..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />

            {search.length >= 2 ? (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {searchResults.length === 0
                  ? <p className="text-xs text-text-muted px-1">No results</p>
                  : searchResults.map(({ artist, genre }) => (
                    <button key={artist} onClick={() => { onSelect(artist); setOpen(false); setSearch('') }}
                      className="w-full text-left px-3 py-2 rounded-lg text-xs hover:bg-glass transition-all flex items-center justify-between">
                      <span className="text-text-primary">{artist}</span>
                      <span className="text-text-muted">{genre}</span>
                    </button>
                  ))
                }
              </div>
            ) : (
              <>
                {/* Language tabs */}
                <div className="flex flex-wrap gap-1">
                  {langs.map(l => (
                    <button key={l}
                      onClick={() => { setSelectedLang(l); setSelectedGenre('') }}
                      className={`px-2 py-0.5 rounded-md text-xs transition-all ${selectedLang === l ? 'text-background font-semibold' : 'text-text-muted'}`}
                      style={selectedLang === l ? { background: '#8ff5ff' } : { background: 'rgba(255,255,255,0.05)' }}
                    >{l}</button>
                  ))}
                </div>

                {/* Genre list */}
                {genres.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {genres.map(g => (
                      <button key={g}
                        onClick={() => setSelectedGenre(g === selectedGenre ? '' : g)}
                        className={`px-2 py-0.5 rounded-md text-xs transition-all ${selectedGenre === g ? 'text-background font-semibold' : 'text-text-muted'}`}
                        style={selectedGenre === g ? { background: '#c3f400', color: '#0e0e0e' } : { background: 'rgba(255,255,255,0.05)' }}
                      >{g}</button>
                    ))}
                  </div>
                )}

                {/* Artist list */}
                {artists.length > 0 && (
                  <div className="max-h-40 overflow-y-auto space-y-0.5">
                    {artists.map(a => (
                      <button key={a} onClick={() => { onSelect(a); setOpen(false) }}
                        className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-text-secondary hover:text-text-primary hover:bg-glass transition-all">
                        {a}
                      </button>
                    ))}
                  </div>
                )}

                {genres.length > 0 && artists.length === 0 && (
                  <p className="text-xs text-text-muted px-1">Select a genre above</p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Stem Status Panel — always visible independent of result ──────────────
function StemStatusPanel({
  stemFile,
  stemStatus,
  stemUrls,
  stemJobId,
  onTabSwitch,
}: {
  stemFile: File | null
  stemStatus: string
  stemUrls: Record<string, string>
  stemJobId: string
  onTabSwitch: () => void
}) {
  if (!stemFile && Object.keys(stemUrls).length === 0) return null

  const statusColor =
    stemStatus === 'done'     ? '#c3f400' :
    stemStatus === 'failed'   ? '#ff4757' :
    '#ffa502'

  return (
    <div className="glass-panel p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="section-title flex items-center gap-1.5">
          <Scissors size={12} /> Stem Extraction
        </h3>
        {stemStatus === 'done' && (
          <button
            onClick={onTabSwitch}
            className="text-xs px-2 py-1 rounded-lg font-semibold"
            style={{ background: 'rgba(195,244,0,0.1)', color: '#c3f400' }}
          >
            View Stems →
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs" style={{ color: statusColor }}>
        {(stemStatus === 'uploading' || stemStatus === 'processing') && (
          <Loader2 size={11} className="animate-spin flex-shrink-0" />
        )}
        <span>
          {stemStatus === 'uploading'   && `Uploading ${stemFile?.name}…`}
          {stemStatus === 'processing'  && 'Extracting stems via Demucs (2–8 min)…'}
          {stemStatus === 'done'        && `✓ ${Object.keys(stemUrls).length} stems ready`}
          {stemStatus === 'failed'      && 'Extraction failed'}
        </span>
      </div>

      {stemStatus === 'done' && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {Object.keys(stemUrls).map(name => (
            <span key={name} className="px-2 py-0.5 rounded-md text-xs capitalize"
              style={{ background: 'rgba(195,244,0,0.08)', color: '#c3f400' }}>
              {name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}


export default function StudioPage() {
  const router = useRouter()
  const [authChecked, setAuthChecked] = useState(false)
  const [token, setToken] = useState('')

  const [state, setState] = useState<StudioState>(DEFAULT_STATE)
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [history, setHistory] = useState<GenerateResult[]>([])
  const [running, setRunning] = useState(false)
  const [activeVariant, setActiveVariant] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [creativeOpen, setCreativeOpen] = useState(true)
  const [multimodalOpen, setMultimodalOpen] = useState(true)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [pipelineStatus, setPipelineStatus] = useState<'idle'|'running'|'complete'|'error'>('idle')
  const [activeStep, setActiveStep] = useState('')
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set())
  const [failedSteps, setFailedSteps] = useState<Set<string>>(new Set())

  const [artistQuery, setArtistQuery] = useState('')
  const [artistSuggestions, setArtistSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const artistDebounce = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [uploadedInst, setUploadedInst] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Remix mode
  const [detectedChorus, setDetectedChorus] = useState('')
  const [detectingChorus, setDetectingChorus] = useState(false)
  const [lockedChorus, setLockedChorus] = useState('')

  // Stem extraction
  const [stemFile, setStemFile] = useState<File | null>(null)
  const stemFileRef = useRef<HTMLInputElement>(null)
  const [stemJobId, setStemJobId] = useState('')
  const [stemStatus, setStemStatus] = useState<'idle'|'uploading'|'processing'|'done'|'failed'>('idle')
  const [stemUrls, setStemUrls] = useState<Record<string, string>>({})

  const [activeTab, setActiveTab] = useState<'lyrics'|'insights'|'variants'|'stats'|'stems'>('lyrics')

  // Intelligence Layer state
  const [instrumentalAnalysis, setInstrumentalAnalysis] = useState<AudioAnalysisResult | null>(null)
  const [analyzingTrack, setAnalyzingTrack] = useState(false)
  const [genreRemixVariants, setGenreRemixVariants] = useState<RemixVariant[]>([])
  const [selectedRemixGenres, setSelectedRemixGenres] = useState<string[]>([])
  const [generatingVariants, setGeneratingVariants] = useState(false)
  const [dawExporting, setDawExporting] = useState(false)
  const [expandedVariant, setExpandedVariant] = useState<string | null>(null)

  // Sound Design state
  const [targetGenre, setTargetGenre] = useState('')
  const [genreBlendEnabled, setGenreBlendEnabled] = useState(false)
  const [genreBlendPrimary, setGenreBlendPrimary] = useState('trap')
  const [genreBlendSecondary, setGenreBlendSecondary] = useState('acoustic')
  const [genreBlendWeight, setGenreBlendWeight] = useState(0.5)
  const [producerControlsEnabled, setProducerControlsEnabled] = useState(false)
  const [producerDarkness, setProducerDarkness] = useState(0.5)
  const [producerMelodicness, setProducerMelodicness] = useState(0.5)
  const [producerAggression, setProducerAggression] = useState(0.5)
  const [producerAtmosphere, setProducerAtmosphere] = useState(0.5)
  const [producerGrooveDensity, setProducerGrooveDensity] = useState(0.5)

  const REMIX_GENRE_OPTIONS = ['Drill', 'EDM', 'Afrobeat', 'Synthwave', 'Acoustic', 'Trap']
  const GENRE_OPTIONS = ['acoustic', 'afrobeat', 'cinematic', 'drill', 'edm', 'house', 'jersey_club', 'kpop', 'punjabi', 'reggaeton', 'synthwave', 'trap']

  const set = <K extends keyof StudioState>(key: K) => (val: StudioState[K]) =>
    setState(s => ({ ...s, [key]: val }))

  // ── Auth guard ────────────────────────────────────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem(SESSION_TOKEN_KEY)
    if (!stored) { router.replace('/login'); return }
    setToken(stored)
    try {
      const savedResult = localStorage.getItem(STUDIO_RESULT_KEY)
      if (savedResult) setResult(JSON.parse(savedResult))
      const savedHistory = localStorage.getItem(STUDIO_HISTORY_KEY)
      if (savedHistory) setHistory(JSON.parse(savedHistory))
    } catch { /* ignore */ }
    try {
      const openProject = localStorage.getItem('sonicflow_open_project')
      if (openProject) {
        const proj = JSON.parse(openProject)
        localStorage.removeItem('sonicflow_open_project')
        setArtistQuery(proj.artist || '')
        const genModeMap: Record<string, GenMode> = {
          generate: 'Generate New', continue: 'Continue Story', remix: 'Remix Style',
        }
        const perspMap2: Record<string, PerspectiveMode> = {
          same: 'Same POV', opposite: 'Opposite Empathy', response: 'Response Verse',
        }
        setState(s => ({
          ...s,
          artist:        proj.artist        || s.artist,
          theme:         proj.theme         || s.theme,
          refLyrics:     proj.ref_lyrics    || proj.lyrics || '',
          language:      (proj.language     || s.language) as Language,
          bars:          (proj.bars         || s.bars) as 4|8|16|32,
          structure:     proj.structure     || s.structure,
          outputMode:    (proj.output_mode  || s.outputMode) as OutputMode,
          genMode:       genModeMap[proj.gen_mode]            || s.genMode,
          perspective:   perspMap2[proj.perspective_mode]     || s.perspective,
          gender:        (proj.gender       || s.gender) as 'Neutral'|'Male'|'Female',
          styleStrength: proj.style_strength ?? s.styleStrength,
          temperature:   proj.temperature   ?? s.temperature,
          chorusStrict:  proj.chorus_strict ?? s.chorusStrict,
          producerMode:  proj.producer_mode ?? s.producerMode,
          sectionMode:   (proj.section_mode || s.sectionMode) as SectionMode,
        }))
        toast(`Opened: ${proj.title || proj.theme || 'Project'}`, { icon: '📂' })
      }
    } catch { /* ignore */ }
    setAuthChecked(true)
  }, [router])

  // ── Artist autocomplete (Genius search) ──────────────────────────────
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

  // ── Auto-analyze uploaded instrumental ───────────────────────────────
  useEffect(() => {
    if (!uploadedInst || !token) { setInstrumentalAnalysis(null); return }
    let cancelled = false
    setAnalyzingTrack(true)
    setInstrumentalAnalysis(null)
    analyzeTrack(token, uploadedInst)
      .then(result => { if (!cancelled) setInstrumentalAnalysis(result) })
      .catch(() => { /* non-critical — analysis is optional */ })
      .finally(() => { if (!cancelled) setAnalyzingTrack(false) })
    return () => { cancelled = true }
  }, [uploadedInst, token])

  // ── Generate genre remix variants ─────────────────────────────────────
  const generateVariants = useCallback(async () => {
    if (!result || !lockedChorus || selectedRemixGenres.length === 0) return
    setGeneratingVariants(true)
    setGenreRemixVariants([])
    try {
      const { variants } = await generateRemixVariants(token, {
        locked_chorus: lockedChorus,
        original_lyrics: result.lyrics,
        theme: state.theme,
        artists: [state.artist || 'Drake'],
        target_genres: selectedRemixGenres.map(g => g.toLowerCase()),
        bars: state.bars,
        language: state.language,
      })
      setGenreRemixVariants(variants)
      if (variants.length > 0) toast.success(`${variants.length} genre remix${variants.length > 1 ? 's' : ''} generated!`)
      else toast.error('No variants returned — check genre availability.')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed'
      toast.error(`Remix variants failed: ${msg}`)
    } finally {
      setGeneratingVariants(false)
    }
  }, [result, lockedChorus, selectedRemixGenres, token, state.theme, state.artist, state.bars, state.language])

  // ── DAW Export ────────────────────────────────────────────────────────
  const exportDAWSession = useCallback(async () => {
    if (!result) return
    setDawExporting(true)
    try {
      const blob = await downloadDAWSession(token, {
        title: result.theme || state.theme || 'SonicFlow Session',
        artist: state.artist || 'Unknown',
        theme: result.theme || state.theme,
        lyrics: result.lyrics,
        language: state.language,
        bpm: instrumentalAnalysis?.bpm ?? 120,
        key: instrumentalAnalysis?.key ?? 'C major',
        bars: state.bars,
        darkness: 0.5,
        chords: (instrumentalAnalysis?.chords ?? []).slice(0, 8),
        voice_audio_b64: result.voice_audio_b64,
        music_audio_b64: result.music_audio_b64,
        mix_audio_b64: result.mixed_audio_b64,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(result.theme || 'session').replace(/\s+/g, '_')}_daw_session.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('DAW session downloaded!')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Export failed'
      toast.error(`DAW export failed: ${msg}`)
    } finally {
      setDawExporting(false)
    }
  }, [result, token, state.theme, state.artist, state.language, state.bars, instrumentalAnalysis])

  // ── Main generation ───────────────────────────────────────────────────
  const generate = useCallback(async () => {
    if (!state.artist && !state.theme) {
      toast.error('Please define Artist or Theme.')
      return
    }

    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setRunning(true)
    setPipelineStatus('running')
    setCompletedSteps(new Set())
    setFailedSteps(new Set())
    setActiveStep('lyrics')
    setResult(null)

    const modeMap: Record<GenMode, 'generate'|'continue'|'remix'> = {
      'Generate New': 'generate', 'Continue Story': 'continue', 'Remix Style': 'remix',
    }
    const perspMap: Record<PerspectiveMode, 'same'|'opposite'|'response'> = {
      'Same POV': 'same', 'Opposite Empathy': 'opposite', 'Response Verse': 'response',
    }

    const markDone = (step: string) => setCompletedSteps(prev => new Set([...prev, step]))
    const nextStep = (step: string) => setActiveStep(step)

    let t1: ReturnType<typeof setTimeout>
    let t2: ReturnType<typeof setTimeout>
    let t3: ReturnType<typeof setTimeout>
    let t4: ReturnType<typeof setTimeout>
    const clearTimers = () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); clearTimeout(t4) }

    try {
      const isRemix = state.genMode === 'Remix Style'
      const effectiveBars = state.fastMode ? 8 : state.bars
      const effectiveVariants = state.fastMode ? 1 : state.numVariants
      const params = {
        artists: [state.artist || 'Drake'],
        theme: state.theme,
        structure: STRUCTURES[state.structure] ?? STRUCTURES['Verse-Chorus (Pop/Rock)'],
        language: state.language,
        gender: state.gender,
        bars: effectiveBars,
        reference_lyrics: state.refLyrics,
        num_variants: effectiveVariants,
        temperature: state.temperature,
        style_strength: state.styleStrength,
        output_mode: state.outputMode,
        enable_mix: state.outputMode === 'draft' && state.enableMix,
        vocal_source: state.outputMode === 'producer' ? state.producerVocalSource : undefined,
        gen_mode: modeMap[state.genMode],
        perspective_mode: perspMap[state.perspective],
        remix_mode: isRemix,
        locked_chorus: isRemix ? lockedChorus : '',
        section_mode: state.sectionMode === 'Verse Only' ? 'Verse Only' : 'Full Song',
        chorus_strict: state.chorusStrict,
        producer_mode: state.outputMode === 'producer' || state.producerMode,
        target_genre: targetGenre || undefined,
        genre_blend: genreBlendEnabled ? {
          primary: genreBlendPrimary,
          secondary: genreBlendSecondary,
          weight: genreBlendWeight,
        } : undefined,
        producer_controls: producerControlsEnabled ? {
          darkness: producerDarkness,
          melodicness: producerMelodicness,
          aggression: producerAggression,
          atmosphere: producerAtmosphere,
          groove_density: producerGrooveDensity,
        } : undefined,
      }

      t1 = setTimeout(() => { markDone('lyrics'); nextStep('voice') }, 3000)
      t2 = setTimeout(() => { markDone('voice'); nextStep('music') }, 8000)
      t3 = setTimeout(() => { markDone('music'); nextStep('mix') }, 15000)
      t4 = setTimeout(() => { markDone('mix'); nextStep('analysis') }, 18000)

      const res = await generateSong(params, token, abortRef.current?.signal, uploadedInst)
      clearTimers()

      const failed = new Set<string>()
      const expectsVoice = state.outputMode === 'draft' ||
        (state.outputMode === 'producer' && state.producerVocalSource === 'reference_tts')
      const expectsMusic = state.outputMode === 'music_demo' ||
        (state.outputMode === 'producer' && state.producerVocalSource === 'suno_singing')
      if (expectsVoice && !res.voice_audio_b64) failed.add('voice')
      if (expectsMusic && !res.music_audio_b64) failed.add('music')
      if (state.outputMode === 'draft' && state.enableMix && !res.mixed_audio_b64) failed.add('mix')
      if (!res.analysis) failed.add('analysis')
      setFailedSteps(failed)
      setCompletedSteps(new Set(['lyrics','voice','music','mix','analysis'].filter(s => !failed.has(s))))
      setActiveStep('')

      setResult(res)
      const newHistory = [res, ...history]
      setHistory(newHistory)
      setPipelineStatus('complete')
      setActiveTab('lyrics')
      setActiveVariant(0)
      toast.success('Production complete!')

      // Auto-extract stems when Producer + AI Singing — skip the manual re-upload step
      let autoStemJobId: string | null = null
      if (
        state.outputMode === 'producer' &&
        state.producerVocalSource === 'suno_singing' &&
        res.music_audio_b64
      ) {
        try {
          const binary = atob(res.music_audio_b64)
          const bytes = new Uint8Array(binary.length)
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
          const blob = new Blob([bytes], { type: 'audio/mpeg' })
          const safeTs = res.timestamp.replace(/:/g, '-')
          const autoFile = new File([blob], `producer_song_${safeTs}.mp3`, { type: 'audio/mpeg' })
          setStemFile(autoFile)
          setStemStatus('uploading')
          setStemUrls({})
          toast('Stem extraction started automatically — see Stems tab in 2–8 min', { icon: '🎚️' })
          try {
            const { job_id } = await extractStems(token, autoFile)
            autoStemJobId = job_id   // capture locally — React state hasn't updated yet
            setStemJobId(job_id)
            setStemStatus('processing')
          } catch {
            setStemStatus('failed')
          }
        } catch { /* non-critical */ }
      }

      try {
        localStorage.setItem(STUDIO_RESULT_KEY, JSON.stringify(res))
        const historyMeta = newHistory.slice(0, 20).map(h => ({
          ...h, voice_audio_b64: null, music_audio_b64: null, mixed_audio_b64: null,
        }))
        localStorage.setItem(STUDIO_HISTORY_KEY, JSON.stringify(historyMeta))
      } catch { /* storage full */ }

      try {
        await saveProject(token, {
          title:            res.theme || state.theme || 'Untitled',
          theme:            res.theme || state.theme,
          artist:           state.artist || 'Unknown',
          lyrics:           res.lyrics,
          has_voice:        !!res.voice_audio_b64,
          has_music:        !!res.music_audio_b64,
          has_mix:          !!res.mixed_audio_b64,
          duration_s:       0,
          voice_audio_b64:  res.voice_audio_b64,
          music_audio_b64:  res.music_audio_b64,
          mixed_audio_b64:  res.mixed_audio_b64,
          language:         state.language,
          bars:             effectiveBars,
          structure:        state.structure,
          output_mode:      state.outputMode,
          gen_mode:         modeMap[state.genMode],
          perspective_mode: perspMap[state.perspective],
          gender:           state.gender,
          style_strength:   state.styleStrength,
          temperature:      state.temperature,
          chorus_strict:    state.chorusStrict,
          producer_mode:    state.outputMode === 'producer' || state.producerMode,
          section_mode:     state.sectionMode,
          ref_lyrics:       state.refLyrics || null,
          analysis:         res.analysis ?? null,
          stem_job_id:      autoStemJobId || stemJobId || null,
        })
      } catch { /* non-critical */ }

    } catch (err: unknown) {
      clearTimers()
      const isAbort =
        (err instanceof Error && (err.name === 'CanceledError' || err.name === 'AbortError')) ||
        (err as { code?: string })?.code === 'ERR_CANCELED'
      if (isAbort) {
        setPipelineStatus('idle'); setActiveStep(''); setCompletedSteps(new Set())
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
  }, [state, token, history, lockedChorus, uploadedInst])

  const formatLyrics = (text: string) =>
    text.split('\n').map((line, i) => {
      const isHeader = /^\[.+\]$/.test(line.trim())
      return (
        <span key={i}>
          {isHeader
            ? <span className="lyrics-section">{line}</span>
            : <span className="text-text-primary" style={{ lineHeight: '1.9' }}>{line}</span>
          }
          {'\n'}
        </span>
      )
    })

  // ── Chorus detection ──────────────────────────────────────────────────
  const detectChorus = useCallback(async () => {
    if (!state.refLyrics.trim()) return
    setDetectingChorus(true)
    try {
      const { chorus, found } = await extractChorus(token, state.refLyrics)
      if (found && chorus) {
        setDetectedChorus(chorus); setLockedChorus(chorus)
        toast.success('Chorus detected and locked!')
      } else {
        toast.error('No clear chorus found. Paste labeled lyrics or set manually.')
      }
    } catch { toast.error('Chorus detection failed.') }
    finally { setDetectingChorus(false) }
  }, [state.refLyrics, token])

  // ── Stem extraction ───────────────────────────────────────────────────
  const startStemExtraction = useCallback(async (file: File) => {
    if (!file) return
    setStemStatus('uploading')
    setStemUrls({})
    toast('Uploading for stem extraction…', { icon: '🎚️' })
    try {
      const { job_id } = await extractStems(token, file)
      setStemJobId(job_id)
      setStemStatus('processing')
      toast('Stems being extracted (2–8 min)…', { icon: '⚙️' })
    } catch (e: unknown) {
      setStemStatus('failed')
      const msg = e instanceof Error ? e.message : 'Upload failed'
      toast.error(`Stem extraction failed: ${msg}`)
    }
  }, [token])

  // Poll stem status
  useEffect(() => {
    if (!stemJobId || stemStatus !== 'processing') return
    const poll = setInterval(async () => {
      try {
        const job = await getStemStatus(token, stemJobId)
        if (job.status === 'done') {
          clearInterval(poll)
          setStemStatus('done'); setStemUrls(job.stems)
          toast.success('Stems extracted! See Stems tab.')
        } else if (job.status === 'failed') {
          clearInterval(poll)
          setStemStatus('failed')
          toast.error(`Stem extraction failed: ${job.error || 'unknown error'}`)
        }
      } catch { /* keep polling */ }
    }, 6000)
    return () => clearInterval(poll)
  }, [stemJobId, stemStatus, token])

  const handleLogout = () => {
    logout(token).finally(() => {
      localStorage.removeItem(SESSION_TOKEN_KEY)
      router.replace('/login')
    })
  }

  const clearAll = useCallback(() => {
    abortRef.current?.abort()
    setHistory([])
    setResult(null)
    setState(DEFAULT_STATE)
    setArtistQuery('')
    setPipelineStatus('idle')
    setActiveStep('')
    setCompletedSteps(new Set())
    setFailedSteps(new Set())
    setDetectedChorus('')
    setLockedChorus('')
    setStemJobId('')
    setStemStatus('idle')
    setStemUrls({})
    setStemFile(null)
    setUploadedInst(null)
    setActiveTab('lyrics')
    setActiveVariant(0)
    setRunning(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (stemFileRef.current) stemFileRef.current.value = ''
    localStorage.removeItem(STUDIO_RESULT_KEY)
    localStorage.removeItem(STUDIO_HISTORY_KEY)
  }, [])

  const pipelineSteps = buildSteps(activeStep, completedSteps, failedSteps, state.outputMode, state.producerVocalSource)
  const hasStemsReady = Object.keys(stemUrls).length > 0

  if (!authChecked) return null

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── SIDEBAR ─────────────────────────────────────────────────────── */}
      <aside className={`flex-shrink-0 transition-all duration-300 overflow-y-auto ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}
        style={{ background: '#111111', borderRight: '1px solid rgba(255,255,255,0.04)' }}>
        <div className="p-5 space-y-5 min-w-72">

          {/* Logo */}
          <div className="flex items-center gap-3 pb-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #8ff5ff, #d277ff)' }}>
              <Music2 size={16} color="#0e0e0e" />
            </div>
            <div>
              <div className="font-display font-bold text-sm text-text-primary">SonicFlow</div>
              <div className="text-xs text-text-muted">Studio v5</div>
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
            <button onClick={handleLogout}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-text-muted hover:text-text-primary hover:bg-glass transition-all w-full text-left">
              <Settings size={15} /> Sign Out
            </button>
          </nav>

          <div style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />

          {/* Artist */}
          <div>
            <label className="label">Artist</label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
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
                      <button key={s}
                        className="w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-glass hover:text-text-primary transition-colors"
                        onMouseDown={() => selectArtist(s)}>{s}</button>
                    ))}
                  </div>
                )}
              </div>
              <GlobalArtistPicker onSelect={selectArtist} currentLanguage={state.language} />
            </div>
          </div>

          {/* Creative Controls */}
          <div>
            <button className="flex items-center justify-between w-full text-left mb-3"
              onClick={() => setCreativeOpen(o => !o)}>
              <span className="section-title flex items-center gap-2"><Sliders size={13} /> Creative Controls</span>
              {creativeOpen ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            </button>

            {creativeOpen && (
              <div className="space-y-4">
                <div>
                  <label className="label flex justify-between">
                    Creativity <span style={{ color: '#8ff5ff' }}>{state.temperature}</span>
                  </label>
                  <input type="range" className="w-full" min={0.5} max={1.2} step={0.05}
                    value={state.temperature} onChange={e => set('temperature')(+e.target.value)} />
                </div>
                <div>
                  <label className="label flex justify-between">
                    Style Strength <span style={{ color: '#8ff5ff' }}>{state.styleStrength}</span>
                  </label>
                  <input type="range" className="w-full" min={0} max={1} step={0.05}
                    value={state.styleStrength} onChange={e => set('styleStrength')(+e.target.value)} />
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
                      <button key={b} onClick={() => set('bars')(b)}
                        className={`py-2 rounded-lg text-xs font-display font-semibold transition-all ${state.bars === b ? 'text-background' : 'text-text-muted hover:text-text-primary'}`}
                        style={state.bars === b ? { background: '#8ff5ff' } : { background: 'rgba(255,255,255,0.05)' }}>
                        {b}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="label">Creative Variants</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {([1,3,5] as const).map(v => (
                      <button key={v} onClick={() => set('numVariants')(v)}
                        className={`py-2 rounded-lg text-xs font-display font-semibold transition-all ${state.numVariants === v ? 'text-background' : 'text-text-muted hover:text-text-primary'}`}
                        style={state.numVariants === v ? { background: '#c3f400', color: '#0e0e0e' } : { background: 'rgba(255,255,255,0.05)' }}>
                        {v}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Section Mode */}
                <div>
                  <label className="label">Generation Mode</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {SECTION_MODES.map(m => (
                      <button key={m} onClick={() => set('sectionMode')(m)}
                        className={`py-2 rounded-lg text-xs font-display font-semibold transition-all ${state.sectionMode === m ? 'text-background' : 'text-text-muted hover:text-text-primary'}`}
                        style={state.sectionMode === m ? { background: '#d277ff', color: '#0e0e0e' } : { background: 'rgba(255,255,255,0.05)' }}>
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Output Mode */}
          <div>
            <label className="label">Output Mode</label>
            <div className="space-y-1.5">
              {(Object.entries(OUTPUT_MODE_CONFIG) as [OutputMode, typeof OUTPUT_MODE_CONFIG[OutputMode]][]).map(([id, cfg]) => (
                <button key={id} onClick={() => set('outputMode')(id)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all text-left"
                  style={state.outputMode === id
                    ? { background: `${cfg.color}18`, border: `1px solid ${cfg.color}40`, color: cfg.color }
                    : { background: 'rgba(255,255,255,0.03)', border: '1px solid transparent', color: '#555' }}>
                  <span className="flex-shrink-0">{cfg.icon}</span>
                  <div>
                    <div>{cfg.label}</div>
                    <div className="font-normal opacity-70">{cfg.sub}</div>
                  </div>
                </button>
              ))}
            </div>
            <p className="text-xs mt-2" style={{ color: '#444' }}>
              {OUTPUT_MODE_CONFIG[state.outputMode].desc}
            </p>
          </div>

          {/* Producer Vocal Source — only visible in Producer Remix mode */}
          {state.outputMode === 'producer' && (
            <div className="rounded-xl p-3 space-y-2" style={{ background: 'rgba(255,165,2,0.06)', border: '1px solid rgba(255,165,2,0.15)' }}>
              {/* Visual workflow guide */}
              <div className="flex items-center gap-1.5 text-xs font-semibold mb-1" style={{ color: '#ffa502' }}>
                Producer Flow
              </div>
              <div className="flex items-center gap-1 text-xs mb-2">
                {[
                  { n: 1, label: 'Generate' },
                  { n: 2, label: 'Extract Stems' },
                  { n: 3, label: 'Export to DAW' },
                ].map(({ n, label }, idx) => (
                  <div key={n} className="flex items-center gap-1">
                    <div className="w-4 h-4 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                      style={{ background: 'rgba(255,165,2,0.25)', color: '#ffa502', fontSize: '9px' }}>{n}</div>
                    <span style={{ color: '#888' }}>{label}</span>
                    {idx < 2 && <span style={{ color: '#444' }}>→</span>}
                  </div>
                ))}
              </div>
              <div style={{ height: '1px', background: 'rgba(255,165,2,0.1)' }} />
              <label className="label" style={{ color: '#ffa502' }}>Vocal Source</label>
              <button
                onClick={() => set('producerVocalSource')('suno_singing')}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all text-left"
                style={state.producerVocalSource === 'suno_singing'
                  ? { background: 'rgba(195,244,0,0.12)', border: '1px solid rgba(195,244,0,0.3)', color: '#c3f400' }
                  : { background: 'rgba(255,255,255,0.03)', border: '1px solid transparent', color: '#555' }}>
                <Music2 size={11} />
                <div>
                  <div>AI Singing <span className="font-normal opacity-60">(Suno)</span></div>
                  <div className="font-normal opacity-60">Musical vocals — recommended</div>
                </div>
              </button>
              <button
                onClick={() => set('producerVocalSource')('reference_tts')}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all text-left"
                style={state.producerVocalSource === 'reference_tts'
                  ? { background: 'rgba(210,119,255,0.10)', border: '1px solid rgba(210,119,255,0.25)', color: '#d277ff' }
                  : { background: 'rgba(255,255,255,0.03)', border: '1px solid transparent', color: '#555' }}>
                <Mic2 size={11} />
                <div>
                  <div>Timing Guide <span className="font-normal opacity-60">(Fast)</span></div>
                  <div className="font-normal opacity-60">TTS rhythm reference only</div>
                </div>
              </button>
              {state.producerVocalSource === 'reference_tts' && (
                <p className="text-xs px-1" style={{ color: '#888' }}>
                  TTS is spoken — not singable. Use for bar-count reference only.
                </p>
              )}
            </div>
          )}

          {/* Multimodal Tools */}
          <div>
            <button className="flex items-center justify-between w-full text-left mb-3"
              onClick={() => setMultimodalOpen(o => !o)}>
              <span className="section-title flex items-center gap-2"><Mic2 size={13} /> Audio Tools</span>
              {multimodalOpen ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            </button>

            {multimodalOpen && (
              <div className="space-y-3">
                {/* Upload Instrumental */}
                <div>
                  <label className="label flex items-center gap-1.5">
                    <Upload size={11} /> Upload Instrumental
                    <span className="text-xs text-text-muted">(shapes lyric style)</span>
                  </label>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="w-full py-2.5 rounded-xl text-xs border border-dashed transition-colors hover:border-primary hover:text-primary"
                    style={{
                      borderColor: uploadedInst ? 'rgba(210,119,255,0.4)' : 'rgba(255,255,255,0.12)',
                      color: uploadedInst ? '#d277ff' : undefined,
                      background: uploadedInst ? 'rgba(210,119,255,0.06)' : undefined,
                    }}
                  >
                    <Upload size={13} className="inline mr-1.5" />
                    {uploadedInst ? uploadedInst.name : 'MP3 / WAV'}
                  </button>
                  <input ref={fileInputRef} type="file" accept=".mp3,.wav" className="hidden"
                    onChange={e => setUploadedInst(e.target.files?.[0] ?? null)} />
                  {uploadedInst && (
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-xs flex items-center gap-1" style={{ color: '#d277ff' }}>
                        {analyzingTrack
                          ? <><Loader2 size={10} className="animate-spin" /> Analyzing audio...</>
                          : '✓ Shaping lyric cadence'
                        }
                      </span>
                      <button onClick={() => { setUploadedInst(null); setInstrumentalAnalysis(null) }}
                        className="text-xs text-text-muted hover:text-error">remove</button>
                    </div>
                  )}
                  {/* BPM / Key / Energy badges */}
                  {instrumentalAnalysis && !instrumentalAnalysis.error && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      <span className="px-2 py-0.5 rounded-md text-xs font-semibold"
                        style={{ background: 'rgba(143,245,255,0.12)', color: '#8ff5ff' }}>
                        {instrumentalAnalysis.bpm.toFixed(0)} BPM
                      </span>
                      <span className="px-2 py-0.5 rounded-md text-xs font-semibold"
                        style={{ background: 'rgba(195,244,0,0.10)', color: '#c3f400' }}>
                        {instrumentalAnalysis.key}
                      </span>
                      <span className="px-2 py-0.5 rounded-md text-xs font-semibold capitalize"
                        style={{ background: 'rgba(210,119,255,0.10)', color: '#d277ff' }}>
                        {instrumentalAnalysis.energy_intensity} energy
                      </span>
                    </div>
                  )}
                </div>

                {/* Mix toggle — Draft mode only */}
                {state.outputMode === 'draft' && uploadedInst && (
                  <label className="flex items-center justify-between cursor-pointer">
                    <div>
                      <span className="text-sm text-text-secondary flex items-center gap-1.5">
                        <Blend size={11} /> Mix with Uploaded Track
                      </span>
                      <p className="text-xs text-text-muted">Vocal layered over your beat</p>
                    </div>
                    <div className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${state.enableMix ? 'bg-primary' : 'bg-surface-3'}`}
                      onClick={() => set('enableMix')(!state.enableMix)}>
                      <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.enableMix ? 'translate-x-5' : 'translate-x-0.5'}`} />
                    </div>
                  </label>
                )}

                {/* Stem Extraction */}
                <div style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />
                <div>
                  <label className="label flex items-center gap-1.5"><Scissors size={11} /> Stem Extraction</label>
                  <button onClick={() => stemFileRef.current?.click()}
                    className="w-full py-2.5 rounded-xl text-xs text-text-muted border border-dashed transition-colors hover:border-accent hover:text-accent"
                    style={{ borderColor: 'rgba(195,244,0,0.2)' }}>
                    <Upload size={13} className="inline mr-1.5" />
                    {stemFile ? stemFile.name : 'Upload MP3/WAV for stems'}
                  </button>
                  <input ref={stemFileRef} type="file" accept=".mp3,.wav" className="hidden"
                    onChange={e => {
                      const f = e.target.files?.[0] ?? null
                      setStemFile(f)
                      if (f) startStemExtraction(f)
                    }} />
                  {stemStatus !== 'idle' && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs"
                      style={{ color: stemStatus === 'done' ? '#c3f400' : stemStatus === 'failed' ? '#ff4757' : '#ffa502' }}>
                      {(stemStatus === 'uploading' || stemStatus === 'processing') && <Loader2 size={11} className="animate-spin" />}
                      {stemStatus === 'uploading' && 'Uploading…'}
                      {stemStatus === 'processing' && 'Extracting (2–8 min)…'}
                      {stemStatus === 'done' && '✓ Stems ready — see Stems tab'}
                      {stemStatus === 'failed' && 'Extraction failed'}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Advanced Options */}
          <div>
            <button className="flex items-center justify-between w-full text-left mb-3"
              onClick={() => setAdvancedOpen(o => !o)}>
              <span className="section-title flex items-center gap-2"><Wand2 size={13} /> Advanced Options</span>
              {advancedOpen ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            </button>

            {advancedOpen && (
              <div className="space-y-3">
                {/* Chorus Mode */}
                <label className="flex items-center justify-between cursor-pointer">
                  <div>
                    <span className="text-sm text-text-secondary">Hook Writing Mode (Short Form)</span>
                    <p className="text-xs text-text-muted">3-line chorus, 4-6 words each</p>
                  </div>
                  <div className={`relative w-10 h-5 rounded-full transition-colors ${state.chorusStrict ? 'bg-primary' : 'bg-surface-3'}`}
                    onClick={() => set('chorusStrict')(!state.chorusStrict)}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.chorusStrict ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>

                {/* Producer Mode */}
                <label className="flex items-center justify-between cursor-pointer">
                  <div>
                    <span className="text-sm text-text-secondary flex items-center gap-1.5">
                      <Layers size={12} /> Producer Mode
                    </span>
                    <p className="text-xs text-text-muted">Structure, rhyme + tempo focus</p>
                  </div>
                  <div className={`relative w-10 h-5 rounded-full transition-colors ${state.producerMode ? 'bg-primary' : 'bg-surface-3'}`}
                    onClick={() => set('producerMode')(!state.producerMode)}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.producerMode ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>

                {/* Fast Mode */}
                <label className="flex items-center justify-between cursor-pointer">
                  <div>
                    <span className="text-sm text-text-secondary flex items-center gap-1.5">
                      <Zap size={12} /> Fast Mode
                    </span>
                    <p className="text-xs text-text-muted">8 bars, 1 variant — under 10s</p>
                  </div>
                  <div className={`relative w-10 h-5 rounded-full transition-colors ${state.fastMode ? 'bg-accent' : 'bg-surface-3'}`}
                    onClick={() => set('fastMode')(!state.fastMode)}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background transition-transform ${state.fastMode ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </div>
                </label>
              </div>
            )}
          </div>

          <div style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />

          {/* Clear */}
          <button
            onClick={clearAll}
            className="flex items-center gap-2 w-full px-3 py-2.5 rounded-xl text-sm text-text-muted hover:text-error hover:bg-glass transition-all">
            <Trash2 size={14} /> Clear Project
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ─────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center justify-between px-6 py-4"
          style={{ background: 'rgba(14,14,14,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(o => !o)}
              className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all">
              <Sliders size={16} />
            </button>
            <div>
              <h1 className="font-display font-bold text-lg text-text-primary leading-none">
                Global AI Music Studio
              </h1>
              <p className="text-xs text-text-muted mt-0.5">
                AI Songwriting · Stem Extraction · Multi-language
                <span style={{ color: OUTPUT_MODE_CONFIG[state.outputMode].color }}>
                  {' '}· {OUTPUT_MODE_CONFIG[state.outputMode].label}
                </span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {(result || running || pipelineStatus !== 'idle') && (
              <button
                onClick={clearAll}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all hover:scale-105 active:scale-95"
                style={{ background: 'rgba(255,71,87,0.10)', color: '#ff4757', border: '1px solid rgba(255,71,87,0.2)' }}
                title="Clear all and start fresh"
              >
                <RotateCcw size={11} /> New Project
              </button>
            )}
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full pulse-dot" style={{ background: '#2ed573' }} />
              <span className="text-xs text-text-muted">System Online</span>
            </div>
          </div>
        </header>

        <div className="flex gap-6 p-6">
          {/* ── LEFT: Input ─────────────────────────────────────────────── */}
          <div className="flex-1 max-w-xl space-y-5">

            {/* Stem Status Panel — always visible, independent of lyrics */}
            <StemStatusPanel
              stemFile={stemFile}
              stemStatus={stemStatus}
              stemUrls={stemUrls}
              stemJobId={stemJobId}
              onTabSwitch={() => setActiveTab('stems')}
            />

            {/* Theme & Mode */}
            <div className="glass-panel p-5 space-y-4">
              <h2 className="font-display font-semibold text-sm text-text-secondary uppercase tracking-widest">
                1. Theme & Creative Mode
              </h2>
              <div>
                <label className="label">Project Theme</label>
                <input className="input-field" placeholder="nostalgic late night drive in Seoul"
                  value={state.theme} onChange={e => set('theme')(e.target.value)} />
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
              <textarea className="input-field resize-none" rows={5}
                placeholder="Paste existing lyrics here (optional — used for Continue / Remix)..."
                value={state.refLyrics}
                onChange={e => { set('refLyrics')(e.target.value); setDetectedChorus(''); setLockedChorus('') }} />

              {state.genMode === 'Remix Style' && (
                <div className="space-y-3">
                  {/* Step indicator for Remix flow */}
                  <div className="flex items-center gap-2 text-xs">
                    {[
                      { n: 1, label: 'Paste lyrics' },
                      { n: 2, label: 'Lock chorus' },
                      { n: 3, label: 'Generate' },
                    ].map(({ n, label }, idx) => {
                      const done = n === 1 ? state.refLyrics.trim().length >= 30
                                 : n === 2 ? !!lockedChorus
                                 : false
                      const active = n === 1 ? state.refLyrics.trim().length < 30
                                   : n === 2 ? state.refLyrics.trim().length >= 30 && !lockedChorus
                                   : !!lockedChorus
                      return (
                        <div key={n} className="flex items-center gap-1.5">
                          <div className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                            style={{
                              background: done ? '#c3f400' : active ? 'rgba(143,245,255,0.2)' : 'rgba(255,255,255,0.06)',
                              color: done ? '#0e0e0e' : active ? '#8ff5ff' : '#555',
                            }}>{n}</div>
                          <span style={{ color: done ? '#c3f400' : active ? '#8ff5ff' : '#444' }}>{label}</span>
                          {idx < 2 && <span className="text-text-muted">→</span>}
                        </div>
                      )
                    })}
                  </div>

                  <button onClick={detectChorus}
                    disabled={detectingChorus || state.refLyrics.trim().length < 30}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
                    style={{ background: 'rgba(195,244,0,0.10)', color: '#c3f400', border: '1px solid rgba(195,244,0,0.2)' }}>
                    {detectingChorus
                      ? <><Loader2 size={12} className="animate-spin" /> Detecting Chorus…</>
                      : <><Scissors size={12} /> Detect &amp; Lock Chorus</>}
                  </button>

                  {detectedChorus && (
                    <div className="rounded-xl p-3 space-y-1"
                      style={{ background: 'rgba(195,244,0,0.06)', border: '1px solid rgba(195,244,0,0.15)' }}>
                      <div className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: '#c3f400' }}>
                        <Lock size={11} /> CHORUS LOCKED — will not be changed
                      </div>
                      <pre className="text-xs text-text-secondary whitespace-pre-wrap leading-relaxed">
                        {detectedChorus}
                      </pre>
                      <button onClick={() => { setDetectedChorus(''); setLockedChorus('') }}
                        className="text-xs text-text-muted hover:text-error transition-colors mt-1">
                        Remove lock
                      </button>
                    </div>
                  )}
                </div>
              )}
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
                {(STRUCTURES[state.structure] ?? []).map((s, i) => (
                  <span key={i} className="px-2 py-0.5 rounded-md text-xs"
                    style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff' }}>{s}</span>
                ))}
              </div>
            </div>

            {/* Sound Design */}
            <div className="glass-panel p-5 space-y-4">
              <h2 className="font-display font-semibold text-sm text-text-secondary uppercase tracking-widest">
                4. Sound Design
              </h2>

              {/* Target Genre */}
              <div>
                <label className="label">Target Genre</label>
                <select className="select-field" value={targetGenre} onChange={e => setTargetGenre(e.target.value)}>
                  <option value="">— auto (from artist) —</option>
                  {GENRE_OPTIONS.map(g => <option key={g} value={g}>{g.replace('_', ' ')}</option>)}
                </select>
              </div>

              {/* Genre Blend */}
              <div>
                <label className="label flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={genreBlendEnabled} onChange={e => setGenreBlendEnabled(e.target.checked)}
                    className="w-3.5 h-3.5 rounded accent-lime-400" />
                  <Blend size={12} style={{ color: '#c3f400' }} />
                  Genre Blend
                </label>
                {genreBlendEnabled && (
                  <div className="mt-2 space-y-2 pl-1">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="label text-xs">Primary</label>
                        <select className="select-field text-xs py-1" value={genreBlendPrimary}
                          onChange={e => setGenreBlendPrimary(e.target.value)}>
                          {GENRE_OPTIONS.map(g => <option key={g} value={g}>{g.replace('_', ' ')}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="label text-xs">Secondary</label>
                        <select className="select-field text-xs py-1" value={genreBlendSecondary}
                          onChange={e => setGenreBlendSecondary(e.target.value)}>
                          {GENRE_OPTIONS.map(g => <option key={g} value={g}>{g.replace('_', ' ')}</option>)}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="label flex justify-between text-xs">
                        Blend Weight
                        <span style={{ color: '#c3f400' }}>
                          {genreBlendWeight <= 0.3 ? `${genreBlendPrimary} dominant` :
                           genreBlendWeight >= 0.7 ? `${genreBlendSecondary} dominant` : 'even mix'}
                        </span>
                      </label>
                      <input type="range" className="w-full" min={0} max={1} step={0.05}
                        value={genreBlendWeight} onChange={e => setGenreBlendWeight(+e.target.value)} />
                    </div>
                  </div>
                )}
              </div>

              {/* Producer Controls — only in Producer mode */}
              {(state.outputMode === 'producer' || state.producerMode) && (
                <div>
                  <label className="label flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={producerControlsEnabled} onChange={e => setProducerControlsEnabled(e.target.checked)}
                      className="w-3.5 h-3.5 rounded accent-orange-400" />
                    <Sliders size={12} style={{ color: '#ffa502' }} />
                    Producer Controls
                  </label>
                  {producerControlsEnabled && (
                    <div className="mt-2 space-y-2 pl-1">
                      {([
                        ['Darkness',      producerDarkness,      setProducerDarkness],
                        ['Melodicness',   producerMelodicness,   setProducerMelodicness],
                        ['Aggression',    producerAggression,    setProducerAggression],
                        ['Atmosphere',    producerAtmosphere,    setProducerAtmosphere],
                        ['Groove Density',producerGrooveDensity, setProducerGrooveDensity],
                      ] as [string, number, (v: number) => void][]).map(([label, val, setter]) => (
                        <div key={label}>
                          <label className="label flex justify-between text-xs">
                            {label} <span style={{ color: '#ffa502' }}>{val.toFixed(2)}</span>
                          </label>
                          <input type="range" className="w-full" min={0} max={1} step={0.05}
                            value={val} onChange={e => setter(+e.target.value)} />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Generate */}
            <div className="flex gap-3">
              <button onClick={generate} disabled={running}
                className="btn-primary flex-1 py-4 text-base flex items-center justify-center gap-2">
                {running
                  ? <><RotateCcw size={18} className="animate-spin" /> Producing...</>
                  : <><Zap size={18} /> IGNITE PRODUCTION</>}
              </button>
              {running && (
                <button onClick={() => abortRef.current?.abort()}
                  className="flex-shrink-0 flex items-center justify-center gap-2 px-5 py-4 rounded-xl font-display font-semibold text-sm transition-all hover:scale-105 active:scale-95"
                  style={{ background: 'rgba(255,71,87,0.12)', border: '1px solid rgba(255,71,87,0.3)', color: '#ff4757' }}>
                  <Square size={16} fill="#ff4757" /> Stop
                </button>
              )}
            </div>

            <GenerationStatus steps={pipelineSteps} overallStatus={pipelineStatus} />
          </div>

          {/* ── RIGHT: Output ────────────────────────────────────────────── */}
          <div className="flex-1 space-y-5">

            {/* Stems panel visible even without lyrics result */}
            {hasStemsReady && !result && (
              <div className="glass-panel p-5 space-y-3">
                <h3 className="section-title">🎚️ Extracted Stems</h3>
                <StemPlayer stems={stemUrls} />
              </div>
            )}

            {!result && !hasStemsReady ? (
              <div className="glass-panel p-10 text-center space-y-4">
                <div className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
                  style={{ background: 'rgba(143,245,255,0.06)' }}>
                  <Music2 size={32} style={{ color: '#8ff5ff', opacity: 0.4 }} />
                </div>
                <p className="text-text-muted text-sm">
                  Studio is ready. Define your theme on the left to begin.
                </p>
              </div>
            ) : result ? (
              <div className="animate-slide-up space-y-5">
                <div className="flex items-center justify-between gap-3 overflow-hidden">
                  <div className="min-w-0 overflow-hidden">
                    <h2 className="font-display font-bold text-xl text-text-primary truncate">
                      {result.theme || 'Latest Project'}
                    </h2>
                    <p className="text-xs text-text-muted">{result.timestamp}</p>
                    {result.instrumental_hint && (
                      <p className="text-xs mt-0.5" style={{ color: '#d277ff' }}>
                        🎛️ Lyrics styled to uploaded instrumental
                      </p>
                    )}
                    {result.suno_style_tags && (
                      <p className="text-xs mt-0.5 font-mono" style={{ color: '#8ff5ff', opacity: 0.7 }}>
                        🎨 {result.suno_style_tags}
                      </p>
                    )}
                  </div>
                </div>

                {/* Audio Players — context-aware by output_mode */}
                <div className="glass-panel p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="section-title">Production Output</h3>
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                      style={{
                        background: `${OUTPUT_MODE_CONFIG[result.output_mode as OutputMode]?.color || '#8ff5ff'}18`,
                        color: OUTPUT_MODE_CONFIG[result.output_mode as OutputMode]?.color || '#8ff5ff',
                      }}>
                      {OUTPUT_MODE_CONFIG[result.output_mode as OutputMode]?.label || result.output_mode}
                    </span>
                  </div>

                  {/* DRAFT MODE: ElevenLabs voice + optional mix */}
                  {result.output_mode === 'draft' && (
                    <>
                      {result.voice_audio_b64 ? (
                        <AudioPlayer b64={result.voice_audio_b64} label="Draft Vocal (ElevenLabs)"
                          filename={`vocal_draft_${result.timestamp}.mp3`} accentColor="#d277ff" />
                      ) : (
                        <div className="flex items-center gap-2 text-error text-xs p-3 rounded-xl"
                          style={{ background: 'rgba(255,71,87,0.08)' }}>
                          <AlertCircle size={14} />
                          Vocal generation failed — {result.voice_error || 'check ElevenLabs API key'}
                        </div>
                      )}
                      {result.mixed_audio_b64 && (
                        <AudioPlayer b64={result.mixed_audio_b64} label="Quick Demo Mix (Vocal + Beat)"
                          filename={`demo_mix_${result.timestamp}.mp3`} accentColor="#ffa502" />
                      )}
                      {state.enableMix && !result.mixed_audio_b64 && result.mix_error && (
                        <div className="flex items-center gap-2 text-xs p-3 rounded-xl"
                          style={{ background: 'rgba(255,165,2,0.05)', color: '#ffa502' }}>
                          <Info size={14} /> Mix unavailable — {result.mix_error}
                        </div>
                      )}
                      {uploadedInst && (
                        <div className="space-y-2">
                          <span className="section-title">Your Uploaded Beat</span>
                          <audio src={URL.createObjectURL(uploadedInst)} controls className="w-full" />
                        </div>
                      )}
                    </>
                  )}

                  {/* MUSIC DEMO MODE: Suno full song */}
                  {result.output_mode === 'music_demo' && (
                    <>
                      {result.music_audio_b64 ? (
                        <AudioPlayer b64={result.music_audio_b64} label="Full Song (Suno AI — vocals + instruments)"
                          filename={`full_song_${result.timestamp}.mp3`} accentColor="#c3f400" />
                      ) : (
                        <div className="flex items-center gap-2 text-xs p-3 rounded-xl"
                          style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502' }}>
                          <Info size={14} />
                          Music generation failed — {result.music_error || 'check Suno credits'}
                        </div>
                      )}
                      <div className="text-xs p-3 rounded-xl" style={{ background: 'rgba(195,244,0,0.04)', color: '#555' }}>
                        Suno generates complete songs with real vocal delivery + instrumentation.
                        Download below and import to your DAW.
                      </div>
                    </>
                  )}

                  {/* PRODUCER MODE */}
                  {result.output_mode === 'producer' && (
                    <>
                      {/* AI Singing path — Suno full song */}
                      {result.music_audio_b64 && (
                        <>
                          <AudioPlayer b64={result.music_audio_b64}
                            label="AI Song (Suno — real vocals + instruments)"
                            filename={`producer_song_${result.timestamp.replace(/:/g,'-')}.mp3`} accentColor="#c3f400" />
                          <div className="text-xs p-3 rounded-xl"
                            style={{ background: 'rgba(195,244,0,0.06)', color: '#c3f400', border: '1px solid rgba(195,244,0,0.12)' }}>
                            {stemStatus === 'processing' || stemStatus === 'uploading'
                              ? '⚙️ Stem extraction running automatically — check Stems tab in 2–8 min'
                              : stemStatus === 'done'
                              ? '✓ Stems extracted automatically — see Stems tab'
                              : 'Stem extraction will start automatically. Check the Stems tab for isolated vocals, drums, and bass.'}
                          </div>
                        </>
                      )}
                      {!result.music_audio_b64 && result.music_error && (
                        <div className="flex items-center gap-2 text-xs p-3 rounded-xl"
                          style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502' }}>
                          <Info size={14} /> Suno generation failed — {result.music_error}
                        </div>
                      )}

                      {/* Reference TTS path — ElevenLabs timing guide */}
                      {result.voice_audio_b64 && (
                        <>
                          <AudioPlayer b64={result.voice_audio_b64}
                            label="Timing Guide Vocal (TTS — rhythm reference only)"
                            filename={`timing_guide_${result.timestamp}.mp3`} accentColor="#d277ff" />
                          <div className="text-xs p-3 rounded-xl"
                            style={{ background: 'rgba(210,119,255,0.06)', color: '#888' }}>
                            This is spoken delivery — use it to map bar lengths and phrasing in your DAW, not for final vocal.
                          </div>
                        </>
                      )}
                      {!result.voice_audio_b64 && result.voice_error && (
                        <div className="flex items-center gap-2 text-error text-xs p-3 rounded-xl"
                          style={{ background: 'rgba(255,71,87,0.08)' }}>
                          <AlertCircle size={14} />
                          Voice generation failed — {result.voice_error}
                        </div>
                      )}

                      {/* DAW export buttons */}
                      {(result.music_audio_b64 || result.voice_audio_b64) && (
                        <div className="space-y-2">
                          <div className="text-xs font-semibold" style={{ color: '#ffa502' }}>
                            Export for DAW
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {result.music_audio_b64 && (
                              <button
                                onClick={() => b64ToDownloadUrl(result.music_audio_b64!, `producer_song_${result.timestamp}.mp3`)}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all"
                                style={{ background: 'rgba(195,244,0,0.10)', color: '#c3f400', border: '1px solid rgba(195,244,0,0.2)' }}>
                                <Download size={11} /> full_song.mp3
                              </button>
                            )}
                            {result.voice_audio_b64 && (
                              <button
                                onClick={() => b64ToDownloadUrl(result.voice_audio_b64!, `timing_guide_${result.timestamp}.mp3`)}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all"
                                style={{ background: 'rgba(210,119,255,0.10)', color: '#d277ff', border: '1px solid rgba(210,119,255,0.2)' }}>
                                <Download size={11} /> timing_guide.mp3
                              </button>
                            )}
                            {uploadedInst && (
                              <a
                                href={URL.createObjectURL(uploadedInst)}
                                download={uploadedInst.name}
                                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all"
                                style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502', border: '1px solid rgba(255,165,2,0.2)' }}>
                                <Download size={11} /> instrumental.{uploadedInst.name.split('.').pop()}
                              </a>
                            )}
                          </div>

                          {/* DAW Session ZIP export */}
                          <button
                            onClick={exportDAWSession}
                            disabled={dawExporting}
                            title="Download stems, MIDI, arrangement markers and project file"
                            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-50 w-full justify-center"
                            style={{ background: 'rgba(255,165,2,0.12)', color: '#ffa502', border: '1px solid rgba(255,165,2,0.3)' }}>
                            {dawExporting
                              ? <><Loader2 size={12} className="animate-spin" /> Building session...</>
                              : <><Download size={12} /> Export DAW Session (ZIP)</>}
                          </button>

                          <p className="text-xs" style={{ color: '#555' }}>
                            Ready for FL Studio · Logic Pro · Ableton Live · Includes MIDI + arrangement markers
                          </p>
                          {hasStemsReady && (
                            <p className="text-xs" style={{ color: '#c3f400' }}>
                              ✓ Individual stems available in Stems tab
                            </p>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Tabs */}
                <div className="glass-panel overflow-hidden">
                  <div className="flex border-b overflow-x-auto" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
                    {(['lyrics','insights','variants','stats', ...(hasStemsReady ? ['stems'] : [])] as const).map(tab => (
                      <button key={tab}
                        onClick={() => setActiveTab(tab as typeof activeTab)}
                        className={`flex-shrink-0 flex-1 py-3 text-xs font-display font-semibold uppercase tracking-wider transition-all ${activeTab === tab ? 'tab-active' : 'text-text-muted hover:text-text-secondary'}`}>
                        {tab === 'lyrics'   ? '📝 Lyrics'
                          : tab === 'insights' ? '💡 Insights'
                          : tab === 'variants' ? '🌈 Variants'
                          : tab === 'stems'    ? '🎚️ Stems'
                          : '📊 Stats'}
                      </button>
                    ))}
                  </div>

                  <div className="p-5">
                    {/* Lyrics */}
                    {activeTab === 'lyrics' && (
                      <div className="space-y-3">
                        {result.locked_chorus && (
                          <div className="rounded-lg px-3 py-2 text-xs flex items-center justify-between"
                            style={{ background: 'rgba(195,244,0,0.06)', border: '1px solid rgba(195,244,0,0.15)', color: '#c3f400' }}>
                            <span><Lock size={10} className="inline mr-1" /> Chorus locked during remix</span>
                            {result.chorus_preserved === true && (
                              <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                                style={{ background: 'rgba(195,244,0,0.15)', color: '#c3f400' }}>
                                ✓ Preserved
                              </span>
                            )}
                            {result.chorus_preserved === false && (
                              <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                                style={{ background: 'rgba(255,71,87,0.12)', color: '#ff4757' }}>
                                ✗ Modified
                              </span>
                            )}
                          </div>
                        )}
                        <div className="whitespace-pre-wrap text-sm leading-loose font-body">
                          {formatLyrics(result.lyrics)}
                        </div>
                      </div>
                    )}

                    {/* Insights — real analysis */}
                    {activeTab === 'insights' && (
                      <div className="space-y-4">
                        <h3 className="section-title">AI Production Analysis</h3>

                        {/* Instrumental analysis badges if available */}
                        {instrumentalAnalysis !== null ? (
                          instrumentalAnalysis.error === null ? (
                            <div className="rounded-xl p-3 space-y-2"
                              style={{ background: 'rgba(143,245,255,0.05)', border: '1px solid rgba(143,245,255,0.12)' }}>
                              <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#8ff5ff' }}>
                                Instrumental Profile
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(143,245,255,0.1)', color: '#8ff5ff' }}>
                                  {instrumentalAnalysis.bpm.toFixed(0)} BPM
                                </span>
                                <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(195,244,0,0.08)', color: '#c3f400' }}>
                                  {instrumentalAnalysis.key}
                                </span>
                                <span className="px-2 py-0.5 rounded text-xs capitalize" style={{ background: 'rgba(210,119,255,0.08)', color: '#d277ff' }}>
                                  {instrumentalAnalysis.energy_intensity} energy
                                </span>
                                <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502' }}>
                                  {instrumentalAnalysis.stress_pattern}
                                </span>
                              </div>
                              {instrumentalAnalysis.flow_descriptors.length > 0 ? (
                                <p className="text-xs" style={{ color: '#888' }}>
                                  Flow: {instrumentalAnalysis.flow_descriptors.join(' · ')}
                                </p>
                              ) : null}
                            </div>
                          ) : null
                        ) : null}

                        {/* Flow Profile card from generated lyrics */}
                        {result.analysis != null && Boolean((result.analysis as Record<string, unknown>).cadence_profile) ? (
                          <div className="rounded-xl p-3 space-y-2"
                            style={{ background: 'rgba(195,244,0,0.04)', border: '1px solid rgba(195,244,0,0.1)' }}>
                            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#c3f400' }}>
                              Flow Profile
                            </div>
                            {(() => {
                              const cp = (result.analysis as Record<string, unknown>).cadence_profile as Record<string, string | number>
                              return (
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                  {cp.rhyme_scheme ? (
                                    <div><span className="text-text-muted">Rhyme:</span> <span style={{ color: '#c3f400' }}>{String(cp.rhyme_scheme)}</span></div>
                                  ) : null}
                                  {cp.avg_syllables_per_line ? (
                                    <div><span className="text-text-muted">Syllables/line:</span> <span style={{ color: '#c3f400' }}>{Number(cp.avg_syllables_per_line).toFixed(1)}</span></div>
                                  ) : null}
                                  {cp.flow_density ? (
                                    <div><span className="text-text-muted">Flow density:</span> <span style={{ color: '#c3f400' }}>{String(cp.flow_density)}</span></div>
                                  ) : null}
                                  {cp.stress_style ? (
                                    <div><span className="text-text-muted">Stress style:</span> <span style={{ color: '#c3f400' }}>{String(cp.stress_style)}</span></div>
                                  ) : null}
                                </div>
                              )
                            })()}
                          </div>
                        ) : null}

                        {/* Cadence Meta — from intelligence layer */}
                        {result.cadence_meta && (
                          <div className="rounded-xl p-3 space-y-2"
                            style={{ background: 'rgba(210,119,255,0.04)', border: '1px solid rgba(210,119,255,0.1)' }}>
                            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#d277ff' }}>
                              Cadence Transfer
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              {result.cadence_meta.source === 'reference' && (
                                <div className="col-span-2">
                                  <span className="text-text-muted">Source:</span>{' '}
                                  <span style={{ color: '#d277ff' }}>reference lyrics</span>
                                </div>
                              )}
                              {result.cadence_meta.avg_syllables_per_line != null && (
                                <div><span className="text-text-muted">Syllables/line:</span>{' '}
                                  <span style={{ color: '#d277ff' }}>{Number(result.cadence_meta.avg_syllables_per_line).toFixed(1)}</span>
                                </div>
                              )}
                              {result.cadence_meta.rhyme_scheme && (
                                <div><span className="text-text-muted">Rhyme:</span>{' '}
                                  <span style={{ color: '#d277ff' }}>{result.cadence_meta.rhyme_scheme}</span>
                                </div>
                              )}
                              {result.cadence_meta.flow_density && (
                                <div><span className="text-text-muted">Flow:</span>{' '}
                                  <span style={{ color: '#d277ff' }}>{result.cadence_meta.flow_density}</span>
                                </div>
                              )}
                              {result.cadence_meta.stress_style && (
                                <div><span className="text-text-muted">Stress:</span>{' '}
                                  <span style={{ color: '#d277ff' }}>{result.cadence_meta.stress_style}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {result.analysis ? (
                          <div className="space-y-3">
                            {Object.entries(result.analysis).filter(([k]) => k !== 'cadence_profile').map(([key, val]) => (
                              <div key={key} className="space-y-1">
                                <div className="text-xs font-semibold uppercase tracking-wider"
                                  style={{ color: '#8ff5ff' }}>
                                  {key.replace(/_/g, ' ')}
                                </div>
                                {Array.isArray(val) ? (
                                  <ul className="space-y-1">
                                    {(val as string[]).map((item, i) => (
                                      <li key={i} className="text-xs text-text-secondary flex gap-2">
                                        <span style={{ color: '#c3f400' }}>▸</span> {item}
                                      </li>
                                    ))}
                                  </ul>
                                ) : typeof val === 'object' && val !== null ? (
                                  <pre className="text-xs text-text-secondary overflow-auto rounded p-2"
                                    style={{ background: 'rgba(255,255,255,0.02)', maxHeight: '120px' }}>
                                    {JSON.stringify(val, null, 2)}
                                  </pre>
                                ) : (
                                  <p className="text-xs text-text-secondary">{String(val)}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-text-muted text-sm">Analysis unavailable.</p>
                        )}
                      </div>
                    )}

                    {/* Variants */}
                    {activeTab === 'variants' && (
                      <div className="space-y-3">
                        <div className="flex gap-2">
                          {result.versions?.map((_, i) => (
                            <button key={i} onClick={() => setActiveVariant(i)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-display font-semibold transition-all ${activeVariant === i ? 'text-background' : 'text-text-muted hover:text-text-primary'}`}
                              style={activeVariant === i ? { background: '#c3f400' } : { background: 'rgba(255,255,255,0.05)' }}>
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

                    {/* Stems */}
                    {activeTab === 'stems' && (
                      <div className="space-y-3">
                        <h3 className="section-title">Extracted Stems</h3>
                        {hasStemsReady
                          ? <StemPlayer stems={stemUrls} />
                          : (
                            <p className="text-text-muted text-sm">
                              {stemStatus === 'processing'
                                ? 'Stem extraction in progress — check back in a few minutes.'
                                : 'Upload an MP3 in the sidebar to extract stems.'}
                            </p>
                          )}
                      </div>
                    )}

                    {/* Stats */}
                    {activeTab === 'stats' && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="glass-panel p-4 text-center">
                            <div className="text-2xl font-display font-bold" style={{ color: '#8ff5ff' }}>
                              {result.retrieval_quality.toFixed(3)}
                            </div>
                            <div className="text-xs text-text-muted mt-1">Retrieval Quality</div>
                          </div>
                          <div className="glass-panel p-4 text-center">
                            <div className="text-2xl font-display font-bold" style={{ color: '#c3f400' }}>
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
            ) : null}

            {/* Genre Remix Variants Panel */}
            {result && result.lyrics && lockedChorus && (
              <div className="glass-panel p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="section-title flex items-center gap-2">
                    <Blend size={13} /> Generate Genre Remixes
                  </h3>
                  {generatingVariants && (
                    <span className="text-xs flex items-center gap-1" style={{ color: '#d277ff' }}>
                      <Loader2 size={11} className="animate-spin" />
                      Generating {selectedRemixGenres.length} remix{selectedRemixGenres.length > 1 ? 'es' : ''}...
                    </span>
                  )}
                </div>

                {/* Genre chips */}
                <div className="flex flex-wrap gap-2">
                  {REMIX_GENRE_OPTIONS.map(genre => {
                    const isSelected = selectedRemixGenres.includes(genre)
                    return (
                      <button key={genre}
                        onClick={() => {
                          if (isSelected) {
                            setSelectedRemixGenres(prev => prev.filter(g => g !== genre))
                          } else if (selectedRemixGenres.length < 5) {
                            setSelectedRemixGenres(prev => [...prev, genre])
                          } else {
                            toast.error('Max 5 genres per request')
                          }
                        }}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                        style={isSelected
                          ? { background: 'rgba(210,119,255,0.2)', color: '#d277ff', border: '1px solid rgba(210,119,255,0.4)' }
                          : { background: 'rgba(255,255,255,0.04)', color: '#555', border: '1px solid rgba(255,255,255,0.08)' }
                        }>
                        {genre}
                      </button>
                    )
                  })}
                </div>

                <button
                  onClick={generateVariants}
                  disabled={generatingVariants || selectedRemixGenres.length === 0}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all disabled:opacity-40"
                  style={{ background: 'rgba(210,119,255,0.12)', color: '#d277ff', border: '1px solid rgba(210,119,255,0.25)' }}>
                  {generatingVariants
                    ? <><Loader2 size={12} className="animate-spin" /> Generating {selectedRemixGenres.length} remixes...</>
                    : <><Wand2 size={12} /> Generate {selectedRemixGenres.length > 0 ? `${selectedRemixGenres.length} ` : ''}Genre Remix{selectedRemixGenres.length !== 1 ? 'es' : ''}</>
                  }
                </button>

                {/* Remix variant result cards */}
                {genreRemixVariants.length > 0 && (
                  <div className="space-y-3 mt-1">
                    {genreRemixVariants.map((variant, i) => (
                      <div key={i} className="rounded-xl overflow-hidden"
                        style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        {/* Card header */}
                        <button
                          className="w-full flex items-center justify-between px-4 py-3 text-left transition-colors hover:bg-glass"
                          onClick={() => setExpandedVariant(expandedVariant === variant.genre ? null : variant.genre)}>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-md text-xs font-bold"
                              style={{ background: 'rgba(210,119,255,0.2)', color: '#d277ff' }}>
                              {variant.genre}
                            </span>
                            <span className="text-xs" style={{ color: '#888' }}>
                              {variant.bpm_target.toFixed(0)} BPM
                            </span>
                            <span className="text-xs" style={{ color: '#666' }}>
                              · cadence {(variant.cadence_match_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <ChevronDown size={14} className={`text-text-muted transition-transform ${expandedVariant === variant.genre ? 'rotate-180' : ''}`} />
                        </button>

                        {expandedVariant === variant.genre && (
                          <div className="px-4 pb-4 space-y-3">
                            <p className="text-xs" style={{ color: '#888' }}>{variant.style_notes}</p>
                            {variant.suno_tags && (
                              <p className="text-xs" style={{ color: '#555' }}>
                                Tags: {variant.suno_tags}
                              </p>
                            )}
                            <div className="whitespace-pre-wrap text-xs leading-loose text-text-secondary rounded-lg p-3"
                              style={{ background: 'rgba(255,255,255,0.02)' }}>
                              {variant.lyrics}
                            </div>
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(variant.lyrics)
                                toast.success(`${variant.genre} lyrics copied!`)
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                              style={{ background: 'rgba(195,244,0,0.08)', color: '#c3f400', border: '1px solid rgba(195,244,0,0.15)' }}>
                              Copy Lyrics
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* History */}
            {history.length > 1 && (
              <div className="glass-panel p-5 space-y-3 overflow-hidden">
                <h3 className="section-title">Session History ({history.length} tracks)</h3>
                {history.slice(1, 6).map((h, i) => (
                  <button key={i} onClick={() => { setResult(h); setActiveTab('lyrics') }}
                    className="w-full text-left px-4 py-3 rounded-xl text-sm text-text-secondary hover:bg-glass transition-all flex items-center gap-2 overflow-hidden">
                    <span className="text-text-muted text-xs flex-shrink-0">{h.timestamp}</span>
                    <span className="truncate">{h.theme || 'Untitled'}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <footer className="px-6 py-4 text-center text-xs text-text-muted"
          style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          AI Songwriting System V5 | Production Mode | Local + EC2
        </footer>
      </main>
    </div>
  )
}
