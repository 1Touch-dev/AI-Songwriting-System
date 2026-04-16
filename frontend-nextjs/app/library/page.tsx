'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Music2, Mic2, Radio, Search, ArrowLeft, Clock, ExternalLink, Trash2, X } from 'lucide-react'
import { getProjects, deleteProject } from '@/lib/api'
import type { Project } from '@/lib/types'

export default function LibraryPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [token, setToken] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('sonicflow_token')
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
    } catch {
      // silently ignore — show no error toast to keep UX clean
    } finally {
      setDeletingId(null)
    }
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
        artist: p.artist,
        theme: p.theme,
        lyrics: p.lyrics,
        title: p.title,
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
              <div className="text-2xl font-display font-bold" style={{ color: s.color }}>
                {s.value}
              </div>
              <div className="text-xs text-text-muted mt-1">{s.label}</div>
            </div>
          ))}
        </div>

        {/* Helper hint */}
        {!loading && !error && filtered.length > 0 && (
          <p className="text-xs text-text-muted mb-4 flex items-center gap-1.5">
            <ExternalLink size={11} /> Click any project to open it in Studio
          </p>
        )}

        {/* Content */}
        {loading ? (
          <div className="text-center py-20 text-text-muted">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            Loading projects...
          </div>
        ) : error ? (
          <div className="glass-panel p-8 text-center space-y-3">
            <p className="text-error text-sm">{error}</p>
            <p className="text-text-muted text-xs">
              Could not reach the API — check that the backend is running and port 8000 is open.
            </p>
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

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirmDelete) {
      onDelete()
      setConfirmDelete(false)
    } else {
      setConfirmDelete(true)
    }
  }

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    setConfirmDelete(false)
  }

  return (
    <div
      className="glass-panel-hover p-5 flex items-start gap-5 group cursor-pointer overflow-hidden relative"
      onClick={!confirmDelete ? onClick : undefined}
      style={{ opacity: deleting ? 0.4 : 1, transition: 'opacity 0.2s' }}
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
            <p className="text-sm text-text-muted mt-0.5 truncate">{p.theme}</p>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Clock size={12} className="text-text-muted" />
            <span className="text-xs text-text-muted whitespace-nowrap">{p.timestamp}</span>
          </div>
        </div>

        {/* Lyrics preview */}
        <p className="text-xs text-text-muted mt-2 leading-relaxed overflow-hidden"
          style={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
          }}>
          {p.lyrics.replace(/\[[^\]]+\]/g, '').trim().slice(0, 200)}
        </p>

        {/* Tags + actions row */}
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
          {p.duration_s > 0 && (
            <span className="px-2 py-0.5 rounded-md text-xs text-text-muted flex-shrink-0"
              style={{ background: 'rgba(255,255,255,0.05)' }}>
              {Math.floor(p.duration_s / 60)}:{String(Math.floor(p.duration_s % 60)).padStart(2,'0')}
            </span>
          )}

          {/* Open in Studio hint */}
          {!confirmDelete && (
            <span className="ml-auto text-xs flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-60 transition-opacity"
              style={{ color: '#8ff5ff' }}>
              <ExternalLink size={11} /> Open in Studio
            </span>
          )}

          {/* Delete controls */}
          <div className="flex items-center gap-1.5 flex-shrink-0 ml-auto" onClick={e => e.stopPropagation()}>
            {confirmDelete ? (
              <>
                <button
                  onClick={handleDeleteClick}
                  disabled={deleting}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all"
                  style={{ background: 'rgba(255,71,87,0.18)', color: '#ff4757', border: '1px solid rgba(255,71,87,0.35)' }}
                >
                  <Trash2 size={11} /> {deleting ? 'Deleting…' : 'Confirm'}
                </button>
                <button
                  onClick={handleCancelDelete}
                  className="flex items-center justify-center w-6 h-6 rounded-lg text-text-muted hover:text-text-primary transition-colors"
                  style={{ background: 'rgba(255,255,255,0.06)' }}
                >
                  <X size={12} />
                </button>
              </>
            ) : (
              <button
                onClick={handleDeleteClick}
                title="Delete project"
                className="flex items-center justify-center w-7 h-7 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-error transition-all"
                style={{ background: 'rgba(255,255,255,0.05)' }}
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
