'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Music2, Mic2, Radio, Search, ArrowLeft, Clock,
  ExternalLink, Trash2, X, Play, Pause, Download,
  ChevronDown, ChevronUp, Layers, Zap,
} from 'lucide-react'
import { getProjects, deleteProject, audioUrl } from '@/lib/api'
import type { Project } from '@/lib/types'

const SESSION_TOKEN_KEY = 'sonicflow_token'

function MiniPlayer({ url, label, color }: { url: string; label: string; color: string }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onTime = () => { if (a.duration) setProgress(a.currentTime / a.duration) }
    const onLoad = () => setDuration(a.duration)
    const onEnd  = () => { setPlaying(false); setProgress(0) }
    a.addEventListener('timeupdate', onTime)
    a.addEventListener('loadedmetadata', onLoad)
    a.addEventListener('ended', onEnd)
    return () => {
      a.removeEventListener('timeupdate', onTime)
      a.removeEventListener('loadedmetadata', onLoad)
      a.removeEventListener('ended', onEnd)
    }
  }, [])

  const toggle = () => {
    const a = audioRef.current
    if (!a) return
    if (playing) { a.pause(); setPlaying(false) } else { a.play(); setPlaying(true) }
  }

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const a = audioRef.current
    if (!a) return
    const r = e.currentTarget.getBoundingClientRect()
    a.currentTime = ((e.clientX - r.left) / r.width) * a.duration
  }

  const fmt = (s: number) => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`

  const download = () => {
    const a = document.createElement('a')
    a.href = url
    a.download = label.toLowerCase().replace(/\s+/g,'_') + '.mp3'
    a.click()
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
      <audio ref={audioRef} src={url} preload="none" />

      <button onClick={toggle}
        className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center transition-all"
        style={{ background: `${color}22`, color }}>
        {playing ? <Pause size={11} /> : <Play size={11} />}
      </button>

      <span className="text-xs flex-shrink-0 w-24 truncate" style={{ color }}>{label}</span>

      <div className="flex-1 h-1 rounded-full cursor-pointer"
        style={{ background: 'rgba(255,255,255,0.08)' }}
        onClick={seek}>
        <div className="h-full rounded-full transition-all" style={{ width: `${progress * 100}%`, background: color }} />
      </div>

      <span className="text-xs text-text-muted flex-shrink-0 w-8 text-right">
        {duration > 0 ? fmt(duration * progress) : '--:--'}
      </span>

      <button onClick={download} title="Download"
        className="flex-shrink-0 w-6 h-6 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
        style={{ background: 'rgba(255,255,255,0.04)' }}>
        <Download size={10} />
      </button>
    </div>
  )
}

export default function LibraryPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [token, setToken] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_TOKEN_KEY)
    if (!stored) { router.replace('/login'); return }
    setToken(stored)
    getProjects(stored)
      .then(setProjects)
      .catch(e => setError(e?.response?.data?.detail || e.message || 'Network error'))
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id: string) => {
    setDeletingId(id)
    try {
      await deleteProject(token, id)
      setProjects(prev => prev.filter(p => p.id !== id))
    } catch { /* ignore */ }
    finally { setDeletingId(null) }
  }

  const filtered = projects.filter(p =>
    !search ||
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    p.artist.toLowerCase().includes(search.toLowerCase()) ||
    p.theme.toLowerCase().includes(search.toLowerCase())
  )

  const openInStudio = (p: Project) => {
    try {
      localStorage.setItem('sonicflow_open_project', JSON.stringify({
        artist:           p.artist,
        theme:            p.theme,
        lyrics:           p.lyrics,
        title:            p.title,
        language:         p.language,
        bars:             p.bars,
        structure:        p.structure,
        gen_mode:         p.gen_mode,
        perspective_mode: p.perspective_mode,
        gender:           p.gender,
        style_strength:   p.style_strength,
        temperature:      p.temperature,
        chorus_strict:    p.chorus_strict,
        producer_mode:    p.producer_mode,
        section_mode:     p.section_mode,
        ref_lyrics:       p.ref_lyrics,
      }))
    } catch { /* storage full */ }
    router.push('/')
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-30 flex items-center gap-4 px-6 py-4"
        style={{ background: 'rgba(14,14,14,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <Link href="/"
          className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all">
          <ArrowLeft size={16} />
        </Link>
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #8ff5ff, #d277ff)' }}>
            <Music2 size={14} color="#0e0e0e" />
          </div>
          <h1 className="font-display font-bold text-lg text-text-primary truncate">Project Library</h1>
        </div>
        <div className="ml-auto flex items-center gap-3 flex-shrink-0">
          <div className="relative">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              className="input-field pl-9 w-48 py-2 text-sm"
              placeholder="Search..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <Link href="/" className="btn-primary py-2 px-4 text-sm flex items-center gap-1.5">
            <Radio size={14} /> Studio
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6">
        {/* Stats bar */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: 'Total Tracks', value: projects.length, color: '#8ff5ff' },
            { label: 'With Voice', value: projects.filter(p => p.has_voice).length, color: '#d277ff' },
            { label: 'With Music', value: projects.filter(p => p.has_music).length, color: '#c3f400' },
          ].map(s => (
            <div key={s.label} className="glass-panel p-4 text-center">
              <div className="text-2xl font-display font-bold" style={{ color: s.color }}>{s.value}</div>
              <div className="text-xs text-text-muted mt-1">{s.label}</div>
            </div>
          ))}
        </div>

        {!loading && !error && filtered.length > 0 && (
          <p className="text-xs text-text-muted mb-4 flex items-center gap-1.5">
            <ExternalLink size={11} /> Click any project to open it in Studio
          </p>
        )}

        {loading ? (
          <div className="text-center py-20 text-text-muted">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            Loading projects...
          </div>
        ) : error ? (
          <div className="glass-panel p-8 text-center space-y-3">
            <p className="text-error text-sm">{error}</p>
            <p className="text-text-muted text-xs">Could not reach the API — check backend is running.</p>
            <Link href="/" className="btn-secondary inline-flex items-center gap-2 mt-2">
              <ArrowLeft size={14} /> Back to Studio
            </Link>
          </div>
        ) : filtered.length === 0 ? (
          <div className="glass-panel p-12 text-center space-y-4">
            <Music2 size={40} className="mx-auto opacity-20" />
            <p className="text-text-muted">
              {search ? 'No projects match your search.' : 'No projects yet. Generate your first track in the Studio.'}
            </p>
            <Link href="/" className="btn-primary inline-flex items-center gap-2">
              <Radio size={15} /> Open Studio
            </Link>
          </div>
        ) : (
          <div className="grid gap-4">
            {filtered.map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                onClick={() => openInStudio(p)}
                onDelete={() => handleDelete(p.id)}
                deleting={deletingId === p.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ProjectCard({
  project: p,
  onClick,
  onDelete,
  deleting,
}: {
  project: Project
  onClick: () => void
  onDelete: () => void
  deleting: boolean
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const voiceAudio = audioUrl(p.voice_url)
  const musicAudio = audioUrl(p.music_url)
  const mixAudio   = audioUrl(p.mix_url)
  const hasAudio   = !!(voiceAudio || musicAudio || mixAudio)

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirmDelete) { onDelete(); setConfirmDelete(false) }
    else setConfirmDelete(true)
  }

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    setConfirmDelete(false)
  }

  return (
    <div
      className="glass-panel-hover overflow-hidden group"
      style={{ opacity: deleting ? 0.4 : 1, transition: 'opacity 0.2s' }}
    >
      {/* Main row — click to open in Studio */}
      <div
        className="p-5 flex items-start gap-5 cursor-pointer"
        onClick={!confirmDelete ? onClick : undefined}
      >
        {/* Icon */}
        <div className="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center"
          style={{ background: 'rgba(143,245,255,0.08)' }}>
          <Music2 size={20} style={{ color: '#8ff5ff', opacity: 0.7 }} />
        </div>

        {/* Meta */}
        <div className="flex-1 min-w-0 overflow-hidden">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 overflow-hidden">
              <h3 className="font-display font-semibold text-base text-text-primary truncate group-hover:text-white transition-colors">
                {p.artist} — {p.title}
              </h3>
              {/* Input metadata row */}
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {p.language && p.language !== 'English' && (
                  <span className="text-xs px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(210,119,255,0.1)', color: '#d277ff' }}>{p.language}</span>
                )}
                {p.bars && (
                  <span className="text-xs text-text-muted">{p.bars} bars</span>
                )}
                {p.structure && (
                  <span className="text-xs text-text-muted truncate max-w-36">{p.structure}</span>
                )}
                {p.producer_mode && (
                  <span className="text-xs px-1.5 py-0.5 rounded flex items-center gap-1"
                    style={{ background: 'rgba(255,165,2,0.1)', color: '#ffa502' }}>
                    <Layers size={9} /> Producer
                  </span>
                )}
                {p.chorus_strict && (
                  <span className="text-xs px-1.5 py-0.5 rounded"
                    style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff' }}>Hook Mode</span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <Clock size={12} className="text-text-muted" />
              <span className="text-xs text-text-muted whitespace-nowrap">{p.timestamp}</span>
            </div>
          </div>

          {/* Lyrics preview */}
          <p className="text-xs text-text-muted mt-2 leading-relaxed"
            style={{
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}>
            {p.lyrics.replace(/\[[^\]]+\]/g, '').trim().slice(0, 200)}
          </p>

          {/* Tags + actions */}
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            {p.has_voice && (
              <span className="px-2 py-0.5 rounded-md text-xs flex items-center gap-1 flex-shrink-0"
                style={{ background: 'rgba(210,119,255,0.1)', color: '#d277ff' }}>
                <Mic2 size={10} /> Voice
              </span>
            )}
            {p.has_music && (
              <span className="px-2 py-0.5 rounded-md text-xs flex items-center gap-1 flex-shrink-0"
                style={{ background: 'rgba(195,244,0,0.1)', color: '#c3f400' }}>
                <Music2 size={10} /> Music
              </span>
            )}
            {p.has_mix && (
              <span className="px-2 py-0.5 rounded-md text-xs flex items-center gap-1 flex-shrink-0"
                style={{ background: 'rgba(255,165,2,0.1)', color: '#ffa502' }}>
                🎛️ Mix
              </span>
            )}
            {p.duration_s > 0 && (
              <span className="px-2 py-0.5 rounded-md text-xs text-text-muted flex-shrink-0"
                style={{ background: 'rgba(255,255,255,0.05)' }}>
                {Math.floor(p.duration_s / 60)}:{String(Math.floor(p.duration_s % 60)).padStart(2,'0')}
              </span>
            )}

            {hasAudio && (
              <button
                onClick={e => { e.stopPropagation(); setExpanded(o => !o) }}
                className="ml-1 flex items-center gap-1 text-xs px-2 py-0.5 rounded-lg transition-all"
                style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff' }}>
                {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                {expanded ? 'Hide Audio' : 'Play Audio'}
              </button>
            )}

            {!confirmDelete && (
              <span className="ml-auto text-xs flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-60 transition-opacity"
                style={{ color: '#8ff5ff' }}>
                <ExternalLink size={11} /> Open in Studio
              </span>
            )}

            <div className="flex items-center gap-1.5 flex-shrink-0 ml-auto" onClick={e => e.stopPropagation()}>
              {confirmDelete ? (
                <>
                  <button onClick={handleDeleteClick} disabled={deleting}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all"
                    style={{ background: 'rgba(255,71,87,0.18)', color: '#ff4757', border: '1px solid rgba(255,71,87,0.35)' }}>
                    <Trash2 size={11} /> {deleting ? 'Deleting…' : 'Confirm'}
                  </button>
                  <button onClick={handleCancelDelete}
                    className="flex items-center justify-center w-6 h-6 rounded-lg text-text-muted hover:text-text-primary transition-colors"
                    style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <X size={12} />
                  </button>
                </>
              ) : (
                <button onClick={handleDeleteClick} title="Delete project"
                  className="flex items-center justify-center w-7 h-7 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-error transition-all"
                  style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Expanded audio + analysis section */}
      {expanded && (
        <div className="px-5 pb-5 space-y-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.04)' }}
          onClick={e => e.stopPropagation()}>
          <div className="pt-3 space-y-2">
            {voiceAudio && (
              <MiniPlayer url={voiceAudio} label="Vocal Output" color="#d277ff" />
            )}
            {musicAudio && (
              <MiniPlayer url={musicAudio} label="Full Song" color="#c3f400" />
            )}
            {mixAudio && (
              <MiniPlayer url={mixAudio} label="Final Mix" color="#ffa502" />
            )}
          </div>

          {/* Analysis preview */}
          {p.analysis && Object.keys(p.analysis).length > 0 && (
            <div className="mt-3 p-3 rounded-xl space-y-1.5"
              style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#8ff5ff' }}>AI Analysis</p>
              {(['theme','tone','rhyme_scheme','narrative_perspective'] as const).map(k => {
                const val = (p.analysis as Record<string, unknown>)[k]
                if (!val) return null
                return (
                  <div key={k} className="flex gap-2 text-xs">
                    <span className="text-text-muted capitalize flex-shrink-0 w-28">{k.replace(/_/g,' ')}</span>
                    <span className="text-text-secondary">{String(val)}</span>
                  </div>
                )
              })}
            </div>
          )}

          <button
            onClick={() => onClick()}
            className="w-full mt-2 py-2.5 rounded-xl text-xs font-semibold transition-all"
            style={{ background: 'rgba(143,245,255,0.08)', color: '#8ff5ff', border: '1px solid rgba(143,245,255,0.12)' }}>
            Open in Studio →
          </button>
        </div>
      )}
    </div>
  )
}
