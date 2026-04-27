'use client'

import { useRef, useState, useEffect } from 'react'
import { Play, Pause, Download, Music2, Mic2, Drum, Activity, Archive, Gauge, Music } from 'lucide-react'
import { BASE_URL } from '@/lib/api'

interface Stem {
  name: string
  url: string
}

interface AudioMetadata {
  bpm: number
  key: string
}

interface StemPlayerProps {
  stems: Record<string, string>  // stem name → URL
  jobId?: string
  audioMetadata?: AudioMetadata | null
}

const STEM_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  vocals:  { label: 'Vocals (AI)',             color: '#d277ff', icon: <Mic2 size={14} />   },
  drums:   { label: 'Drums',                   color: '#8ff5ff', icon: <Drum size={14} />   },
  bass:    { label: 'Bass',                    color: '#c3f400', icon: <Activity size={14} />},
  other:   { label: 'Instrumental (Extracted)', color: '#ffa502', icon: <Music2 size={14} /> },
}

function StemTrack({ name, url }: Stem) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)

  const cfg = STEM_CONFIG[name] ?? { label: name, color: '#888', icon: <Music2 size={14} /> }

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTimeUpdate = () => {
      if (audio.duration) setProgress(audio.currentTime / audio.duration)
    }
    const onLoaded = () => setDuration(audio.duration)
    const onEnded  = () => { setPlaying(false); setProgress(0) }
    audio.addEventListener('timeupdate', onTimeUpdate)
    audio.addEventListener('loadedmetadata', onLoaded)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate)
      audio.removeEventListener('loadedmetadata', onLoaded)
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  const toggle = () => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) { audio.pause(); setPlaying(false) }
    else { audio.play(); setPlaying(true) }
  }

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const audio = audioRef.current
    if (!audio) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    audio.currentTime = ratio * audio.duration
  }

  const fmt = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  const download = () => {
    const a = document.createElement('a')
    a.href = url
    a.download = `${name}.wav`
    a.click()
  }

  return (
    <div className="flex items-center gap-3 p-3 rounded-xl"
      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>

      <audio ref={audioRef} src={url} preload="metadata" />

      {/* Icon + label */}
      <div className="flex items-center gap-2 w-28 flex-shrink-0">
        <div className="w-6 h-6 rounded-md flex items-center justify-center"
          style={{ background: `${cfg.color}22`, color: cfg.color }}>
          {cfg.icon}
        </div>
        <span className="text-xs font-medium text-text-primary">{cfg.label}</span>
      </div>

      {/* Play / Pause */}
      <button onClick={toggle}
        className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center transition-all"
        style={{ background: `${cfg.color}22`, color: cfg.color }}>
        {playing ? <Pause size={13} /> : <Play size={13} />}
      </button>

      {/* Progress bar */}
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full cursor-pointer"
          style={{ background: 'rgba(255,255,255,0.10)' }}
          onClick={seek}>
          <div className="h-full rounded-full transition-all"
            style={{ width: `${progress * 100}%`, background: cfg.color }} />
        </div>
        <span className="text-xs text-text-muted flex-shrink-0 w-10">
          {duration > 0 ? fmt(duration * progress) : '--:--'}
        </span>
      </div>

      {/* Download */}
      <button onClick={download}
        title={`Download ${cfg.label}`}
        className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
        style={{ background: 'rgba(255,255,255,0.05)' }}>
        <Download size={12} />
      </button>
    </div>
  )
}

export default function StemPlayer({ stems, jobId, audioMetadata }: StemPlayerProps) {
  const entries = Object.entries(stems)
  if (entries.length === 0) return null

  // Order: vocals, drums, bass, other
  const ordered = ['vocals', 'drums', 'bass', 'other'].filter(n => stems[n])
  const rest = entries.filter(([n]) => !ordered.includes(n)).map(([n]) => n)

  const downloadZip = () => {
    if (!jobId) return
    const a = document.createElement('a')
    a.href = `${BASE_URL}/stems/${jobId}/download-zip`
    a.download = `stems_${jobId}.zip`
    a.click()
  }

  return (
    <div className="space-y-3">
      {/* Metadata chips */}
      {audioMetadata && (audioMetadata.bpm > 0 || audioMetadata.key !== 'Unknown') && (
        <div className="flex items-center gap-2 flex-wrap">
          {audioMetadata.bpm > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: 'rgba(143,245,255,0.10)', color: '#8ff5ff', border: '1px solid rgba(143,245,255,0.2)' }}>
              <Gauge size={11} />
              {audioMetadata.bpm} BPM
            </div>
          )}
          {audioMetadata.key && audioMetadata.key !== 'Unknown' && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: 'rgba(210,119,255,0.10)', color: '#d277ff', border: '1px solid rgba(210,119,255,0.2)' }}>
              <Music size={11} />
              {audioMetadata.key}
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-text-muted">
        All stems normalized to -14 LUFS. Download individual WAVs or grab all at once for Logic Pro, Ableton, or FL Studio.
      </p>

      {[...ordered, ...rest].map(name => (
        <StemTrack key={name} name={name} url={stems[name]} />
      ))}

      {/* ZIP download */}
      {jobId && (
        <button
          onClick={downloadZip}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold transition-all hover:opacity-90 mt-1"
          style={{ background: 'rgba(195,244,0,0.10)', color: '#c3f400', border: '1px solid rgba(195,244,0,0.25)' }}>
          <Archive size={13} />
          Download All Stems (ZIP)
        </button>
      )}
    </div>
  )
}
