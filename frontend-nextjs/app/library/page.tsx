'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Music2, Mic2, Radio, Search, ArrowLeft, Clock } from 'lucide-react'
import { getProjects } from '@/lib/api'
import type { Project } from '@/lib/types'

export default function LibraryPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('sonicflow_token')
    if (!token) { router.replace('/login'); return }
    getProjects(token)
      .then(setProjects)
      .catch(e => setError(e?.response?.data?.detail || e.message || 'Network error'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = projects.filter(p =>
    !search ||
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    p.artist.toLowerCase().includes(search.toLowerCase()) ||
    p.theme.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-30 flex items-center gap-4 px-6 py-4"
        style={{ background: 'rgba(14,14,14,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <Link href="/"
          className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all">
          <ArrowLeft size={16} />
        </Link>
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #8ff5ff, #d277ff)' }}>
            <Music2 size={14} color="#0e0e0e" />
          </div>
          <h1 className="font-display font-bold text-lg text-text-primary">Project Library</h1>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <div className="relative">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              className="input-field pl-9 w-56 py-2 text-sm"
              placeholder="Search projects..."
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
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ProjectCard({ project: p }: { project: Project }) {
  return (
    <div className="glass-panel-hover p-5 flex items-start gap-5">
      {/* Icon */}
      <div className="w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center"
        style={{ background: 'rgba(143,245,255,0.08)' }}>
        <Music2 size={20} style={{ color: '#8ff5ff', opacity: 0.7 }} />
      </div>

      {/* Meta */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-display font-semibold text-base text-text-primary truncate">
              {p.title}
            </h3>
            <p className="text-sm text-text-muted mt-0.5 truncate">
              {p.artist} — {p.theme}
            </p>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Clock size={12} className="text-text-muted" />
            <span className="text-xs text-text-muted">{p.timestamp}</span>
          </div>
        </div>

        {/* Lyrics preview */}
        <p className="text-xs text-text-muted mt-2 line-clamp-2 leading-relaxed">
          {p.lyrics.slice(0, 160)}...
        </p>

        {/* Tags + Actions */}
        <div className="flex items-center gap-3 mt-3">
          <div className="flex gap-1.5">
            {p.has_voice && (
              <span className="px-2 py-0.5 rounded-md text-xs flex items-center gap-1"
                style={{ background: 'rgba(210,119,255,0.1)', color: '#d277ff' }}>
                <Mic2 size={10} /> Voice
              </span>
            )}
            {p.has_music && (
              <span className="px-2 py-0.5 rounded-md text-xs flex items-center gap-1"
                style={{ background: 'rgba(195,244,0,0.1)', color: '#c3f400' }}>
                <Music2 size={10} /> Music
              </span>
            )}
            {p.duration_s > 0 && (
              <span className="px-2 py-0.5 rounded-md text-xs text-text-muted"
                style={{ background: 'rgba(255,255,255,0.05)' }}>
                {Math.floor(p.duration_s / 60)}:{String(Math.floor(p.duration_s % 60)).padStart(2,'0')}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
