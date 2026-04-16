import { useState, useCallback } from 'react'
import { NVIS } from '../theme'
import type { PipelineStep, ReextractResult } from '../types'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PIPELINE_STEPS: string[] = [
  'Extract Spans',
  'Classify Blocks',
  'Rebuild Sections',
  'Extract Tables',
  'Upsert to Memory',
]

function stepStatusIcon(status: PipelineStep['status']): string {
  switch (status) {
    case 'pending':
      return '\u25CB'  // ○
    case 'running':
      return '\u27F3'  // ⟳
    case 'done':
      return '\u2713'  // ✓
    case 'error':
      return '\u2717'  // ✗
    default:
      return '\u25CB'
  }
}

function stepStatusColor(status: PipelineStep['status']): string {
  switch (status) {
    case 'pending':
      return NVIS.dim
    case 'running':
      return NVIS.accent
    case 'done':
      return '#15803d'
    case 'error':
      return '#dc2626'
    default:
      return NVIS.dim
  }
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SpotReextractProps {
  section?: unknown
  sectionId?: string
  blockCount: number
  tableCount: number
  onAccept: (result: ReextractResult) => void
  onCancel: () => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SpotReextract({
  section: _section,
  sectionId,
  blockCount,
  tableCount,
  onAccept,
  onCancel,
}: SpotReextractProps) {
  const [scope, setScope] = useState<'section' | 'page'>('section')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<PipelineStep[]>(
    PIPELINE_STEPS.map((name) => ({ name, status: 'pending' }))
  )
  const [result, setResult] = useState<ReextractResult | null>(null)

  // Estimated impact
  const estimatedTime = (blockCount * 0.15 + tableCount * 0.8).toFixed(1)

  // Simulate pipeline execution
  const runPipeline = useCallback(async () => {
    setRunning(true)
    setResult(null)

    const newSteps: PipelineStep[] = PIPELINE_STEPS.map((name) => ({
      name,
      status: 'pending' as const,
    }))
    setSteps(newSteps)

    for (let i = 0; i < PIPELINE_STEPS.length; i++) {
      // Set current step to running
      newSteps[i] = { ...newSteps[i], status: 'running' }
      setSteps([...newSteps])

      // Simulate delay
      await new Promise((resolve) => setTimeout(resolve, 300 + Math.random() * 400))

      // Set step to done
      const duration = Math.round(200 + Math.random() * 600)
      newSteps[i] = { ...newSteps[i], status: 'done', durationMs: duration }
      setSteps([...newSteps])
    }

    // Simulate result
    const mockResult: ReextractResult = {
      scope,
      targetId: sectionId ?? 'unknown',
      blocksAdded: Math.floor(Math.random() * 3),
      blocksRemoved: Math.floor(Math.random() * 2),
      blocksModified: Math.floor(Math.random() * 5) + 1,
      confidenceDelta: parseFloat((Math.random() * 0.15 + 0.02).toFixed(3)),
      pipelineSteps: newSteps,
    }
    setResult(mockResult)
    setRunning(false)
  }, [scope, sectionId])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !running) onCancel()
      }}
    >
      <div
        style={{
          width: '480px',
          maxHeight: '80vh',
          backgroundColor: NVIS.surface,
          border: `1px solid ${NVIS.borderSolid}`,
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '14px 16px',
            borderBottom: `1px solid ${NVIS.borderSolid}`,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <span
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: NVIS.white,
            }}
          >
            Spot Re-extract
          </span>
          {sectionId && (
            <span
              style={{
                fontSize: '10px',
                color: NVIS.accent,
                padding: '2px 6px',
                borderRadius: '3px',
                backgroundColor: `${NVIS.accent}14`,
                border: `1px solid ${NVIS.accent}30`,
              }}
            >
              \u00A7 {sectionId}
            </span>
          )}
        </div>

        {/* Body */}
        <div style={{ padding: '16px', flex: 1, overflowY: 'auto' }}>
          {/* Scope selector */}
          <div style={{ marginBottom: '14px' }}>
            <div
              style={{
                fontSize: '9px',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: NVIS.dim,
                marginBottom: '6px',
              }}
            >
              Scope
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              {(['section', 'page'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setScope(s)}
                  disabled={running}
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '11px',
                    padding: '4px 12px',
                    borderRadius: '3px',
                    border:
                      scope === s
                        ? `1px solid ${NVIS.accent}`
                        : `1px solid ${NVIS.borderSolid}`,
                    backgroundColor:
                      scope === s ? `${NVIS.accent}14` : NVIS.surface2,
                    color: scope === s ? NVIS.accent : NVIS.dim,
                    cursor: running ? 'not-allowed' : 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Impact preview */}
          <div
            style={{
              padding: '10px 12px',
              backgroundColor: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: '4px',
              marginBottom: '14px',
              fontSize: '11px',
              color: NVIS.dim,
            }}
          >
            <span style={{ color: NVIS.white, fontWeight: 600 }}>
              {blockCount} blocks
            </span>
            {', '}
            <span style={{ color: NVIS.white, fontWeight: 600 }}>
              {tableCount} table{tableCount !== 1 ? 's' : ''}
            </span>
            {', '}
            ~{estimatedTime}s estimated
          </div>

          {/* Pipeline progress */}
          <div
            style={{
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: NVIS.dim,
              marginBottom: '6px',
            }}
          >
            Pipeline
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '14px' }}>
            {steps.map((step, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '4px 8px',
                  borderRadius: '3px',
                  backgroundColor:
                    step.status === 'running'
                      ? `${NVIS.accent}08`
                      : 'transparent',
                  border:
                    step.status === 'running'
                      ? `1px solid ${NVIS.accent}20`
                      : '1px solid transparent',
                }}
              >
                <span
                  style={{
                    fontSize: '12px',
                    color: stepStatusColor(step.status),
                    width: '16px',
                    textAlign: 'center',
                  }}
                >
                  {stepStatusIcon(step.status)}
                </span>
                <span
                  style={{
                    flex: 1,
                    fontSize: '11px',
                    color:
                      step.status === 'done'
                        ? NVIS.white
                        : step.status === 'running'
                        ? NVIS.accent
                        : NVIS.dim,
                  }}
                >
                  {step.name}
                </span>
                {step.durationMs != null && (
                  <span
                    style={{
                      fontSize: '9px',
                      fontVariantNumeric: 'tabular-nums',
                      color: NVIS.dim,
                    }}
                  >
                    {step.durationMs}ms
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Diff preview */}
          {result && (
            <div
              style={{
                padding: '10px 12px',
                backgroundColor: NVIS.surface2,
                border: `1px solid ${NVIS.borderSolid}`,
                borderRadius: '4px',
              }}
            >
              <div
                style={{
                  fontSize: '9px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: NVIS.dim,
                  marginBottom: '6px',
                }}
              >
                Diff Preview
              </div>
              <div style={{ display: 'flex', gap: '12px', fontSize: '11px' }}>
                {result.blocksAdded > 0 && (
                  <span style={{ color: '#15803d' }}>
                    +{result.blocksAdded} added
                  </span>
                )}
                {result.blocksRemoved > 0 && (
                  <span style={{ color: '#dc2626' }}>
                    -{result.blocksRemoved} removed
                  </span>
                )}
                {result.blocksModified > 0 && (
                  <span style={{ color: NVIS.accent }}>
                    ~{result.blocksModified} modified
                  </span>
                )}
              </div>
              <div style={{ fontSize: '10px', color: NVIS.dim, marginTop: '4px' }}>
                Confidence delta:{' '}
                <span
                  style={{
                    color: result.confidenceDelta >= 0 ? '#15803d' : '#dc2626',
                    fontWeight: 600,
                  }}
                >
                  {result.confidenceDelta >= 0 ? '+' : ''}
                  {result.confidenceDelta.toFixed(3)}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 16px',
            borderTop: `1px solid ${NVIS.borderSolid}`,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            justifyContent: 'flex-end',
          }}
        >
          {!running && !result && (
            <button
              onClick={runPipeline}
              style={{
                fontFamily: 'monospace',
                fontSize: '11px',
                padding: '6px 16px',
                borderRadius: '4px',
                border: `1px solid ${NVIS.accent}`,
                backgroundColor: `${NVIS.accent}14`,
                color: NVIS.accent,
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Run Re-extract
            </button>
          )}
          {result && (
            <button
              onClick={() => onAccept(result)}
              style={{
                fontFamily: 'monospace',
                fontSize: '11px',
                padding: '6px 16px',
                borderRadius: '4px',
                border: '1px solid rgba(21, 128, 61, 0.4)',
                backgroundColor: 'rgba(21, 128, 61, 0.12)',
                color: '#15803d',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Accept
            </button>
          )}
          <button
            onClick={onCancel}
            disabled={running}
            style={{
              fontFamily: 'monospace',
              fontSize: '11px',
              padding: '6px 16px',
              borderRadius: '4px',
              border: `1px solid ${NVIS.borderSolid}`,
              backgroundColor: NVIS.surface2,
              color: NVIS.dim,
              cursor: running ? 'not-allowed' : 'pointer',
              opacity: running ? 0.5 : 1,
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
