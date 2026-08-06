import React, { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertCircle,
  Archive,
  Braces,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Copy,
  Database,
  FileText,
  MessageSquare,
  Loader2,
  Mic,
  Network,
  RefreshCw,
  Search,
  Shield,
  Sparkles,
  Tag,
  Target,
  Terminal,
  XCircle,
} from 'lucide-react'
import type { DisclosureVariant, ThinkingTraceLikeStep } from './memory-turn'
import type { ThinkingTraceLeadingIcon } from './thinkingTraceHelpers'
import { useRegisterAction } from './_support/useRegisterAction'
import { GraphTraversalOverlay } from './GraphTraversalOverlay'
import type { GraphTraversalRequest, TraceEntity } from './GraphTraversalOverlay'

export type ThinkingTraceStep = ThinkingTraceLikeStep

type UnknownRecord = Record<string, unknown>

type PhaseTheme = 'blue' | 'indigo' | 'purple' | 'amber' | 'rose'

type PhaseUiConfig = {
  title: string
  icon?: ThinkingTraceStep['icon']
  theme: PhaseTheme
}

const PHASE_DICTIONARY: Record<string, PhaseUiConfig> = {
  'classifying-intent': { title: 'Classifying intent', icon: 'target', theme: 'indigo' },
  'memory-intent': { title: 'Resolving memory intent', icon: 'memory', theme: 'purple' },
  'extract-entities': { title: 'Extracting entities', icon: 'search', theme: 'purple' },
  'extracting-entities': { title: 'Extracting entities', icon: 'search', theme: 'purple' },
  'finalizing-intent': { title: 'Finalizing intent', icon: 'target', theme: 'indigo' },
  'looking-in-memory': { title: 'Querying memory', icon: 'memory', theme: 'purple' },
  'memory-recall': { title: 'Querying memory', icon: 'memory', theme: 'purple' },
  'getting-results': { title: 'Getting results', icon: 'check', theme: 'blue' },
  'querying-threat-matrix': { title: 'Querying threat matrix', icon: 'shield', theme: 'amber' },
  'create-evidence-case': { title: 'Building evidence case', icon: 'shield', theme: 'rose' },
  'create-figure': { title: 'Rendering figure', icon: 'terminal', theme: 'indigo' },
  analytics: { title: 'Running analytics', icon: 'terminal', theme: 'indigo' },
  answering: { title: 'Compiling response', icon: 'terminal', theme: 'blue' },
  response: { title: 'Compiling response', icon: 'terminal', theme: 'blue' },
  default: { title: 'Processing request', icon: 'terminal', theme: 'blue' },
}

export function useThinkingTrace(defaultOpen = false) {
  const [open, setOpen] = useState(defaultOpen)
  return {
    open,
    setOpen,
    toggle: () => setOpen((value) => !value),
  }
}

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
  summary?: string
  className?: string
  dataQid?: string
  onRetryStep?: (step: ThinkingTraceStep) => void
}

export function ThinkingTrace({
  steps = [],
  title = 'Thinking',
  label,
  currentLabel,
  disclosureVariant = 'thinking',
  leadingIcon = disclosureVariant === 'evidence-case' ? 'shield' : 'none',
  placement = 'footer',
  displayMode = 'full',
  defaultOpen = false,
  isStreaming = false,
  summary,
  className,
  dataQid,
  onRetryStep,
}: ThinkingTraceProps): JSX.Element | null {
  const [open, setOpen] = useState(defaultOpen)
  const [expandedStepIds, setExpandedStepIds] = useState<Set<string>>(() => new Set())
  const [graphRequest, setGraphRequest] = useState<GraphTraversalRequest | null>(null)
  const wasStreaming = useRef(isStreaming)
  const normalizedSteps = useMemo(() => normalizeThinkingTraceSteps(steps), [steps])
  const visibleSteps = useMemo(() => {
    if (displayMode === 'current') {
      const running = [...normalizedSteps].reverse().find((step) => step.status === 'running')
      return running ? [running] : normalizedSteps.slice(-1)
    }
    return normalizedSteps
  }, [displayMode, normalizedSteps])
  const qid = dataQid ?? (disclosureVariant === 'evidence-case' ? 'shared-chat:thinking:evidence-case' : 'shared-chat:thinking')

  useRegisterAction(`${qid}:toggle`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_TOGGLE_THINKING_TRACE',
    label: 'Toggle thinking trace',
    description: 'Expand or collapse the shared chat thinking trace',
  })
  useRegisterAction(`${qid}:pipeline:visualize-graph`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_VISUALIZE_GRAPH_TRAVERSAL',
    label: 'Visualize graph traversal',
    description: 'Open a bounded Memory graph traversal for entities extracted from a thinking trace step',
  })
  useRegisterAction(`${qid}:pipeline:download-json`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_DOWNLOAD_TRACE_ENTITIES_JSON',
    label: 'Download trace entities JSON',
    description: 'Download structured entities from a thinking trace step as JSON',
  })
  useRegisterAction(`${qid}:pipeline:copy-all`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_COPY_TRACE_ENTITIES',
    label: 'Copy trace entities',
    description: 'Copy all raw entity values from a thinking trace step',
  })
  useRegisterAction(`${qid}:pipeline:retry-step`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_RETRY_TRACE_STEP',
    label: 'Retry trace step',
    description: 'Retry a failed shared chat thinking trace step when a retry handler is available',
  })
  useRegisterAction(`${qid}:pipeline:toggle-step`, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_TOGGLE_TRACE_STEP',
    label: 'Toggle trace step',
    description: 'Expand or collapse details for a completed shared chat thinking trace step',
  })

  const resolvedCurrent = currentLabel ?? visibleSteps[visibleSteps.length - 1]?.label ?? title
  const runningStep = [...normalizedSteps].reverse().find((step) => step.status === 'running')
  const pipelineSteps = title === 'Watch thinking' ? normalizedSteps.filter((step) => step.id !== 'watch-scene-context') : normalizedSteps
  const pipelineRunningStep = [...pipelineSteps].reverse().find((step) => step.status === 'running')
  const activeStep = pipelineRunningStep ?? runningStep
  const activeTheme = activeStep ? phaseUiConfig(activeStep).theme : PHASE_DICTIONARY.default.theme
  const renderedPipelineSteps = visibleSteps.length ? visibleSteps : [{ id: 'current', label: resolvedCurrent, status: 'running' as const }]
  const hasTerminalCompletion = [...pipelineSteps].reverse().some((step) => {
    if (step.status !== 'completed' && step.status !== 'skipped') return false
    return ['answering', 'response', 'getting-results', 'create-evidence-case'].includes(normalizePhaseKey(step.id))
  })
  const failedStep = hasTerminalCompletion
    ? undefined
    : [...pipelineSteps].reverse().find((step) => isStepError(step))
  const isComplete = !isStreaming && hasTerminalCompletion && !failedStep
  const entityCount = normalizedSteps.reduce((count, step) => count + traceEntitiesFromStep(step).length, 0)
  const completionSummary = summary ?? (entityCount > 0 ? `${entityCount} ${entityCount === 1 ? 'entity' : 'entities'}` : undefined)
  const statusLabel = failedStep
    ? `Process stopped: ${phaseUiConfig(failedStep).title}`
    : isStreaming
      ? currentLabel ?? (activeStep ? phaseUiConfig(activeStep).title : resolvedCurrent)
      : isComplete
        ? title === 'Watch thinking' ? 'Report ready' : 'Analysis complete'
        : activeStep ? phaseUiConfig(activeStep).title : label ?? title

  useEffect(() => {
    const justCompleted = wasStreaming.current && !isStreaming && hasTerminalCompletion
    wasStreaming.current = isStreaming
    if (!justCompleted) return
    const timer = window.setTimeout(() => setOpen(false), 1500)
    return () => window.clearTimeout(timer)
  }, [hasTerminalCompletion, isStreaming])

  if (!steps.length && !isStreaming && !currentLabel) return null

  const togglePipelineStep = (stepKey: string): void => {
    setExpandedStepIds((current) => {
      const next = new Set(current)
      if (next.has(stepKey)) next.delete(stepKey)
      else next.add(stepKey)
      return next
    })
  }

  return (
    <section
      className={['chat-thinking-trace', 'chat-thinking-trace--process', className].filter(Boolean).join(' ')}
      data-qid={qid}
      data-disclosure-variant={disclosureVariant}
      data-placement={placement}
      data-state={failedStep ? 'failed' : isStreaming ? 'processing' : isComplete ? 'complete' : 'ready'}
      data-phase-theme={activeTheme}
      style={{
        marginTop: 0,
        overflow: 'visible',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        flex: placement === 'header' ? '1 1 auto' : undefined,
        minWidth: placement === 'header' ? 0 : undefined,
      }}
    >
      <button
        type="button"
        className="chat-thinking-trace__status"
        data-qid={`${qid}:toggle`}
        data-qs-action="SHARED_CHAT_TOGGLE_THINKING_TRACE"
        title={open ? 'Collapse thinking trace' : 'Expand thinking trace'}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        style={{
          width: placement === 'header' ? 'auto' : '100%',
          maxWidth: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: placement === 'header' ? 6 : 8,
          padding: placement === 'header' ? 0 : '9px 10px',
          border: 0,
          background: 'transparent',
          color: placement === 'header' ? '#b8c2d0' : '#e0e0e0',
          cursor: 'pointer',
          font: 'inherit',
          textAlign: 'left',
          minHeight: 44,
        }}
      >
        {leadingIcon !== 'none' && placement !== 'header' && (
          <span className="chat-thinking-trace__leading-icon" aria-hidden="true">
            <TraceLeadingIcon leadingIcon={leadingIcon} />
          </span>
        )}
        <span
          className={[
            'chat-thinking-trace__state-icon',
            failedStep ? 'chat-thinking-trace__state-icon--failed' : isComplete ? 'chat-thinking-trace__state-icon--complete' : '',
          ].filter(Boolean).join(' ')}
          aria-hidden="true"
        >
          {failedStep
            ? <XCircle size={16} strokeWidth={2} />
            : isComplete
              ? <CheckCircle2 size={16} strokeWidth={2.4} />
              : <Sparkles size={16} strokeWidth={1.8} />}
        </span>
        <span className="chat-thinking-trace__status-copy" style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <span className="chat-thinking-trace__status-label" style={{ color: placement === 'header' ? '#b8c2d0' : '#e0e0e0', fontWeight: placement === 'header' ? 700 : 650 }}>
            {statusLabel}
          </span>
          {isComplete && !open && completionSummary ? (
            <span className="chat-thinking-trace__summary">{completionSummary}</span>
          ) : null}
        </span>
        <span className="chat-thinking-trace__disclosure-chevron" aria-hidden="true">
          {open ? <ChevronUp size={13} strokeWidth={2} /> : <ChevronDown size={13} strokeWidth={2} />}
        </span>
      </button>
      <div className="chat-thinking-trace__progress" aria-hidden="true">
        <span
          className={isStreaming ? 'animate-indeterminate' : undefined}
          data-complete={isComplete ? 'true' : 'false'}
          data-processing={isStreaming ? 'true' : 'false'}
        />
      </div>

      {open ? (
        <div
          className="chat-thinking-trace__accordion"
          data-open="true"
        >
          <div className="chat-thinking-trace__accordion-inner">
            <div className="chat-thinking-trace__verbose-panel" data-qid={`${qid}:verbose-panel`}>
            <div className="chat-thinking-trace__pipeline-header">
              <Terminal size={14} strokeWidth={1.7} aria-hidden="true" />
              <span>Pipeline Execution Log</span>
            </div>
            <ol
              className="chat-thinking-trace__pipeline"
              data-qid={`${qid}:steps`}
              style={{
                margin: 0,
                padding: '8px 10px 10px 18px',
                listStyle: 'none',
                display: 'grid',
                gap: 8,
              }}
            >
              {renderedPipelineSteps.map((step, index) => {
              const entities = traceEntitiesFromStep(step)
              const uiConfig = phaseUiConfig(step)
              const stepQid = qidToken(step.id ?? step.label ?? 'step')
              const stepKey = `${step.id ?? step.label ?? 'step'}:${index}`
              const isLast = index === renderedPipelineSteps.length - 1
              const stepIsError = isStepError(step)
              const stepIsCompleted = isStepComplete(step)
              const stepErrorMessage = errorMessageFromStep(step)
              const hasStepActions = stepIsCompleted && entities.length > 0
              const hasExpandableContent = Boolean(step.detail || entities.length > 0 || hasStepActions)
              const canToggleStep = stepIsCompleted && hasExpandableContent
              const stepIsExpanded = !stepIsCompleted || expandedStepIds.has(stepKey)
              return (
                <motion.li
                  className="chat-thinking-trace__pipeline-step"
                  key={`${step.id}-${step.status ?? 'pending'}`}
                  data-qid={`${qid}:step:${stepQid}`}
                  data-status={step.status ?? 'pending'}
                  data-error={stepIsError ? 'true' : 'false'}
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.24, delay: Math.min(index * 0.035, 0.18), ease: 'easeOut' }}
                  style={{ position: 'relative', display: 'flex', flexDirection: 'column', paddingBottom: isLast ? 0 : 6 }}
                >
                  {!isLast ? (
                    <motion.span
                      className="chat-thinking-trace__pipeline-connector"
                      initial={{ scaleY: 0 }}
                      animate={{ scaleY: 1 }}
                      transition={{ duration: 0.28, delay: Math.min(index * 0.035 + 0.08, 0.26), ease: 'easeInOut' }}
                      aria-hidden="true"
                    />
                  ) : null}
                  <span className="chat-thinking-trace__pipeline-step-header">
                    <motion.span
                      className="chat-thinking-trace__pipeline-icon"
                      initial={{ opacity: 0, scale: 0.78 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.24, ease: [0.165, 0.84, 0.44, 1], delay: Math.min(index * 0.035 + 0.12, 0.3) }}
                    >
                      <StepStatusIcon id={step.id} status={step.status} icon={step.icon ?? uiConfig.icon} />
                    </motion.span>
                    <span className="chat-thinking-trace__pipeline-title-row">
                      {canToggleStep ? (
                        <button
                          type="button"
                          className="chat-thinking-trace__pipeline-step-toggle"
                          data-qid={`${qid}:step:${stepQid}:toggle`}
                          data-qs-action="SHARED_CHAT_TOGGLE_TRACE_STEP"
                          title={stepIsExpanded ? `Collapse ${uiConfig.title}` : `Expand ${uiConfig.title}`}
                          aria-label={stepIsExpanded ? `Collapse ${uiConfig.title}` : `Expand ${uiConfig.title}`}
                          aria-expanded={stepIsExpanded}
                          onClick={(event) => {
                            event.stopPropagation()
                            togglePipelineStep(stepKey)
                          }}
                        >
                          <span className="chat-thinking-trace__pipeline-title">{uiConfig.title}</span>
                          <motion.span
                            className="chat-thinking-trace__pipeline-step-chevron"
                            animate={{ rotate: stepIsExpanded ? 180 : 0 }}
                            transition={{ duration: 0.18 }}
                            aria-hidden="true"
                          >
                            <ChevronDown size={13} strokeWidth={2} />
                          </motion.span>
                        </button>
                      ) : (
                        <span className="chat-thinking-trace__pipeline-title">{uiConfig.title}</span>
                      )}
                    </span>
                  </span>
                  <span className="chat-thinking-trace__pipeline-step-body">
                    <AnimatePresence initial={false}>
                      {stepIsExpanded && hasExpandableContent ? (
                        <motion.span
                          className="chat-thinking-trace__pipeline-content"
                          initial={{ opacity: 0, scaleY: 0.96 }}
                          animate={{ opacity: 1, scaleY: 1 }}
                          exit={{ opacity: 0, scaleY: 0.96 }}
                          transition={{ duration: 0.2, ease: [0.165, 0.84, 0.44, 1] }}
                          style={{ transformOrigin: 'top' }}
                        >
                          {hasStepActions ? (
                            <motion.span
                              className="chat-thinking-trace__pipeline-actions"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ duration: 0.18, delay: 0.18 }}
                            >
                              <button
                                type="button"
                                className="chat-thinking-trace__pipeline-action chat-thinking-trace__pipeline-action--graph"
                                data-qid={`${qid}:step:${stepQid}:visualize-graph`}
                                data-qs-action="SHARED_CHAT_VISUALIZE_GRAPH_TRAVERSAL"
                                title="Visualize bounded Memory graph traversal"
                                aria-label="Visualize bounded Memory graph traversal"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  setGraphRequest({ phaseTitle: uiConfig.title, entities })
                                }}
                              >
                                <Network size={13} strokeWidth={2.1} aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                className="chat-thinking-trace__pipeline-action"
                                data-qid={`${qid}:step:${stepQid}:download-json`}
                                data-qs-action="SHARED_CHAT_DOWNLOAD_TRACE_ENTITIES_JSON"
                                title="Download entities as JSON file"
                                aria-label="Download entities as JSON file"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  downloadTraceEntities(entities)
                                }}
                              >
                                <Braces size={13} strokeWidth={2.1} aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                className="chat-thinking-trace__pipeline-action"
                                data-qid={`${qid}:step:${stepQid}:copy-all`}
                                data-qs-action="SHARED_CHAT_COPY_TRACE_ENTITIES"
                                title="Copy all raw entity values"
                                aria-label="Copy all raw entity values"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  void copyTraceEntities(entities)
                                }}
                              >
                                <Copy size={13} strokeWidth={2.1} aria-hidden="true" />
                              </button>
                            </motion.span>
                          ) : null}
                          {step.detail && (
                            <span className="chat-thinking-trace__pipeline-detail">
                              {renderInlineEntityText(step.detail)}
                            </span>
                          )}
                          {entities.length > 0 && (
                            <span className="chat-thinking-trace__entity-row" aria-label="Extracted entities">
                              {entities.map((entity) => (
                                <TraceEntityChip
                                  entity={entity}
                                  key={`${entity.type}:${entity.value}`}
                                  variant="block"
                                />
                              ))}
                            </span>
                          )}
                        </motion.span>
                      ) : null}
                    </AnimatePresence>
                    {stepIsError && stepErrorMessage ? (
                      <motion.span
                        className="chat-thinking-trace__pipeline-error"
                        initial={{ opacity: 0, scaleY: 0.96 }}
                        animate={{ opacity: 1, scaleY: 1 }}
                        transition={{ duration: 0.24, delay: 0.2, ease: [0.165, 0.84, 0.44, 1] }}
                        style={{ transformOrigin: 'top' }}
                      >
                        <span className="chat-thinking-trace__pipeline-error-message">{stepErrorMessage}</span>
                        {onRetryStep ? (
                          <button
                            type="button"
                            className="chat-thinking-trace__pipeline-retry"
                            data-qid={`${qid}:step:${stepQid}:retry`}
                            data-qs-action="SHARED_CHAT_RETRY_TRACE_STEP"
                            title="Retry step"
                            aria-label={`Retry ${uiConfig.title}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              onRetryStep(step)
                            }}
                          >
                            <RefreshCw size={12} strokeWidth={2} aria-hidden="true" />
                            Retry
                          </button>
                        ) : null}
                      </motion.span>
                    ) : null}
                  </span>
                </motion.li>
              )
              })}
            </ol>
            </div>
          </div>
        </div>
      ) : null}
      {graphRequest ? (
        <GraphTraversalOverlay
          request={graphRequest}
          onClose={() => setGraphRequest(null)}
        />
      ) : null}
    </section>
  )
}

function normalizeThinkingTraceSteps(steps: ThinkingTraceStep[]): ThinkingTraceStep[] {
  const latestById = new Map<string, ThinkingTraceStep>()
  const anonymous: ThinkingTraceStep[] = []
  for (const step of steps) {
    const key = normalizePhaseKey(step.id)
    if (!key) {
      anonymous.push(step)
      continue
    }
    latestById.set(key, step)
  }
  return [...latestById.values(), ...anonymous]
}

export function TraceLeadingIcon({ leadingIcon }: { leadingIcon: ThinkingTraceLeadingIcon }): JSX.Element | null {
  if (leadingIcon === 'none') return null
  if (leadingIcon === 'shield') return <Shield size={16} strokeWidth={1.7} />
  if (leadingIcon === 'mic') return <Mic size={16} strokeWidth={1.7} />
  return <Sparkles size={16} strokeWidth={1.7} />
}

export function ThinkingTraceToggle({
  open,
  onToggle,
  label = 'Show thinking',
  liveLabel,
  isLive = false,
  leadingIcon = 'none',
  qid = 'shared-chat:thinking:toggle',
}: {
  open: boolean
  onToggle: () => void
  label?: string
  currentStep?: ThinkingTraceStep | null
  liveLabel?: string
  isLive?: boolean
  leadingIcon?: ThinkingTraceLeadingIcon
  messageId?: string
  qid?: string
}): JSX.Element {
  useRegisterAction(qid, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_TOGGLE_THINKING_TRACE',
    label: 'Toggle thinking trace',
    description: 'Expand or collapse the shared chat thinking trace',
  })

  return (
    <button
      type="button"
      className="chat-thinking-trace__status"
      data-qid={qid}
      data-qs-action="SHARED_CHAT_TOGGLE_THINKING_TRACE"
      title={isLive && liveLabel ? liveLabel : label}
      onClick={onToggle}
      aria-expanded={open}
    >
      {leadingIcon !== 'none' ? <TraceLeadingIcon leadingIcon={leadingIcon} /> : null}
      <span>{isLive && liveLabel ? liveLabel : label}</span>
      {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
    </button>
  )
}

export function ThinkingTraceSteps({
  steps,
  displayMode = 'full',
  style,
}: {
  steps: ThinkingTraceStep[]
  messageId?: string
  displayMode?: ThinkingTraceProps['displayMode']
  style?: React.CSSProperties
}): JSX.Element {
  const visibleSteps = displayMode === 'current' ? steps.slice(-1) : steps
  return (
    <ol style={style}>
      {visibleSteps.map((step) => (
        <li key={`${step.id}-${step.status ?? 'pending'}`}>
          <StepStatusIcon id={step.id} status={step.status} icon={step.icon} /> {step.label}
        </li>
      ))}
    </ol>
  )
}

function StepStatusIcon({ id, status, icon }: { id?: string; status?: ThinkingTraceStep['status']; icon?: ThinkingTraceStep['icon'] }): JSX.Element {
  if (isStepError({ status })) {
    return <AlertCircle size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  const semanticKey = `${icon ?? ''} ${id ?? ''}`.toLowerCase()
  if (semanticKey.includes('parse') || semanticKey.includes('payload') || semanticKey.includes('file') || id === 'watch-scene-context') {
    return <FileText size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  if (semanticKey.includes('extract') || semanticKey.includes('entity') || semanticKey.includes('search')) {
    return <Search size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  if (semanticKey.includes('query') || semanticKey.includes('threat') || semanticKey.includes('matrix') || semanticKey.includes('evidence') || semanticKey.includes('shield')) {
    return <Shield size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  if (semanticKey.includes('memory') || semanticKey.includes('recall') || semanticKey.includes('archive')) {
    return <Database size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  if (semanticKey.includes('compile') || semanticKey.includes('answer') || semanticKey.includes('response') || semanticKey.includes('terminal')) {
    return <Terminal size={15} strokeWidth={1.7} aria-hidden="true" />
  }
  if (status === 'running') return <Loader2 className="chat-thinking-trace__running-spinner" size={15} strokeWidth={1.7} aria-hidden="true" />
  switch (id) {
    case 'classifying-intent':
      return <Target size={15} strokeWidth={1.7} aria-hidden="true" />
    case 'extracting-entities':
      return <Tag size={15} strokeWidth={1.7} aria-hidden="true" />
    case 'looking-in-memory':
    case 'persona-recall':
      return <Archive size={15} strokeWidth={1.7} aria-hidden="true" />
    case 'create-evidence-case':
      return <Shield size={15} strokeWidth={1.7} aria-hidden="true" />
    case 'answering':
    case 'persona-answer':
      return <MessageSquare size={15} strokeWidth={1.7} aria-hidden="true" />
    default:
      return status === 'completed' || status === 'skipped'
        ? <CheckCircle2 size={15} strokeWidth={1.7} aria-hidden="true" />
        : <Circle size={15} strokeWidth={1.7} aria-hidden="true" />
  }
}

function isStepComplete(step: ThinkingTraceStep): boolean {
  return step.status === 'completed' || step.status === 'done' || step.status === 'skipped'
}

function isStepError(step: Pick<ThinkingTraceStep, 'status'>): boolean {
  return step.status === 'failed' || step.status === 'error'
}

function errorMessageFromStep(step: ThinkingTraceStep): string | null {
  const data = isUnknownRecord(step.data) ? step.data : null
  for (const value of [data?.errorMessage, data?.error, data?.message]) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  if (isStepError(step) && step.detail?.trim()) return step.detail.trim()
  return null
}

function TraceEntityChip({ entity, variant }: { entity: TraceEntity; variant: 'inline' | 'block' }): JSX.Element {
  const normalizedType = normalizeEntityType(entity.type)
  const qid = `shared-chat:trace-entity:${variant}:${qidToken(entity.type)}:${qidToken(entity.value)}`
  useRegisterAction(qid, {
    app: 'shared-chat',
    action: 'SHARED_CHAT_COPY_TRACE_ENTITY',
    label: 'Copy trace entity',
    description: 'Copy one structured entity value from a thinking trace',
  })
  return (
    <button
      type="button"
      className={variant === 'inline' ? 'chat-thinking-trace__entity-chip chat-thinking-trace__entity-chip--inline' : 'chat-thinking-trace__entity-chip'}
      data-qid={qid}
      data-qs-action="SHARED_CHAT_COPY_TRACE_ENTITY"
      data-entity-type={normalizedType}
      title={`Copy ${entity.label}: ${entity.value}`}
      onClick={(event) => {
        event.stopPropagation()
        void navigator.clipboard?.writeText(entity.value).catch(() => undefined)
      }}
    >
      {variant === 'block' && <span className="chat-thinking-trace__entity-label">{entity.label}</span>}
      <span className="chat-thinking-trace__entity-value">{entity.value}</span>
      <Copy size={11} strokeWidth={1.8} aria-hidden="true" />
    </button>
  )
}

function renderInlineEntityText(text: string): React.ReactNode {
  const entities = inlineEntitiesFromText(text)
  if (!entities.length) return text

  const nodes: React.ReactNode[] = []
  let cursor = 0
  for (const entity of entities) {
    const index = text.indexOf(entity.value, cursor)
    if (index < 0) continue
    if (index > cursor) nodes.push(text.slice(cursor, index))
    nodes.push(<TraceEntityChip entity={entity} key={`${entity.type}:${entity.value}:${index}`} variant="inline" />)
    cursor = index + entity.value.length
  }
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

function traceEntitiesFromStep(step: ThinkingTraceStep): TraceEntity[] {
  const data = isUnknownRecord(step.data) ? step.data : null
  if (!data) return []

  const values: unknown[] = []
  for (const key of ['entities', 'extractedEntities', 'extracted_entities', 'entitySpans', 'anchors', 'validated', 'candidates', 'unresolved']) {
    const candidate = data[key]
    if (Array.isArray(candidate)) values.push(...candidate)
  }

  const nestedEntities = data.entities
  if (isUnknownRecord(nestedEntities)) {
    for (const nestedValue of Object.values(nestedEntities)) {
      if (Array.isArray(nestedValue)) values.push(...nestedValue)
    }
  }

  return uniqueEntities(values.map(normalizeTraceEntity).filter((entity): entity is TraceEntity => Boolean(entity)))
}

function inlineEntitiesFromText(text: string): TraceEntity[] {
  const matches = text.match(/\b(?:CWE-\d+|CVE-\d{4}-\d{4,7}|(?:\d{1,3}\.){3}\d{1,3}|[a-fA-F0-9]{32,64})\b/g) ?? []
  return uniqueEntities(matches.map((value) => ({ label: entityLabelFromValue(value), value, type: entityTypeFromValue(value) })))
}

function normalizeTraceEntity(value: unknown): TraceEntity | null {
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? { label: entityLabelFromValue(text), value: text, type: entityTypeFromValue(text) } : null
  }
  if (!isUnknownRecord(value)) return null

  const entityValue = stringField(value, ['value', 'text', 'id', 'control_id', 'term', 'name'])
  if (!entityValue) return null
  const type = stringField(value, ['type', 'kind', 'entityType', 'category']) ?? entityTypeFromValue(entityValue)
  const label = stringField(value, ['label', 'title', 'name']) ?? entityLabelFromValue(entityValue)
  return { label, value: entityValue, type: normalizeEntityType(type) }
}

function stringField(record: UnknownRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number') return String(value)
  }
  return null
}

function uniqueEntities(entities: TraceEntity[]): TraceEntity[] {
  const seen = new Set<string>()
  return entities.filter((entity) => {
    const key = `${entity.type}:${entity.value}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function entityTypeFromValue(value: string): string {
  if (/^CWE-\d+$/i.test(value)) return 'cwe'
  if (/^CVE-\d{4}-\d{4,7}$/i.test(value)) return 'cve'
  if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(value)) return 'ip'
  if (/^[a-fA-F0-9]{32,64}$/.test(value)) return 'hash'
  return 'entity'
}

function normalizeEntityType(type: string): string {
  const normalized = type.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  if (normalized === 'ipv4' || normalized === 'ip-address' || normalized === 'network') return 'ip'
  if (normalized === 'sha256' || normalized === 'sha1' || normalized === 'md5' || normalized === 'file-hash') return 'hash'
  if (normalized === 'vulnerability' || normalized === 'weakness' || normalized === 'cwe-id') return 'cwe'
  if (normalized === 'identity' || normalized === 'username' || normalized === 'account') return 'user'
  return normalized || 'entity'
}

function entityLabelFromValue(value: string): string {
  const type = entityTypeFromValue(value)
  if (type === 'cwe') return 'CWE'
  if (type === 'cve') return 'CVE'
  if (type === 'ip') return 'IP'
  if (type === 'hash') return 'Hash'
  return 'Entity'
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function phaseUiConfig(step: ThinkingTraceStep): PhaseUiConfig {
  const idKey = normalizePhaseKey(step.id)
  const labelKey = normalizePhaseKey(step.label)
  const direct = PHASE_DICTIONARY[idKey] ?? PHASE_DICTIONARY[labelKey]
  if (direct) return direct
  const label = step.label?.trim()
  if (label && !label.startsWith('$')) return { title: label, icon: step.icon, theme: 'blue' }
  return PHASE_DICTIONARY.default
}

function normalizePhaseKey(value?: string): string {
  return (value ?? '')
    .toLowerCase()
    .trim()
    .replace(/^\$/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function qidToken(value: string, fallback = 'step'): string {
  const token = normalizePhaseKey(value).slice(0, 64)
  return token || fallback
}

async function copyTraceEntities(entities: TraceEntity[]): Promise<void> {
  const textToCopy = entities.map((entity) => entity.value).join('\n')
  await navigator.clipboard?.writeText(textToCopy).catch(() => undefined)
}

function downloadTraceEntities(entities: TraceEntity[]): void {
  if (typeof document === 'undefined') return
  const jsonString = JSON.stringify(entities, null, 2)
  const blob = new Blob([jsonString], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sparta_entities_${Date.now()}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export default ThinkingTrace
