import { useState, useEffect, useCallback } from 'react'
import { NVIS } from '../theme'

interface EvidenceCasePanelProps {
  open: boolean
  onClose: () => void
  prefillContext?: {
    controlId?: string
    claim?: string
    sources?: string[]
  }
}

type Verdict = 'supported' | 'refuted' | 'insufficient'

const VERDICT_OPTIONS: { value: Verdict; label: string; color: string }[] = [
  { value: 'supported', label: 'Supported', color: NVIS.green },
  { value: 'refuted', label: 'Refuted', color: NVIS.red },
  { value: 'insufficient', label: 'Insufficient', color: NVIS.amber },
]

export default function EvidenceCasePanel({ open, onClose, prefillContext }: EvidenceCasePanelProps) {
  const [claim, setClaim] = useState('')
  const [verdict, setVerdict] = useState<Verdict>('insufficient')
  const [confidence, setConfidence] = useState(50)
  const [sources, setSources] = useState<string[]>([])
  const [newSource, setNewSource] = useState('')
  const [notes, setNotes] = useState('')

  // Reset form when opening with new prefill context
  useEffect(() => {
    if (open && prefillContext) {
      setClaim(prefillContext.claim ?? '')
      setSources(prefillContext.sources ?? [])
      setVerdict('insufficient')
      setConfidence(50)
      setNotes('')
      setNewSource('')
    }
  }, [open, prefillContext])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && open) {
      onClose()
    }
  }, [open, onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const addSource = () => {
    const trimmed = newSource.trim()
    if (trimmed && !sources.includes(trimmed)) {
      setSources([...sources, trimmed])
      setNewSource('')
    }
  }

  const removeSource = (idx: number) => {
    setSources(sources.filter((_, i) => i !== idx))
  }

  const handleCreate = () => {
    const evidenceCase = {
      claim,
      verdict,
      confidence,
      sources,
      notes,
      controlId: prefillContext?.controlId,
      createdAt: new Date().toISOString(),
    }
    console.log('[EvidenceCasePanel] Create case:', evidenceCase)
    onClose()
  }

  if (!open) return null

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 10px',
    background: NVIS.surface2,
    border: `1px solid ${NVIS.borderSolid}`,
    borderRadius: 4,
    color: NVIS.white,
    fontSize: 12,
    fontFamily: 'monospace',
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: NVIS.dim,
    marginBottom: 4,
    display: 'block',
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          zIndex: 1000,
        }}
      />

      {/* Panel */}
      <div
        role="dialog"
        aria-label="Evidence Case"
        aria-modal="true"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: 480,
          height: '100vh',
          background: NVIS.surface,
          borderLeft: `1px solid ${NVIS.borderSolid}`,
          zIndex: 1001,
          display: 'flex',
          flexDirection: 'column',
          fontFamily: 'monospace',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '14px 16px',
          borderBottom: `1px solid ${NVIS.borderSolid}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: NVIS.white }}>Evidence Case</div>
            {prefillContext?.controlId && (
              <div style={{ fontSize: 10, color: NVIS.dim, marginTop: 2 }}>
                Control: <span style={{ color: NVIS.accent }}>{prefillContext.controlId}</span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close panel"
            style={{
              background: 'none',
              border: 'none',
              color: NVIS.dim,
              fontSize: 18,
              cursor: 'pointer',
              padding: '4px 8px',
              fontFamily: 'monospace',
            }}
          >
            X
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Claim */}
          <div>
            <label style={labelStyle}>Claim</label>
            <textarea
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="Enter the claim to evaluate..."
              rows={3}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>

          {/* Verdict */}
          <div>
            <label style={labelStyle}>Verdict</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {VERDICT_OPTIONS.map((opt) => {
                const isSelected = verdict === opt.value
                return (
                  <button
                    key={opt.value}
                    onClick={() => setVerdict(opt.value)}
                    style={{
                      flex: 1,
                      padding: '6px 10px',
                      fontSize: 11,
                      fontWeight: isSelected ? 600 : 400,
                      fontFamily: 'monospace',
                      cursor: 'pointer',
                      border: `1px solid ${isSelected ? opt.color : NVIS.borderSolid}`,
                      borderRadius: 4,
                      background: isSelected ? `${opt.color}1a` : 'transparent',
                      color: isSelected ? opt.color : NVIS.dim,
                    }}
                  >
                    {opt.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Confidence */}
          <div>
            <label style={labelStyle}>
              Confidence: <span style={{ color: NVIS.white }}>{confidence}%</span>
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
              style={{ width: '100%', accentColor: NVIS.accent }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: NVIS.dim }}>
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Sources */}
          <div>
            <label style={labelStyle}>Source References</label>
            {sources.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
                {sources.map((src, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 8px',
                      background: NVIS.surface2,
                      borderRadius: 3,
                      fontSize: 11,
                      color: NVIS.white,
                    }}
                  >
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {src}
                    </span>
                    <button
                      onClick={() => removeSource(idx)}
                      aria-label={`Remove source: ${src}`}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: NVIS.dim,
                        cursor: 'pointer',
                        fontSize: 11,
                        padding: '0 4px',
                        fontFamily: 'monospace',
                      }}
                    >
                      x
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                type="text"
                value={newSource}
                onChange={(e) => setNewSource(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addSource() }}
                placeholder="Add source reference..."
                style={{ ...inputStyle, flex: 1 }}
              />
              <button
                onClick={addSource}
                style={{
                  padding: '6px 12px',
                  fontSize: 11,
                  fontFamily: 'monospace',
                  background: NVIS.surface2,
                  border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: 4,
                  color: NVIS.dim,
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                Add
              </button>
            </div>
          </div>

          {/* Notes */}
          <div>
            <label style={labelStyle}>Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Additional notes..."
              rows={4}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px',
          borderTop: `1px solid ${NVIS.borderSolid}`,
          display: 'flex',
          gap: 8,
          justifyContent: 'flex-end',
          flexShrink: 0,
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              fontFamily: 'monospace',
              background: 'transparent',
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 4,
              color: NVIS.dim,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            style={{
              padding: '8px 16px',
              fontSize: 12,
              fontWeight: 600,
              fontFamily: 'monospace',
              background: NVIS.accent,
              border: 'none',
              borderRadius: 4,
              color: '#000',
              cursor: 'pointer',
            }}
          >
            Create Case
          </button>
        </div>
      </div>
    </>
  )
}
