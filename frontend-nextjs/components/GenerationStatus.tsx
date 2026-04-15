'use client'

import { CheckCircle, Circle, Loader2 } from 'lucide-react'

export type StepStatus = 'pending' | 'active' | 'done' | 'failed'

export interface PipelineStep {
  id: string
  label: string
  status: StepStatus
  detail?: string
}

interface Props {
  steps: PipelineStep[]
  overallStatus: 'idle' | 'running' | 'complete' | 'error'
}

const STEP_ICONS: Record<string, string> = {
  lyrics: '🧠',
  voice: '🎤',
  music: '🎵',
  mix: '🎚️',
  analysis: '🔍',
}

export default function GenerationStatus({ steps, overallStatus }: Props) {
  if (overallStatus === 'idle') return null

  return (
    <div className="glass-panel p-5 space-y-3 animate-fade-in">
      <div className="flex items-center gap-2 mb-4">
        {overallStatus === 'running' && (
          <Loader2 size={16} className="animate-spin" style={{ color: '#8ff5ff' }} />
        )}
        {overallStatus === 'complete' && (
          <CheckCircle size={16} style={{ color: '#2ed573' }} />
        )}
        {overallStatus === 'error' && (
          <span style={{ color: '#ff4757', fontSize: 16 }}>✕</span>
        )}
        <span className="font-display font-semibold text-sm uppercase tracking-widest"
          style={{
            color: overallStatus === 'complete' ? '#2ed573'
                 : overallStatus === 'error' ? '#ff4757'
                 : '#8ff5ff'
          }}>
          {overallStatus === 'running' ? 'Production Pipeline Running...'
           : overallStatus === 'complete' ? 'Production Complete'
           : 'Production Failed — See Error Below'}
        </span>
      </div>

      {steps.map((step) => (
        <div key={step.id} className="flex items-start gap-3">
          <div className="mt-0.5 flex-shrink-0">
            {step.status === 'active' && (
              <Loader2 size={14} className="animate-spin" style={{ color: '#8ff5ff' }} />
            )}
            {step.status === 'done' && (
              <CheckCircle size={14} style={{ color: '#2ed573' }} />
            )}
            {step.status === 'failed' && (
              <Circle size={14} style={{ color: '#ff4757' }} />
            )}
            {step.status === 'pending' && (
              <Circle size={14} style={{ color: '#404040' }} />
            )}
          </div>
          <div>
            <span className={`text-sm font-medium ${
              step.status === 'active' ? 'text-text-primary' :
              step.status === 'done' ? 'text-text-secondary' :
              step.status === 'failed' ? 'text-error' :
              'text-text-muted'
            }`}>
              {STEP_ICONS[step.id] ?? '⚡'} {step.label}
            </span>
            {step.detail && (
              <p className="text-xs text-text-muted mt-0.5">{step.detail}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
