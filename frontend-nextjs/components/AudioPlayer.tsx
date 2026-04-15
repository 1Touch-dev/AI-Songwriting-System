'use client'

import { useState, useRef, useEffect } from 'react'
import { Play, Pause, Download, Volume2, VolumeX } from 'lucide-react'
import { b64ToAudioUrl, b64ToDownloadUrl } from '@/lib/api'

interface Props {
  b64: string
  label: string
  filename: string
  accentColor?: string
}

export default function AudioPlayer({ b64, label, filename, accentColor = '#8ff5ff' }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [muted, setMuted] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!b64) return
    const url = b64ToAudioUrl(b64)
    setAudioUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [b64])

  const toggle = () => {
    if (!audioRef.current) return
    if (playing) {
      audioRef.current.pause()
    } else {
      audioRef.current.play()
    }
    setPlaying(!playing)
  }

  const onTimeUpdate = () => {
    if (!audioRef.current) return
    setProgress(audioRef.current.currentTime / (audioRef.current.duration || 1))
  }

  const onLoadedMetadata = () => {
    if (!audioRef.current) return
    setDuration(audioRef.current.duration)
  }

  const onEnded = () => setPlaying(false)

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    audioRef.current.currentTime = pct * audioRef.current.duration
    setProgress(pct)
  }

  const toggleMute = () => {
    if (!audioRef.current) return
    audioRef.current.muted = !muted
    setMuted(!muted)
  }

  const formatTime = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  if (!audioUrl) return null

  return (
    <div className="glass-panel p-4 space-y-3">
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={onLoadedMetadata}
        onEnded={onEnded}
      />

      <div className="flex items-center justify-between">
        <span className="text-xs font-display font-semibold uppercase tracking-widest"
          style={{ color: accentColor }}>
          {label}
        </span>
        <button
          onClick={() => b64ToDownloadUrl(b64, filename)}
          className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors"
        >
          <Download size={13} />
          Download
        </button>
      </div>

      {/* Waveform / progress bar */}
      <div
        className="relative h-1.5 rounded-full cursor-pointer overflow-hidden"
        style={{ background: 'rgba(255,255,255,0.08)' }}
        onClick={seek}
      >
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all"
          style={{ width: `${progress * 100}%`, background: accentColor }}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          className="flex items-center justify-center w-9 h-9 rounded-full transition-all hover:scale-105"
          style={{ background: accentColor }}
        >
          {playing
            ? <Pause size={16} color="#0e0e0e" fill="#0e0e0e" />
            : <Play size={16} color="#0e0e0e" fill="#0e0e0e" className="ml-0.5" />
          }
        </button>

        <span className="text-xs text-text-muted font-mono tabular-nums">
          {formatTime((progress * duration))} / {formatTime(duration)}
        </span>

        <button onClick={toggleMute} className="ml-auto text-text-muted hover:text-text-primary transition-colors">
          {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
        </button>
      </div>
    </div>
  )
}
