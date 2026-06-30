import { useState, useCallback } from 'react'
import { NVIS } from './theme'
import type { BboxBlock, ProofStatus } from './types'
import { useRegisterAction } from '../../hooks/useRegisterAction'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PIPELINE_STAGES = ['Flag', 'Map', 'Evidence', 'Prove', 'Review'] as const
type PipelineStage = typeof PIPELINE_STAGES[number]

const STAGE_COLORS: Record<PipelineStage, string> = {
  Flag: '#7c3aed',
  Map: NVIS.accent,
  Evidence: '#b45309',
  Prove: '#15803d',
  Review: NVIS.dim,
}

const PROOF_STATUS_COLORS: Record<ProofStatus, { bg: string; border: string; text: string }> = {
  proven: {
    bg: 'rgba(21, 128, 61, 0.10)',
    border: 'rgba(21, 128, 61, 0.25)',
    text: '#15803d',
  },
  partial: {
    bg: 'rgba(74, 158, 255, 0.10)',
    border: 'rgba(74, 158, 255, 0.25)',
    text: NVIS.accent,
  },
  unproven: {
    bg: 'rgba(180, 83, 9, 0.10)',
    border: 'rgba(180, 83, 9, 0.25)',
    text: '#b45309',
  },
  axiom: {
    bg: 'rgba(153, 153, 153, 0.10)',
    border: 'rgba(153, 153, 153, 0.25)',
    text: NVIS.dim,
  },
}

const PROOF_STATUS_LABELS: Record<ProofStatus, string> = {
  proven: 'Proven',
  partial: 'Partial',
  unproven: 'Unproven',
  axiom: 'Axiom',
}

// Mock NIST SP 800-53 controls
const NIST_CONTROLS = [
  'AC-1 Policy and Procedures',
  'AC-2 Account Management',
  'AC-3 Access Enforcement',
  'AC-4 Information Flow',
  'AC-5 Separation of Duties',
  'AC-6 Least Privilege',
  'AU-2 Event Logging',
  'AU-9 Protection of Audit Info',
  'CA-7 Continuous Monitoring',
  'CM-6 Configuration Settings',
  'IA-2 Identification and Auth',
  'IA-5 Authenticator Management',
  'SC-7 Boundary Protection',
  'SC-12 Crypto Key Management',
  'SI-3 Malicious Code Protection',
]

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RequirementsBlockProps {
  block: BboxBlock
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RequirementsBlock({ block }: RequirementsBlockProps) {
  const [flagged, setFlagged] = useState(true)
  const [selectedControl, setSelectedControl] = useState('')
  const [proofStatus] = useState<ProofStatus>('unproven')
  const [currentStage, setCurrentStage] = useState<number>(0) // 0=Flag

  // QuerySpec action registrations (data-qid → voice/NL/agent control)
  useRegisterAction('req-block:item-1', { app: 'datalake-explorer', action: 'ITEM_1', label: 'Item 1', description: 'Item 1 in RequirementsBlock' })
  useRegisterAction('req-block:item-2', { app: 'datalake-explorer', action: 'ITEM_2', label: 'Item 2', description: 'Item 2 in RequirementsBlock' })
  useRegisterAction('req-block:item-3', { app: 'datalake-explorer', action: 'ITEM_3', label: 'Item 3', description: 'Item 3 in RequirementsBlock' })

  const handleCreateEvidence = useCallback(() => {
    console.log('Creating evidence case for block:', block.id, {
      controlMapping: selectedControl,
      text: block.text.slice(0, 200),
    })
    // Advance pipeline
    setCurrentStage(Math.min(PIPELINE_STAGES.length - 1, 2))
  }, [block, selectedControl])

  return (
    <div
      style={{
        borderLeft: flagged ? '3px solid #7c3aed' : '3px solid transparent',
        paddingLeft: '8px',
      }}
    >
      {/* REQ badge + flag toggle (5.1: purple left border) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
        }}
      >
        {flagged && (
          <span
            style={{
              fontSize: '9px',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '3px',
              backgroundColor: 'rgba(124, 58, 237, 0.12)',
              border: '1px solid rgba(124, 58, 237, 0.3)',
              color: '#7c3aed',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            REQ
          </span>
        )}

        {/* Proof status badge */}
        <span
          style={{
            fontSize: '9px',
            fontWeight: 600,
            padding: '2px 6px',
            borderRadius: '3px',
            backgroundColor: PROOF_STATUS_COLORS[proofStatus].bg,
            border: `1px solid ${PROOF_STATUS_COLORS[proofStatus].border}`,
            color: PROOF_STATUS_COLORS[proofStatus].text,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          {PROOF_STATUS_LABELS[proofStatus]}
        </span>

        <button aria-label="Action"
                data-qid="req-block:item-1" data-qs-action="REQ-BLOCK_ITEM_1"
                title="Item 1"
          onClick={() => setFlagged((p) => !p)}
          style={{
            marginLeft: 'auto',
            fontFamily: 'monospace',
            fontSize: '9px',
            padding: '2px 6px',
            borderRadius: '3px',
            border: `1px solid ${NVIS.borderSolid}`,
            backgroundColor: NVIS.surface2,
            color: NVIS.dim,
            cursor: 'pointer',
          }}
        >
          {flagged ? 'Unflag' : 'Flag as REQ'}
        </button>
      </div>

      {/* Control mapping dropdown */}
      {flagged && (
        <>
          <div
            style={{
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: NVIS.dim,
              marginBottom: '4px',
            }}
          >
            Control Mapping
          </div>
          <select
            value={selectedControl}
                data-qid="req-block:item-2" data-qs-action="REQ-BLOCK_ITEM_2"
                title="Item 2"
            onChange={(e) => {
              setSelectedControl(e.target.value)
              if (e.target.value) setCurrentStage(Math.max(currentStage, 1))
            }}
            style={{
              width: '100%',
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '4px 8px',
              borderRadius: '3px',
              backgroundColor: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              color: NVIS.white,
              cursor: 'pointer',
              marginBottom: '8px',
            }}
          >
            <option value="">Select control...</option>
            {NIST_CONTROLS.map((ctrl) => (
              <option key={ctrl} value={ctrl}>
                {ctrl}
              </option>
            ))}
          </select>

          {/* + Evidence Case button */}
          <button aria-label="Action"
                data-qid="req-block:item-3" data-qs-action="REQ-BLOCK_ITEM_3"
                title="Item 3"
            onClick={handleCreateEvidence}
            disabled={!selectedControl}
            style={{
              width: '100%',
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '5px 10px',
              borderRadius: '3px',
              border: selectedControl
                ? '1px solid rgba(124, 58, 237, 0.3)'
                : `1px solid ${NVIS.borderSolid}`,
              backgroundColor: selectedControl
                ? 'rgba(124, 58, 237, 0.10)'
                : NVIS.surface2,
              color: selectedControl ? '#7c3aed' : NVIS.dim,
              cursor: selectedControl ? 'pointer' : 'not-allowed',
              marginBottom: '10px',
              fontWeight: 600,
              opacity: selectedControl ? 1 : 0.5,
            }}
          >
            + Evidence Case
          </button>

          {/* Pipeline strip */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 8px',
              backgroundColor: NVIS.surface2,
              borderRadius: '3px',
              border: `1px solid ${NVIS.borderSolid}`,
            }}
          >
            {PIPELINE_STAGES.map((stage, i) => {
              const isDone = i < currentStage
              const isCurrent = i === currentStage
              const color = isDone
                ? '#15803d'
                : isCurrent
                ? STAGE_COLORS[stage]
                : NVIS.dim

              return (
                <div
                  key={stage}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  {i > 0 && (
                    <span
                      style={{
                        width: '12px',
                        height: '1px',
                        backgroundColor: isDone ? '#15803d' : NVIS.borderSolid,
                      }}
                    />
                  )}
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '2px',
                    }}
                  >
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        backgroundColor: isDone
                          ? '#15803d'
                          : isCurrent
                          ? color
                          : 'transparent',
                        border: `2px solid ${color}`,
                        boxSizing: 'border-box',
                      }}
                    />
                    <span
                      style={{
                        fontSize: '7px',
                        color,
                        textTransform: 'uppercase',
                        letterSpacing: '0.03em',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {stage}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
