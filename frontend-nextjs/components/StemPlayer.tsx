'use client'

import { useRef, useState, useEffect } from 'react'
import { Play, Pause, Download, Music2, Mic2, Drum, Activity } from 'lucide-react'

interface Stem {
  name: string
  url: string
}

interface StemPlayerProps {
  stems: Record<string, string>  // stem name → URL
}

const STEM_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  vocals:  { label: 'Vocals',       color: '#d277ff', icon: <Mic2 size={14} />   },
  drums:   { label: 'Drums',        color: '#8ff5ff', icon: <Drum size={14} />   },
  bass:    { label: 'Bass',         color: '#c3f400', icon: <Activity size={14} />},
  other:   { label: 'Instruments',  color: '#ffa502', icon: <Music2 size={14} /> },
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

export default function StemPlayer({ stems }: StemPlayerProps) {
  const entries = Object.entries(stems)
  if (entries.length === 0) return null

  // Order: vocals, drums, bass, other
  const ordered = ['vocals', 'drums', 'bass', 'other'].filter(n => stems[n])
  const rest = entries.filter(([n]) => !ordered.includes(n)).map(([n]) => n)

  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted">
        Click any stem to preview. Download as WAV for DAW use.
      </p>
      {[...ordered, ...rest].map(name => (
        <StemTrack key={name} name={name} url={stems[name]} />
      ))}
    </div>
  )
}
