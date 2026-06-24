import React, { useMemo, useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Loader2,
  Mic,
  Shield,
  Sparkles,
  XCircle,
} from 'lucide-react'
import type { DisclosureVariant, ThinkingTraceLikeStep } from './memory-turn'
import type { ThinkingTraceLeadingIcon } from './thinkingTraceHelpers'

export type ThinkingTraceStep = ThinkingTraceLikeStep

export interface ThinkingTraceProps {
  steps?: ThinkingTraceStep[]
  title?: string
  label?: string
  currentLabel?: string
  disclosureVariant?: DisclosureVariant
  leadingIcon?: ThinkingTraceLeadingIcon
  placement?: 'header' | 'footer'
  displayMode?: 'current' | 'full'
  defaultOpen?: boolean
  isStreaming?: boolean
  className?: string
  dataQid?: string
}

export function ThinkingTrace({
  steps = [],
  title = 'Thinking',
  label = 'Show thinking',
  currentLabel,
  disclosureVariant = 'thinking',
  leadingIcon = disclosureVariant === 'evidence-case' ? 'shield' : 'sparkle',
  placement = 'footer',
  displayMode = 'full',
  defaultOpen = false,
  isStreaming = false,
  className,
  dataQid,
}: ThinkingTraceProps): JSX.Element | null {
  const [open, setOpen] = useState(defaultOpen)
  const visibleSteps = useMemo(() => {
    if (displayMode === 'current') {
      const running = [...steps].reverse().find((step) => step.status === 'running')
      return running ? [running] : steps.slice(-1)
    }
    return steps
  }, [displayMode, steps])

  if (!steps.length && !isStreaming && !currentLabel) return null

  const resolvedCurrent = currentLabel ?? visibleSteps[visibleSteps.length - 1]?.label ?? title
  const qid = dataQid ?? (disclosureVariant === 'evidence-case' ? 'shared-chat:thinking:evidence-case' : 'shared-chat:thinking')

  return (
    <section
      className={className}
      data-qid={qid}
      data-disclosure-variant={disclosureVariant}
      data-placement={placement}
      style={{
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(255,255,255,0.03)',
        borderRadius: 14,
        marginTop: 10,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        data-qid={`${qid}:toggle`}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '9px 10px',
          border: 0,
          background: 'transparent',
          color: '#e9edf3',
          cursor: 'pointer',
          font: 'inherit',
          textAlign: 'left',
        }}
      >
        <TraceLeadingIcon leadingIcon={leadingIcon} />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 12, fontWeight: 700 }}>{open ? title : label}</span>
          <span style={{ display: 'block', marginTop: 2, color: '#9ba7b7', fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {isStreaming ? resolvedCurrent : stepSummary(steps)}
          </span>
        </span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>

      {open && (
        <ol
          data-qid={`${qid}:steps`}
          style={{
            margin: 0,
            padding: '0 10px 10px 10px',
            listStyle: 'none',
            display: 'grid',
            gap: 8,
          }}
        >
          {(visibleSteps.length ? visibleSteps : [{ id: 'current', label: resolvedCurrent, status: 'running' as const }]).map((step) => (
            <li
              key={`${step.id}-${step.status ?? 'pending'}`}
              data-qid={`${qid}:step:${step.id}`}
              style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: 8, alignItems: 'start' }}
            >
              <StepStatusIcon status={step.status} />
              <span>
                <span style={{ display: 'block', color: '#dce5f3', fontSize: 12, fontWeight: 650 }}>{step.label}</span>
                {step.detail && (
                  <span style={{ display: 'block', color: '#8e9aae', fontSize: 11, lineHeight: 1.45, marginTop: 2 }}>{step.detail}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export function TraceLeadingIcon({ leadingIcon }: { leadingIcon: ThinkingTraceLeadingIcon }): JSX.Element | null {
  if (leadingIcon === 'none') return null
  if (leadingIcon === 'shield') return <Shield size={16} strokeWidth={1.7} aria-hidden="true" />
  if (leadingIcon === 'mic') return <Mic size={16} strokeWidth={1.7} aria-hidden="true" />
  return <Sparkles size={16} strokeWidth={1.7} aria-hidden="true" />
}

function StepStatusIcon({ status }: { status?: ThinkingTraceStep['status'] }): JSX.Element {
  if (status === 'completed') return <CheckCircle2 size={15} strokeWidth={1.7} aria-hidden="true" />
  if (status === 'failed') return <XCircle size={15} strokeWidth={1.7} aria-hidden="true" />
  if (status === 'running') return <Loader2 size={15} strokeWidth={1.7} aria-hidden="true" />
  return <Circle size={15} strokeWidth={1.7} aria-hidden="true" />
}

function stepSummary(steps: ThinkingTraceStep[]): string {
  if (!steps.length) return 'No trace steps captured'
  const failed = steps.find((step) => step.status === 'failed')
  if (failed) return failed.detail ?? failed.label
  const completed = steps.filter((step) => step.status === 'completed').length
  return `${completed}/${steps.length} steps complete`
}

export default ThinkingTrace
