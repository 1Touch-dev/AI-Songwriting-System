'use client'

import { useState, useRef, useEffect } from 'react'
import { Mic, Square, AlertCircle, Loader2 } from 'lucide-react'

interface Props {
  onRecordingComplete: (blob: Blob) => void
  accentColor?: string
}

export default function AudioRecorder({ onRecordingComplete, accentColor = '#d277ff' }: Props) {
  const [isRecording, setIsRecording] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [duration, setDuration] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [isSupported, setIsSupported] = useState(true)
  const [audioLevel, setAudioLevel] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    // Check browser support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setIsSupported(false)
      setError('Audio recording is not supported in this browser. Please use Chrome, Firefox, or Edge.')
    }

    return () => {
      cleanup()
    }
  }, [])

  const cleanup = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }

  const setupAudioLevelMonitoring = (stream: MediaStream) => {
    try {
      const audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser()
      const microphone = audioContext.createMediaStreamSource(stream)
      
      analyser.fftSize = 256
      microphone.connect(analyser)
      
      audioContextRef.current = audioContext
      analyserRef.current = analyser

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      
      const updateLevel = () => {
        if (!analyserRef.current) return
        
        analyserRef.current.getByteFrequencyData(dataArray)
        const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length
        setAudioLevel(Math.min(100, average / 1.28)) // Normalize to 0-100
        
        animationFrameRef.current = requestAnimationFrame(updateLevel)
      }
      
      updateLevel()
    } catch (err) {
      console.error('Audio level monitoring setup failed:', err)
    }
  }

  const startRecording = async () => {
    try {
      setError(null)
      
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        } 
      })
      
      streamRef.current = stream
      
      // Setup audio level monitoring
      setupAudioLevelMonitoring(stream)

      // Create MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm') 
        ? 'audio/webm' 
        : 'audio/mp4'
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: mimeType })
        onRecordingComplete(blob)
        cleanup()
        setIsRecording(false)
        setDuration(0)
        setAudioLevel(0)
      }

      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event)
        setError('Recording failed. Please try again.')
        cleanup()
        setIsRecording(false)
      }

      // Start recording
      mediaRecorder.start(100) // Collect data every 100ms
      setIsRecording(true)
      setDuration(0)

      // Start timer
      timerRef.current = setInterval(() => {
        setDuration(d => d + 1)
      }, 1000)

    } catch (err: unknown) {
      console.error('Failed to start recording:', err)
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setError('Microphone access denied. Please allow microphone access in your browser settings.')
        } else if (err.name === 'NotFoundError') {
          setError('No microphone found. Please connect a microphone and try again.')
        } else {
          setError(`Failed to start recording: ${err.message}`)
        }
      } else {
        setError('Failed to start recording. Please try again.')
      }
      cleanup()
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
  }

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${String(secs).padStart(2, '0')}`
  }

  if (!isSupported) {
    return (
      <div className="glass-panel p-4 border border-error/30">
        <div className="flex items-start gap-2">
          <AlertCircle size={16} className="text-error mt-0.5" />
          <div>
            <p className="text-xs text-error font-semibold mb-1">Browser Not Supported</p>
            <p className="text-xs text-text-muted">
              Audio recording requires Chrome 49+, Firefox 25+, or Edge 79+.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="glass-panel p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-display font-semibold uppercase tracking-widest"
          style={{ color: accentColor }}>
          {isRecording ? 'Recording' : 'Record Audio'}
        </span>
        {isRecording && (
          <span className="text-xs font-mono tabular-nums text-text-primary">
            {formatDuration(duration)}
          </span>
        )}
      </div>

      {/* Visual Feedback - Level Meter */}
      {isRecording && (
        <div className="space-y-1.5">
          <div 
            className="relative h-2 rounded-full overflow-hidden"
            style={{ background: 'rgba(255,255,255,0.08)' }}
          >
            <div
              className="absolute left-0 top-0 h-full rounded-full transition-all duration-100"
              style={{ 
                width: `${audioLevel}%`, 
                background: accentColor,
                boxShadow: `0 0 10px ${accentColor}80`
              }}
            />
          </div>
          <p className="text-xs text-text-muted text-center">
            {audioLevel > 10 ? 'Recording...' : 'Speak into microphone'}
          </p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="flex items-start gap-2 p-2 rounded-lg" 
          style={{ background: 'rgba(255,100,100,0.1)', borderLeft: '2px solid #ff6464' }}>
          <AlertCircle size={14} className="text-error mt-0.5 flex-shrink-0" />
          <p className="text-xs text-error leading-snug">{error}</p>
        </div>
      )}

      {/* Permission Explanation */}
      {!isRecording && !error && (
        <div className="p-3 rounded-lg" style={{ background: 'rgba(210,119,255,0.06)' }}>
          <p className="text-xs text-text-muted leading-relaxed">
            Click <strong style={{ color: accentColor }}>Start Recording</strong> to record audio from your microphone. 
            Your browser will request permission to access your microphone.
          </p>
        </div>
      )}

      {/* Controls */}
      <div className="flex gap-2">
        {!isRecording ? (
          <button
            onClick={startRecording}
            className="flex-1 py-3 rounded-xl font-semibold text-sm transition-all hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2"
            style={{ 
              background: accentColor,
              color: '#0e0e0e',
              boxShadow: `0 4px 16px ${accentColor}40`
            }}
          >
            <Mic size={16} />
            Start Recording
          </button>
        ) : (
          <button
            onClick={stopRecording}
            className="flex-1 py-3 rounded-xl font-semibold text-sm transition-all hover:scale-[1.02] active:scale-[0.98] flex items-center justify-center gap-2"
            style={{ 
              background: '#ff6464',
              color: '#fff',
              boxShadow: '0 4px 16px rgba(255,100,100,0.4)'
            }}
          >
            <Square size={16} fill="white" />
            Stop Recording
          </button>
        )}
      </div>

      {/* Recording Indicator */}
      {isRecording && (
        <div className="flex items-center justify-center gap-2 pt-1">
          <div 
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ background: '#ff6464' }}
          />
          <span className="text-xs text-text-muted">
            Recording in progress
          </span>
        </div>
      )}
    </div>
  )
}
