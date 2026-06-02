'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft, Radio, RefreshCw, Plus, Trash2,
  CheckCircle, AlertCircle, Loader2, Database, Music2, ChevronDown, ChevronUp,
} from 'lucide-react'
import { adminListArtists, adminAddArtist, adminReindex, adminIndexStats } from '@/lib/api'

const SESSION_TOKEN_KEY = 'sonicflow_token'

type Artist = { name: string; songs_labeled: number; chunks_indexed: number; in_raw: boolean }
type IndexStats = { vectors_in_index: number; metadata_entries: number; index_size_mb: number }

export default function AdminPage() {
  const router = useRouter()
  const [token, setToken] = useState('')
  const [artists, setArtists] = useState<Artist[]>([])
  const [stats, setStats] = useState<IndexStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [reindexing, setReindexing] = useState(false)
  const [reindexMsg, setReindexMsg] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [addStatus, setAddStatus] = useState<'idle' | 'saving' | 'done' | 'error'>('idle')
  const [addMsg, setAddMsg] = useState('')

  // Add artist form state
  const [newArtist, setNewArtist] = useState('')
  const [newGenre, setNewGenre] = useState('')
  const [songs, setSongs] = useState<{ song: string; lyrics: string }[]>([{ song: '', lyrics: '' }])

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_TOKEN_KEY)
    if (!stored) { router.replace('/login'); return }
    setToken(stored)
    Promise.all([adminListArtists(stored), adminIndexStats(stored)])
      .then(([a, s]) => { setArtists(a.artists); setStats(s) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [router])

  const refresh = async () => {
    if (!token) return
    setLoading(true)
    try {
      const [a, s] = await Promise.all([adminListArtists(token), adminIndexStats(token)])
      setArtists(a.artists); setStats(s)
    } catch {}
    setLoading(false)
  }

  const handleReindex = async () => {
    setReindexing(true); setReindexMsg('')
    try {
      const r = await adminReindex(token)
      setReindexMsg(r.message || 'Full reindex started.')
    } catch (e: any) {
      setReindexMsg(e?.response?.data?.detail || 'Reindex failed.')
    }
    setReindexing(false)
  }

  const handleAddArtist = async () => {
    if (!newArtist.trim()) return
    const validSongs = songs.filter(s => s.song.trim() && s.lyrics.trim())
    if (!validSongs.length) { setAddMsg('Add at least one song with lyrics.'); setAddStatus('error'); return }
    setAddStatus('saving'); setAddMsg('')
    try {
      const r = await adminAddArtist(token, newArtist.trim(), newGenre.trim(), validSongs)
      setAddMsg(r.message || 'Artist added. Index updating in background.')
      setAddStatus('done')
      setNewArtist(''); setNewGenre(''); setSongs([{ song: '', lyrics: '' }])
      setTimeout(refresh, 3000)
    } catch (e: any) {
      setAddMsg(e?.response?.data?.detail || 'Failed to add artist.')
      setAddStatus('error')
    }
  }

  const addSongRow = () => setSongs(s => [...s, { song: '', lyrics: '' }])
  const removeSongRow = (i: number) => setSongs(s => s.filter((_, idx) => idx !== i))
  const updateSong = (i: number, field: 'song' | 'lyrics', val: string) =>
    setSongs(s => s.map((row, idx) => idx === i ? { ...row, [field]: val } : row))

  const handlePasteJSON = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value
    try {
      const parsed = JSON.parse(text)
      const arr: { song: string; lyrics: string }[] = Array.isArray(parsed)
        ? parsed.map((s: any) => ({ song: s.song || s.title || '', lyrics: s.lyrics || '' }))
        : []
      if (arr.length > 0) {
        setSongs(arr)
        setAddMsg(`Parsed ${arr.length} songs from JSON.`)
        setAddStatus('done')
      }
    } catch {}
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 flex items-center gap-4 px-6 py-4"
        style={{ background: 'rgba(14,14,14,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <Link href="/" className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all">
          <ArrowLeft size={16} />
        </Link>
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #ffa502, #ff6b35)' }}>
            <Database size={14} color="#0e0e0e" />
          </div>
          <h1 className="font-display font-bold text-lg text-text-primary">RAG Admin</h1>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <button onClick={refresh} disabled={loading}
            className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-glass transition-all">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
          <Link href="/library" className="btn-secondary py-2 px-4 text-sm">Library</Link>
          <Link href="/" className="btn-primary py-2 px-4 text-sm flex items-center gap-1.5">
            <Radio size={14} /> Studio
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6 space-y-6">

        {/* Index Stats */}
        {stats && (
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Vectors in Index', value: stats.vectors_in_index.toLocaleString(), color: '#8ff5ff' },
              { label: 'Metadata Entries', value: stats.metadata_entries.toLocaleString(), color: '#d277ff' },
              { label: 'Index Size', value: `${stats.index_size_mb} MB`, color: '#c3f400' },
            ].map(s => (
              <div key={s.label} className="glass-panel p-4 text-center">
                <div className="text-2xl font-display font-bold" style={{ color: s.color }}>{s.value}</div>
                <div className="text-xs text-text-muted mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="glass-panel p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold text-text-primary">Index Management</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleReindex}
              disabled={reindexing}
              className="btn-secondary flex items-center gap-2 text-sm py-2 px-4"
              style={{ borderColor: 'rgba(255,165,2,0.3)', color: '#ffa502' }}>
              {reindexing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Full Reindex
            </button>
            <button
              onClick={() => setShowAddForm(v => !v)}
              className="btn-primary flex items-center gap-2 text-sm py-2 px-4">
              <Plus size={14} /> Add Artist
              {showAddForm ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
          {reindexMsg && (
            <p className="text-xs" style={{ color: '#ffa502' }}>{reindexMsg}</p>
          )}
        </div>

        {/* Add Artist Form */}
        {showAddForm && (
          <div className="glass-panel p-5 space-y-4">
            <h2 className="font-display font-semibold text-text-primary">Add New Artist to RAG</h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-text-muted block mb-1">Artist Name *</label>
                <input className="input-field w-full text-sm" placeholder="e.g. The Weeknd"
                  value={newArtist} onChange={e => setNewArtist(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-text-muted block mb-1">Genre (optional)</label>
                <input className="input-field w-full text-sm" placeholder="e.g. r&b"
                  value={newGenre} onChange={e => setNewGenre(e.target.value)} />
              </div>
            </div>

            {/* Paste JSON shortcut */}
            <div>
              <label className="text-xs text-text-muted block mb-1">
                Paste JSON array (shortcut) — format: <span className="font-mono">[{'{'}song, lyrics{'}'}]</span>
              </label>
              <textarea className="input-field w-full text-xs font-mono" rows={3}
                placeholder='[{"song": "Blinding Lights", "lyrics": "..."}, ...]'
                onChange={handlePasteJSON} />
            </div>

            {/* Song rows */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-muted">Songs ({songs.length})</span>
                <button onClick={addSongRow} className="text-xs flex items-center gap-1 text-text-muted hover:text-text-primary">
                  <Plus size={11} /> Add song
                </button>
              </div>
              {songs.map((s, i) => (
                <div key={i} className="rounded-xl p-3 space-y-2" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div className="flex gap-2 items-center">
                    <input className="input-field flex-1 text-sm" placeholder={`Song title ${i + 1}`}
                      value={s.song} onChange={e => updateSong(i, 'song', e.target.value)} />
                    {songs.length > 1 && (
                      <button onClick={() => removeSongRow(i)}
                        className="p-1.5 rounded-lg text-text-muted hover:text-error transition-colors">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                  <textarea className="input-field w-full text-xs font-body" rows={4}
                    placeholder="Paste full lyrics here..."
                    value={s.lyrics} onChange={e => updateSong(i, 'lyrics', e.target.value)} />
                </div>
              ))}
            </div>

            {addMsg && (
              <div className="flex items-center gap-2 text-xs"
                style={{ color: addStatus === 'error' ? '#ff4757' : '#c3f400' }}>
                {addStatus === 'error' ? <AlertCircle size={13} /> : <CheckCircle size={13} />}
                {addMsg}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={handleAddArtist} disabled={addStatus === 'saving'}
                className="btn-primary flex items-center gap-2 text-sm py-2 px-5">
                {addStatus === 'saving' ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                {addStatus === 'saving' ? 'Saving…' : 'Add & Index Artist'}
              </button>
              <button onClick={() => { setShowAddForm(false); setAddStatus('idle'); setAddMsg('') }}
                className="btn-secondary text-sm py-2 px-4">Cancel</button>
            </div>
          </div>
        )}

        {/* Artist List */}
        <div className="glass-panel overflow-hidden">
          <div className="p-5 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
            <h2 className="font-display font-semibold text-text-primary">
              Trained Artists ({artists.length})
            </h2>
          </div>
          {loading ? (
            <div className="p-8 text-center">
              <Loader2 size={20} className="animate-spin mx-auto text-text-muted" />
            </div>
          ) : artists.length === 0 ? (
            <div className="p-8 text-center text-text-muted text-sm">No artists in corpus yet.</div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
              {artists.map(a => (
                <div key={a.name} className="px-5 py-3 flex items-center gap-4">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(143,245,255,0.06)' }}>
                    <Music2 size={14} style={{ color: '#8ff5ff', opacity: 0.6 }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-text-primary truncate">{a.name}</p>
                    <p className="text-xs text-text-muted">
                      {a.songs_labeled} songs labeled · {a.chunks_indexed} chunks indexed
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {a.chunks_indexed > 0 ? (
                      <span className="text-xs px-2 py-0.5 rounded-full"
                        style={{ background: 'rgba(195,244,0,0.08)', color: '#c3f400' }}>
                        <CheckCircle size={9} className="inline mr-1" />Indexed
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full"
                        style={{ background: 'rgba(255,165,2,0.08)', color: '#ffa502' }}>
                        Not indexed
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
