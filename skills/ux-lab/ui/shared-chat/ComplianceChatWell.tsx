/**
 * ComplianceChatWell — Active Intelligence Dashboard
 *
 * Design: Command console, not chat app
 * - Role-based color coding (2px left border)
 * - Message cards with depth
 * - Content-type badges
 * - Thinking card with expand/collapse
 * - Rich input bar with mode selector
 */
import React, { useLayoutEffect, useMemo, useRef, useState, useCallback, useEffect } from 'react'
import type { SyntheticEvent } from 'react'
import Editor from 'react-simple-code-editor'
import Prism from 'prismjs'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-bash'
import {
  X,
  Plus,
  Copy,
  Check,
  Cpu,
  Shield,
  FileText,
  Code,
  GitPullRequest,
  Terminal,
  AlertTriangle,
  Clock,
  BarChart3,
  ChevronRight,
  ArrowDown,
  CornerDownLeft,
  PlayCircle,
  Search,
  User,
  MapPin,
  Tag,
  Maximize2,
  ThumbsUp,
  ThumbsDown,
  GitCommit,
  RotateCw,
  Loader2,
  Mic,
} from 'lucide-react'
import { EmbryVoiceOrb } from './_support/EmbryVoiceOrb'
import type { EmbryVoiceEnvelope } from './_support/useEmbryPlaybackAudioLevel'
import type { ChatMessage, StreamingStep, TurnBranch, UnknownRecord } from './memory-turn'
import { streamingStepsToThinkingTrace } from './memory-turn'
import MessageFooter from './MessageFooter'
import ThinkingTrace from './ThinkingTrace'
import { MarkdownRenderer } from './MarkdownRenderer'
import FeedbackModal from './FeedbackModal'
import type { FeedbackDetailPayload } from './FeedbackModal'
import { InlineEvidenceCase } from './InlineEvidenceCase'
import type { EvidenceCaseData, EvidenceCaseSpan } from './types'
import { ToolAction } from './ToolAction'
import { RecallCard } from './_support/RecallCard'
import type { RecallItem } from './_support/RecallCard'
import { GateChain } from './_support/GateChain'
import type { GateStep } from './_support/GateChain'
import { ThreatMatrixCard } from './_support/ThreatMatrixCard'
import type { ThreatMatrixSummary } from './_support/ThreatMatrixCard'
import { useRBAC } from './_support/useRBAC'
import {
  branchFromMessage,
  leadingIconForBranch,
  thinkingStepsForMessage,
  thinkingTraceDisclosureParts,
} from './thinkingTraceHelpers'
import { entitySpansFromStructuredContext } from './entityContextSpans'
import { useRegisterAction } from './_support/useRegisterAction'
import EmbryEmptyState from './EmbryEmptyState'
import VoiceRecordingState from './VoiceRecordingState'
import {
  ConsoleEvidenceCaseBlock,
  ConsoleExecutionTraceLog,
  ConsoleTerminalAlert,
  dedupeRepeatedParagraphs,
  isTerminalFailureText,
  stripCitationListEcho,
} from './ConsoleTransactionLog'
import ActionTooltip from './ActionTooltip'
import './terminalChat.css'

export interface StarterChip {
  label: string
  prompt: string
  dataQid?: string
  action?: string
  title?: string
  icon?: React.ReactNode
}

const qidToken = (value: string, fallback = 'item'): string => {
  const token = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
  return token || fallback
}

export type InputMode = 'Auto' | 'QRA' | 'Code' | 'Review'

export interface ComplianceChatWellProps {
  messages?: ChatMessage[]
  streamingSteps?: StreamingStep[]
  isStreaming?: boolean
  liveAssistantMessage?: ChatMessage
  onSend?: (...args: unknown[]) => void | Promise<void>
  placeholder?: string
  composerPlaceholder?: string
  disabled?: boolean
  composerDisabled?: boolean
  showComposer?: boolean
  starterQuestions?: string[]
  contextShareLabel?: string
  hideAnswerModeBanner?: boolean
  thinkingLabel?: string
  emptyTitle?: string
  emptyDescription?: string
  starterChips?: StarterChip[]
  qid?: string
  surface?: string
  className?: string
  activeBranch?: TurnBranch
  sidebar?: boolean
  recentChats?: { id: string; title: string; timestamp: number }[]
  promptTemplates?: string[]
  onDeleteMessage?: (messageId: string) => void
  onCopyMessage?: (messageId: string) => void
  onDownloadMessage?: (messageId: string) => void
  onEditTitle?: (title: string) => void
  chatTitle?: string
  agentStatus?: 'idle' | 'processing' | 'ready'
  onFeedback?: (messageId: string, feedback: 'up' | 'down', details?: FeedbackDetailPayload) => void
  onClarifyClick?: (question: string) => void
  onEntityClick?: (...args: unknown[]) => void
  onRunEvidenceCase?: (message: ChatMessage) => void | Promise<void>
  onNavigateMatrix?: (...args: unknown[]) => void
  evidenceCaseLoading?: boolean
  preSignoffWarning?: string
  starterMode?: string
  chatDistanceMode?: string
  chatDensity?: string
  showComposerThinking?: boolean
  alwaysShowLiveStatus?: boolean
  skills?: unknown[]
  shellQid?: string
  hideHeader?: boolean
  showModeToggle?: boolean
  modeLabels?: Record<string, string>
  modeTitles?: Record<string, string>
  adapter?: unknown
  onMessagesChange?: (messages: ChatMessage[]) => void
  onStreamingStepsChange?: (steps: StreamingStep[]) => void
  onStreamingChange?: (isStreaming: boolean) => void
  defaultMode?: string
  projectLabel?: string
  voiceEnabled?: boolean
  voiceStatus?: 'off' | 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
  voiceLabel?: string
  onVoiceToggle?: (enabled: boolean) => void
  /** Optional: convert filesystem paths to URLs for inline media (image=/path, clip=/path, audio=/path) */
  mediaUrl?: (path: string) => string
  /** Turn id whose receipt card should show processing border glow */
  activeProcessingTurnId?: string
  /** Fallback message id when turn id is unavailable during streaming */
  activeProcessingMessageId?: string
  onRegenerateMessage?: (prompt: string) => void | Promise<void>
  /** Host-owned panel rendered between the message list and the composer (e.g. proposal simulate/apply cards). */
  actionSlot?: React.ReactNode
}

const ROLE_COLORS: Record<string, string> = {
  user: '#ffffff',
  assistant: '#03dac6',
  agent: '#03dac6',
  worker: '#03dac6',
  data: '#bb86fc',
  error: '#ff7b72',
}

const CONTENT_TYPE_BADGES: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  qra: { label: 'QRA', color: '#03dac6', icon: <Shield size={10} /> },
  evidence: { label: 'Evidence', color: '#bb86fc', icon: <FileText size={10} /> },
  code: { label: 'Code', color: '#a3a3a3', icon: <Code size={10} /> },
  diff: { label: 'Diff', color: '#ffb86c', icon: <GitPullRequest size={10} /> },
  log: { label: 'Log', color: '#94a3b8', icon: <Terminal size={10} /> },
}

function detectContentType(message: ChatMessage): string | null {
  const meta = (message.metadata ?? {}) as UnknownRecord
  if (meta.contentType) return meta.contentType as string
  if (meta.evidenceCase || meta.evidence_case) return 'evidence'
  if (meta.code || message.content?.includes('```')) return 'code'
  if (meta.diff || message.content?.includes('diff')) return 'diff'
  if (meta.log || message.content?.includes('log')) return 'log'
  if (meta.qra) return 'qra'
  return null
}

function getRoleColor(message: ChatMessage): string {
  const meta = (message.metadata ?? {}) as UnknownRecord
  const role = message.role
  const agentType = meta.agentType as string || meta.source as string

  if (role === 'user') return ROLE_COLORS.user
  if (agentType === 'worker' || agentType === 'child') return ROLE_COLORS.worker
  if (agentType === 'data' || agentType === 'raw') return ROLE_COLORS.data
  return ROLE_COLORS.assistant
}

function initialsForName(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

function formatMessageTime(message: ChatMessage): string {
  const raw = message.timestamp ?? message.createdAt
  const numeric = typeof raw === 'number' ? raw : typeof raw === 'string' ? Date.parse(raw) : NaN
  if (!Number.isFinite(numeric)) return ''
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(numeric))
}

function FileChip({ file, onRemove, disabled }: { file: File; onRemove: () => void; disabled?: boolean }): JSX.Element {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const isImage = file.type.startsWith('image/')

  useRegisterAction('shared-chat:attachment:remove', {
    app: 'shared-chat',
    action: 'SHARED_CHAT_REMOVE_ATTACHMENT',
    label: 'Remove attachment',
    description: 'Remove an attachment chip from the shared chat composer',
  })

  useEffect(() => {
    if (!isImage) return undefined
    const objectUrl = URL.createObjectURL(file)
    setPreviewUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file, isImage])

  return (
    <span
      style={{
        maxWidth: 210,
        flex: '0 1 210px',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        padding: '5px 8px',
        border: '1px solid #333',
        borderRadius: 999,
        background: '#111',
        color: '#A8B2D1',
        fontSize: 12,
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      {isImage && previewUrl ? (
        <img src={previewUrl} alt="" style={{ width: 18, height: 18, borderRadius: 4, objectFit: 'cover', background: '#050505', flexShrink: 0 }} />
      ) : (
        <FileText size={14} color="#64748b" style={{ flexShrink: 0 }} aria-hidden="true" />
      )}
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{file.name}</span>
      <button
        type="button"
        data-qid={`shared-chat:attachment:remove:${file.name.replace(/[^a-zA-Z0-9_-]+/g, '-').toLowerCase() || 'file'}`}
        data-qs-action="SHARED_CHAT_REMOVE_ATTACHMENT"
        title="Remove file"
        disabled={disabled}
        onClick={onRemove}
        style={{
          width: 18,
          height: 18,
          border: 0,
          borderRadius: 999,
          background: 'transparent',
          color: '#64748b',
          display: 'grid',
          placeItems: 'center',
          padding: 0,
          cursor: disabled ? 'not-allowed' : 'pointer',
          flexShrink: 0,
        }}
      >
        <X size={12} aria-hidden="true" />
      </button>
    </span>
  )
}

const WATCH_MEDIA_PREFIXES = ['watch-frames', 'clips', 'audio_mp3', 'frames'] as const
const ALLOWED_ATTACHMENT_MIME_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  'application/json',
  'text/plain',
  'text/csv',
  'text/markdown',
])
const ALLOWED_ATTACHMENT_EXTENSIONS = new Set(['.log', '.conf', '.yaml', '.yml', '.md', '.txt', '.json', '.csv'])
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
const COMPOSER_TEXTAREA_HEIGHT = 144
const COMPOSER_TEXTAREA_MIN_HEIGHT = COMPOSER_TEXTAREA_HEIGHT
const COMPOSER_TEXTAREA_DEFAULT_HEIGHT = COMPOSER_TEXTAREA_HEIGHT
const COMPOSER_TEXTAREA_MAX_HEIGHT = COMPOSER_TEXTAREA_HEIGHT
const COMPOSER_TEXTAREA_FONT_SIZE = 16

function attachmentExtension(fileName: string): string {
  return fileName.includes('.') ? fileName.slice(fileName.lastIndexOf('.')).toLowerCase() : ''
}

function isJsonAttachment(file: File): boolean {
  return file.type === 'application/json' || attachmentExtension(file.name) === '.json'
}

async function compileAttachmentPayload(text: string, files: File[]): Promise<{ displayText: string; compiledContext: string }> {
  const names = files.map((file) => file.name)
  const displayText = `${text}${names.length > 0 ? `${text ? '\n\n' : ''}*[Attached: ${names.join(', ')}]*` : ''}`
  let compiledContext = text

  for (const file of files) {
    if (!isJsonAttachment(file)) continue
    const rawText = await file.text()
    compiledContext += `\n\n--- INJECTED FILE: ${file.name} ---\n\`\`\`json\n${rawText}\n\`\`\`\n--- END FILE ---`
  }

  return { displayText, compiledContext }
}

type FigureArtifact = {
  url?: string
  src?: string
  alt?: string
}

type TableArtifact = {
  headers?: unknown[]
  rows?: unknown[][]
}

type EntityArtifact = {
  label?: string
  id?: string
}

type VerdictArtifact = {
  gates?: GateStep[]
  state?: string
  tier?: string
}

type EmbryVoiceListenerProjection = {
  status?: string
  mocked?: boolean
  live?: boolean
  authority?: string
  degraded?: boolean
  transcript?: string
  sessionId?: string
  turnId?: string
  playbackEvidencePresent?: boolean
  missingEvents?: string[]
  missingPlaybackEvents?: string[]
  audio?: {
    path?: string | null
    url?: string | null
    sha256?: string | null
    durationMs?: number | null
    bytes?: number | null
  } | null
  voiceEnvelope?: EmbryVoiceEnvelope | null
  latestReplayableTurn?: {
    status?: string
    mocked?: boolean
    live?: boolean
    authority?: string
    degraded?: boolean
    transcript?: string
    sessionId?: string
    turnId?: string
    sourceContract?: string | null
    playbackEvidencePresent?: boolean
    audio?: {
      path?: string | null
      url?: string | null
      sha256?: string | null
      durationMs?: number | null
      bytes?: number | null
    } | null
    voiceEnvelope?: EmbryVoiceEnvelope | null
  } | null
}

function defaultMediaUrl(path: string): string {
  for (const prefix of WATCH_MEDIA_PREFIXES) {
    const match = `/${prefix}/`
    const idx = path.indexOf(match)
    if (idx === -1) continue
    const suffix = path.slice(idx + match.length)
    const segments = suffix.split('/').map((s) => encodeURIComponent(s)).join('/')
    return `/api/projects/watch/static/${prefix}/${segments}`
  }
  return path
}

function resolveChatDistanceMode(mode?: string): string {
  if (typeof window === 'undefined') return mode ?? '10ft'

  const chatMode = new URLSearchParams(window.location.search).get('chatMode')
  if (chatMode === 'drilldown') return 'lean-in'
  if (chatMode === 'triage') return '5ft'
  if (chatMode === 'glance') return '10ft'
  if (mode === 'lean-in' || mode === '5ft' || mode === '10ft') return mode

  return mode ?? '10ft'
}

const LEAN_IN_PLACEHOLDER_QUERIES = [
  'Why do the legacy checks disagree?',
  'Compile evidence for the degraded pass...',
  'What is blocking the create-qras backlog?',
  'Execute command or query...',
] as const

const TACTICAL_COMMANDS = [
  { cmd: '/analyze', desc: 'Run full payload analysis', roles: ['junior_analyst', 'senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/cve', desc: 'Lookup vulnerability details', roles: ['junior_analyst', 'senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/ip', desc: 'Check IP reputation matrix', roles: ['junior_analyst', 'senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/clear', desc: 'Clear console history', roles: ['junior_analyst', 'senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/blockers', desc: 'Analyze current execution blockers', roles: ['junior_analyst', 'senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/create-evidence-case', desc: 'Compile strict evidence case', roles: ['senior_security_engineer'] },
  { cmd: '/analytics', desc: 'Answer from SPARTA analytics surfaces', roles: ['senior_security_engineer', 'compliance_auditor'] },
  { cmd: '/figure', desc: 'Generate telemetry figure', roles: ['senior_security_engineer'] },
  { cmd: '/update', desc: 'Update source data, for example /update id:ST0001', roles: ['senior_security_engineer'] },
  { cmd: '/delete', desc: 'Drop record from matrix', roles: ['senior_security_engineer'] },
] as const

function highlightComposerDraft(code: string): string {
  const language = code.trim().startsWith('{') || code.trim().startsWith('[') ? 'json' : 'bash'
  const grammar = Prism.languages[language] ?? Prism.languages.plaintext
  return Prism.highlight(code, grammar, language)
}

export function isComposerCodeMode(code: string): boolean {
  const trimmed = code.trim()
  if (!trimmed) return false
  if (/^```[^\n]*\n[\s\S]*\n```$/.test(trimmed)) return true
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return false
  try {
    const parsed = JSON.parse(trimmed)
    return Boolean(parsed) && typeof parsed === 'object'
  } catch {
    return false
  }
}

export function formatJsonPaste(text: string): string | null {
  const trimmed = text.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (!parsed || typeof parsed !== 'object') return null
  } catch {
    return null
  }

  let output = ''
  let indent = 0
  let inString = false
  let escaped = false
  const nextNonWhitespace = (start: number): string => {
    for (let index = start; index < trimmed.length; index += 1) {
      if (!/\s/.test(trimmed[index])) return trimmed[index]
    }
    return ''
  }
  const appendIndent = () => {
    output += '  '.repeat(indent)
  }

  for (let index = 0; index < trimmed.length; index += 1) {
    const char = trimmed[index]
    if (inString) {
      output += char
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') {
      inString = true
      output += char
      continue
    }
    if (/\s/.test(char)) continue
    if (char === '{' || char === '[') {
      output += char
      if (nextNonWhitespace(index + 1) !== (char === '{' ? '}' : ']')) {
        indent += 1
        output += '\n'
        appendIndent()
      }
      continue
    }
    if (char === '}' || char === ']') {
      const previous = output.at(-1)
      if (previous !== '{' && previous !== '[') {
        indent = Math.max(0, indent - 1)
        output += '\n'
        appendIndent()
      }
      output += char
      continue
    }
    if (char === ',') {
      output += ',\n'
      appendIndent()
      continue
    }
    if (char === ':') {
      output += ': '
      continue
    }
    output += char
  }
  return output
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function evidenceCaseFromMemoryAnswerV2Metadata(message: ChatMessage, meta: UnknownRecord): EvidenceCaseData | undefined {
  const memoryAnswer = isRecord(meta.memoryAnswer)
    ? meta.memoryAnswer
    : isRecord(meta.memory_answer)
      ? meta.memory_answer
      : undefined
  if (memoryAnswer?.schema !== 'memory.answer.v2') return undefined

  const admission = isRecord(meta.memoryAnswerV2Admission)
    ? meta.memoryAnswerV2Admission
    : isRecord(meta.memory_answer_v2_admission)
      ? meta.memory_answer_v2_admission
      : undefined
  if (admission && admission.admitted !== true) return undefined

  const answerBlocks = Array.isArray(memoryAnswer.answer_blocks) ? memoryAnswer.answer_blocks : []
  const citations = Array.isArray(memoryAnswer.citations) ? memoryAnswer.citations : []
  const citationRefs = citations
    .map((citation) => isRecord(citation) && typeof citation.canonical_ref === 'string' ? citation.canonical_ref : '')
    .filter(Boolean)
  const status = typeof memoryAnswer.status === 'string' ? memoryAnswer.status : 'insufficient_evidence'
  const answer = typeof admission?.content === 'string' && admission.content.trim()
    ? admission.content.trim()
    : message.content

  return {
    case_id: typeof memoryAnswer.request_id === 'string' ? memoryAnswer.request_id : String(message.id ?? 'memory-answer-v2'),
    verdict: status,
    grade: status === 'answered' ? 'A' : 'I',
    gates_passed: citationRefs.length > 0 ? 2 : 1,
    gates_total: 2,
    gate_summary: citationRefs.length > 0 ? '2/2 gates passed' : '1/2 gates passed',
    gate_trace: [
      { gate: 'memory_answer_contract', passed: true, detail: 'memory.answer.v2' },
      { gate: 'bounded_citations', passed: citationRefs.length > 0, detail: `${citationRefs.length} bounded citation(s)` },
    ],
    control_ids: citationRefs
      .filter(ref => ref.startsWith('sparta_controls/'))
      .map(ref => ref.slice('sparta_controls/'.length)),
    tier: 'memory.answer.v2',
    answer,
    answer_blocks: answerBlocks as EvidenceCaseData['answer_blocks'],
    claims: answerBlocks.map((block) => isRecord(block) ? String(block.text ?? '') : '').filter(Boolean),
    citations: citationRefs,
    memory_answer: memoryAnswer as EvidenceCaseData['memory_answer'],
    response_action: 'answer',
    response_policy: { response_action: 'answer' },
    trace_state: status,
  } as EvidenceCaseData
}

function extractEntitySpansFromMessage(message: ChatMessage, meta: UnknownRecord): EvidenceCaseSpan[] {
  const messageRecord = message as unknown as UnknownRecord
  return entitySpansFromStructuredContext(message.content, [
    messageRecord.entitySpans,
    messageRecord.entity_spans,
    messageRecord.entities,
    messageRecord.evidenceCase,
    meta.entitySpans,
    meta.entity_spans,
    meta.entityContext,
    meta.entity_context,
    meta.extract_entities,
    meta.entities,
    meta.evidenceCase,
    meta.evidence_case,
  ])
}

function firstMetadataString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return undefined
}

function ContentTypeBadge({ type }: { type: string }) {
  if (type === 'evidence') return null
  const badge = CONTENT_TYPE_BADGES[type]
  if (!badge) return null

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 8px',
      borderRadius: 4,
      background: `${badge.color}15`,
      border: `1px solid ${badge.color}30`,
      color: badge.color,
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.03em',
    }}>
      {badge.icon}
      {badge.label}
    </span>
  )
}

function CopyButton({
  content,
  qid = 'shared-chat:code-block:copy',
  action = 'SHARED_CHAT_COPY_CODE_BLOCK',
  title = 'Copy',
  label = 'Copy content',
}: {
  content: string
  qid?: string
  action?: string
  title?: string
  label?: string
}) {
  const [copied, setCopied] = useState(false)
  useRegisterAction(qid, { app: 'shared-chat', action, label, description: `${label} to the clipboard` })

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [content])

  return (
    <ActionTooltip content={copied ? 'Copied' : title}>
      <button
        type="button"
        data-qid={qid}
        data-qs-action={action}
        onClick={handleCopy}
        aria-label={copied ? 'Copied' : title}
        onMouseEnter={(event) => {
          if (!copied) event.currentTarget.style.color = '#58a6ff'
        }}
        onMouseLeave={(event) => {
          if (!copied) event.currentTarget.style.color = '#64748b'
        }}
        style={{
          width: 24,
          height: 24,
          borderRadius: 6,
          border: 0,
          background: 'transparent',
          color: copied ? '#a3a3a3' : '#64748b',
          display: 'grid',
          placeItems: 'center',
          cursor: 'pointer',
        }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </ActionTooltip>
  )
}

function CodeBlock({ code, language = 'text', qid }: { code: string; language?: string; qid?: string }) {
  const lines = code.split('\n')
  const codeBlockQid = qid ?? `shared-chat:code-block:${qidToken(language)}`

  return (
    <div style={{
      background: '#0d0d0d',
      borderRadius: 8,
      border: '1px solid rgba(255,255,255,0.06)',
      overflow: 'hidden',
      margin: '8px 0',
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 12px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(255,255,255,0.02)',
      }}>
        <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
          {language}
        </span>
        <CopyButton
          content={code}
          qid={`${codeBlockQid}:copy`}
          action="SHARED_CHAT_COPY_CODE_BLOCK"
          title={`Copy ${language || 'text'} code block`}
          label="Copy code block"
        />
      </div>
      {/* Code */}
      <div style={{
        padding: '12px',
        overflowX: 'auto',
        fontFamily: 'monospace',
        fontSize: 12,
        lineHeight: 1.6,
      }}>
        {lines.map((line, i) => (
          <div key={i} style={{ display: 'flex', gap: 12 }}>
            <span style={{ color: 'rgba(255,255,255,0.2)', minWidth: 24, textAlign: 'right', userSelect: 'none' }}>
              {i + 1}
            </span>
            <pre style={{ margin: 0, color: '#e2e8f0', whiteSpace: 'pre' }}>{line}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ComplianceChatWell({
  messages = [],
  streamingSteps = [],
  isStreaming = false,
  liveAssistantMessage,
  onSend,
  placeholder = 'Ask a question…',
  disabled = false,
  composerDisabled = false,
  showComposer = true,
  emptyTitle = 'Hello, Graham',
  emptyDescription = 'Ask for compliance evidence, scene context, or PersonaPlex memory.',
  starterChips = [],
  qid = 'shared-chat:compliance-well',
  surface = 'shared-chat',
  className,
  activeBranch,
  sidebar = false,
  recentChats = [],
  promptTemplates = [],
  onDeleteMessage,
  onCopyMessage,
  onDownloadMessage,
  onFeedback,
  mediaUrl,
  activeProcessingTurnId,
  activeProcessingMessageId,
  chatDistanceMode,
  voiceEnabled = false,
  voiceStatus = 'off',
  voiceLabel = 'Voice input',
  onVoiceToggle,
  onRegenerateMessage,
  actionSlot,
  projectLabel,
}: ComplianceChatWellProps): JSX.Element {
  const { user } = useRBAC()
  useRegisterAction(`${qid}:input`, { app: surface, action: 'SHARED_CHAT_EDIT_DRAFT', label: 'Edit chat draft', description: 'Edit the shared chat composer draft' })
  useRegisterAction(`${qid}:attach`, { app: surface, action: 'SHARED_CHAT_OPEN_ATTACH_MENU', label: 'Open attach menu', description: 'Open shared chat attachment options' })
  useRegisterAction(`${qid}:attach-file`, { app: surface, action: 'SHARED_CHAT_ATTACH_FILE', label: 'Attach file', description: 'Open the file attachment path for shared chat' })
  useRegisterAction(`${qid}:attach-log`, { app: surface, action: 'SHARED_CHAT_ATTACH_LOG', label: 'Attach log', description: 'Open the log attachment path for shared chat' })
  useRegisterAction(`${qid}:attach-code`, { app: surface, action: 'SHARED_CHAT_ATTACH_CODE', label: 'Attach code', description: 'Open the code attachment path for shared chat' })
  useRegisterAction(`${qid}:voice`, { app: surface, action: 'SHARED_CHAT_TOGGLE_VOICE', label: 'Toggle voice input', description: 'Toggle shared chat voice input' })
  useRegisterAction(`${qid}:voice-mode`, { app: surface, action: 'SHARED_CHAT_TOGGLE_VOICE_MODE', label: 'Toggle voice mode', description: 'Toggle shared chat voice mode from the waveform composer control' })
  useRegisterAction(`${qid}:send`, { app: surface, action: 'SHARED_CHAT_SEND', label: 'Send chat message', description: 'Send the shared chat composer draft' })
  useRegisterAction(`${qid}:snap-to-present`, { app: surface, action: 'SHARED_CHAT_SNAP_TO_PRESENT', label: 'Snap chat to present', description: 'Scroll the shared chat feed to the newest visible message' })
  useRegisterAction(`${qid}:prompt-template`, { app: surface, action: 'SHARED_CHAT_APPLY_TEMPLATE', label: 'Apply prompt template', description: 'Load a shared chat prompt template into the composer' })

  const [draft, setDraft] = useState('')
  const [hoveredMessage, setHoveredMessage] = useState<string | null>(null)
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const [contextPills, setContextPills] = useState<string[]>([])
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [newMessageCount, setNewMessageCount] = useState(0)
  const compactComposer = sidebar
  const composerHeight = compactComposer ? 78 : COMPOSER_TEXTAREA_DEFAULT_HEIGHT
  const composerMinHeight = compactComposer ? 78 : COMPOSER_TEXTAREA_MIN_HEIGHT
  const composerMaxHeight = compactComposer ? 140 : COMPOSER_TEXTAREA_MAX_HEIGHT
  const composerFontSize = compactComposer ? 15 : COMPOSER_TEXTAREA_FONT_SIZE
  const pendingComposerSelectionRef = useRef<number | null>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const attachMenuRef = useRef<HTMLDivElement>(null)
  const liveTraceSteps = streamingStepsToThinkingTrace(streamingSteps)
  const liveDisclosure = thinkingTraceDisclosureParts({ branch: activeBranch, streamingSteps })
  const resolvedChatDistanceMode = resolveChatDistanceMode(chatDistanceMode)
  const [placeholderIndex, setPlaceholderIndex] = useState(0)
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0)
  const composerInputId = `${qidToken(qid)}-composer-input`
  const composerEditorMode = isComposerCodeMode(draft) ? 'code' : 'conversation'
  const slashCommandDraft = draft.startsWith('/') && !/\s/.test(draft)
  const slashCommandQuery = slashCommandDraft ? draft.slice(1).toLowerCase() : ''
  const permittedCommands = useMemo(() => {
    const role = user.role.toLowerCase()
    const isAdminOverride = user.permissions.includes('*') || role === 'lead_systems_architect'
    return TACTICAL_COMMANDS.filter((command) => isAdminOverride || command.roles.includes(role as never))
  }, [user.permissions, user.role])
  const filteredCommands = useMemo(() => {
    if (!slashCommandDraft) return []
    return permittedCommands.filter((command) => command.cmd.slice(1).includes(slashCommandQuery))
  }, [permittedCommands, slashCommandDraft, slashCommandQuery])
  const showCommandMenu = filteredCommands.length > 0
  const resolvedPlaceholder = resolvedChatDistanceMode === 'lean-in'
    ? LEAN_IN_PLACEHOLDER_QUERIES[placeholderIndex % LEAN_IN_PLACEHOLDER_QUERIES.length]
    : placeholder
  const isHotMic = voiceEnabled && voiceStatus === 'listening'
  const renderedMessages = useMemo(() => {
    if (!liveAssistantMessage) return messages
    return [...messages, liveAssistantMessage]
  }, [liveAssistantMessage, messages])
  const activeTurnStartIndex = useMemo(() => {
    const lastUserIndex = [...renderedMessages].reverse().findIndex((message) => message.role === 'user')
    if (lastUserIndex < 0) return Math.max(0, renderedMessages.length - 1)
    return renderedMessages.length - 1 - lastUserIndex
  }, [renderedMessages])

  useLayoutEffect(() => {
    const input = document.getElementById(composerInputId) as HTMLTextAreaElement | null
    if (!input) return
    input.setAttribute('data-qid', `${qid}:input`)
    input.setAttribute('data-qs-action', 'SHARED_CHAT_EDIT_DRAFT')
    input.setAttribute('title', 'Chat composer input')
    input.setAttribute('aria-disabled', String(disabled || composerDisabled || isStreaming))
    input.style.minHeight = `${composerMinHeight}px`
    input.style.maxHeight = `${composerMaxHeight}px`
    input.style.height = compactComposer ? 'auto' : `${composerHeight}px`
    if (compactComposer) {
      input.style.height = `${Math.min(Math.max(input.scrollHeight, composerMinHeight), composerMaxHeight)}px`
    }
    input.style.overflowY = 'auto'
    if (pendingComposerSelectionRef.current !== null) {
      input.setSelectionRange(pendingComposerSelectionRef.current, pendingComposerSelectionRef.current)
      pendingComposerSelectionRef.current = null
    }
  }, [compactComposer, composerDisabled, composerHeight, composerInputId, composerMaxHeight, composerMinHeight, disabled, draft, isHotMic, isStreaming, qid])

  useEffect(() => {
    if (resolvedChatDistanceMode !== 'lean-in') return undefined
    const interval = window.setInterval(() => {
      setPlaceholderIndex((current) => (current + 1) % LEAN_IN_PLACEHOLDER_QUERIES.length)
    }, 4000)
    return () => window.clearInterval(interval)
  }, [resolvedChatDistanceMode])

  useEffect(() => {
    setSelectedCommandIndex((current) => {
      if (filteredCommands.length === 0) return 0
      return Math.min(current, filteredCommands.length - 1)
    })
  }, [filteredCommands.length])

  // Scroll to bottom on new messages and live streaming updates unless the user
  // has intentionally scrolled away from the present.
  useEffect(() => {
    if (isAtBottom && messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    } else if (renderedMessages.length > 0 || isStreaming) {
      const timer = window.setTimeout(() => setNewMessageCount((prev) => Math.max(1, prev + 1)), 0)
      return () => window.clearTimeout(timer)
    }
    return undefined
  }, [renderedMessages.length, isStreaming, isAtBottom])

  const handleScroll = useCallback(() => {
    if (messagesRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesRef.current
      const atBottom = scrollHeight - scrollTop - clientHeight < 50
      setIsAtBottom(atBottom)
      if (atBottom) setNewMessageCount(0)
    }
  }, [setIsAtBottom, setNewMessageCount])

  async function submit(event?: SyntheticEvent): Promise<void> {
    event?.preventDefault()
    const text = draft.trim()
    if ((!text && pendingFiles.length === 0) || disabled || composerDisabled || !onSend) return
    const submittedFiles = [...pendingFiles]
    const { displayText, compiledContext } = await compileAttachmentPayload(text, submittedFiles)
    setDraft('')
    setPendingFiles([])
    setFileError('')
    setSelectedCommandIndex(0)
    setContextPills([])
    await onSend(displayText, 'Auto', submittedFiles, { compiledContext })
  }

  const executeComposerText = useCallback((text: string) => {
    const normalizedText = text.trim()
    if ((!normalizedText && pendingFiles.length === 0) || disabled || composerDisabled || !onSend) return
    const submittedFiles = [...pendingFiles]
    setDraft('')
    setPendingFiles([])
    setFileError('')
    setSelectedCommandIndex(0)
    setContextPills([])
    void compileAttachmentPayload(normalizedText, submittedFiles).then(({ displayText, compiledContext }) => {
      void onSend(displayText, 'Auto', submittedFiles, { compiledContext })
    })
  }, [composerDisabled, disabled, onSend, pendingFiles])

  const handleFileUpload = useCallback(async (files: File[]) => {
    setFileError('')
    const accepted: File[] = []
    const rejected: string[] = []
    for (const file of files) {
      if (file.size > MAX_ATTACHMENT_BYTES) {
        rejected.push(`${file.name} (exceeds 5MB)`)
        continue
      }
      const extension = attachmentExtension(file.name)
      if (isJsonAttachment(file)) {
        try {
          JSON.parse(await file.text())
          accepted.push(file)
        } catch {
          rejected.push(`${file.name} (Invalid JSON Syntax)`)
        }
        continue
      }
      if (ALLOWED_ATTACHMENT_MIME_TYPES.has(file.type) || ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)) {
        accepted.push(file)
        continue
      }
      rejected.push(file.name)
    }
    if (accepted.length > 0) {
      setPendingFiles((current) => {
        const existing = new Set(current.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
        return [
          ...current,
          ...accepted.filter((file) => !existing.has(`${file.name}:${file.size}:${file.lastModified}`)),
        ]
      })
    }
    if (rejected.length > 0) {
      setFileError(`Rejected: ${rejected.join(', ')}`)
      window.setTimeout(() => setFileError(''), 5000)
    }
  }, [])

  const openFilePicker = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = true
    input.setAttribute('aria-hidden', 'true')
    input.style.position = 'fixed'
    input.style.left = '-9999px'
    input.style.top = '-9999px'
    input.addEventListener('change', () => {
      void handleFileUpload(Array.from(input.files ?? []))
      input.remove()
    }, { once: true })
    document.body.appendChild(input)
    input.click()
  }, [handleFileUpload])

  const handleRemoveFile = useCallback((indexToRemove: number) => {
    setPendingFiles((current) => current.filter((_, index) => index !== indexToRemove))
  }, [])

  const handleComposerDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(true)
  }, [])

  const handleComposerDragLeave = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragActive(false)
  }, [])

  const handleComposerDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
  }, [])

  const handleComposerDrop = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(false)
    void handleFileUpload(Array.from(event.dataTransfer.files ?? []))
  }, [handleFileUpload])

  const handleComposerPaste = useCallback((event: React.ClipboardEvent<HTMLDivElement>) => {
    if (Array.from(event.clipboardData.items).some((item) => item.kind === 'file')) return
    const formatted = formatJsonPaste(event.clipboardData.getData('text/plain'))
    if (formatted === null) return
    const input = event.target
    if (!(input instanceof HTMLTextAreaElement)) return

    event.preventDefault()
    const start = input.selectionStart
    const end = input.selectionEnd
    pendingComposerSelectionRef.current = start + formatted.length
    setDraft(`${draft.slice(0, start)}${formatted}${draft.slice(end)}`)
  }, [draft])

  const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement | HTMLDivElement>) => {
    if (showCommandMenu) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSelectedCommandIndex((current) => (current + 1) % filteredCommands.length)
        return
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSelectedCommandIndex((current) => (current - 1 + filteredCommands.length) % filteredCommands.length)
        return
      }
      if (event.key === 'Tab' || event.key === 'Enter') {
        event.preventDefault()
        const selectedCommand = filteredCommands[selectedCommandIndex]
        if (selectedCommand) {
          setDraft(`${selectedCommand.cmd} `)
          setSelectedCommandIndex(0)
          window.setTimeout(() => document.getElementById(composerInputId)?.focus(), 0)
        }
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setSelectedCommandIndex(0)
        setDraft('')
        return
      }
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      executeComposerText(draft)
    }
  }

  const handleRemoveContextPill = (pill: string) => {
    setContextPills(contextPills.filter(p => p !== pill))
  }

  const handleTemplateClick = (template: string) => {
    setDraft(template)
    window.setTimeout(() => document.getElementById(composerInputId)?.focus(), 0)
  }

  const handleStarterChip = (prompt: string) => {
    setDraft(prompt)
    void onSend?.(prompt, 'Auto')
  }

  const replayPromptForMessage = useCallback((messageIndex: number): string | null => {
    for (let index = messageIndex - 1; index >= 0; index -= 1) {
      const candidate = renderedMessages[index]
      if (candidate?.role === 'user' && candidate.content.trim()) return candidate.content.trim()
    }
    return null
  }, [renderedMessages])

  const handleRegenerateMessage = useCallback((prompt: string) => {
    if (isStreaming || disabled || composerDisabled) return
    if (onRegenerateMessage) {
      void onRegenerateMessage(prompt)
      return
    }
    void onSend?.(prompt, 'Auto')
  }, [composerDisabled, disabled, isStreaming, onRegenerateMessage, onSend])

  return (
    <section
      className={className}
      data-qid={qid}
      data-surface={surface}
      data-variant={sidebar ? 'sidebar' : 'full'}
      data-chat-distance-mode={resolvedChatDistanceMode}
      style={{
        minHeight: 0,
        height: '100%',
        display: 'grid',
        gridTemplateRows: 'minmax(0, 1fr) auto',
        background: 'transparent',
        color: '#e2e8f0',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* No internal header — SharedChatPage owns the header. Duplicates removed. */}

      {/* Messages area */}
      <div
        ref={messagesRef}
        data-qid={`${qid}:messages`}
        onScroll={handleScroll}
        style={{
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: sidebar ? 0 : '12px 28px 180px',
          display: 'flex',
          flexDirection: 'column',
          gap: sidebar ? 0 : 12,
          position: 'relative',
          scrollBehavior: 'smooth',
          background: sidebar ? 'var(--surface-deep)' : undefined,
        }}
      >
        {renderedMessages.length === 0 && !isStreaming ? (
          <EmptyState
            title={emptyTitle}
            description={emptyDescription}
            chips={starterChips}
            onChip={(prompt) => { setDraft(prompt); void onSend?.(prompt) }}
            sidebar={sidebar}
            recentChats={recentChats}
            promptTemplates={promptTemplates}
            surface={surface}
            chatDistanceMode={resolvedChatDistanceMode}
            voiceStatus={voiceStatus}
            voiceLabel={voiceLabel}
            onTemplateClick={handleTemplateClick}
          />
        ) : (
	          renderedMessages.map((message, index) => {
	            const messageId = message.id ?? `message-${index}`
	            const contentType = detectContentType(message)
	            const roleColor = getRoleColor(message)
	            const isHovered = hoveredMessage === messageId
              const replayPrompt = message.role === 'user' ? null : replayPromptForMessage(index)

            const meta = (message.metadata ?? {}) as UnknownRecord
            const turnId = typeof meta.turnId === 'string' ? meta.turnId : undefined
            const isReceiptProcessing = Boolean(
              isStreaming && (
                (activeProcessingTurnId && turnId === activeProcessingTurnId)
                || (activeProcessingMessageId && messageId === activeProcessingMessageId)
              ),
            )

            return (
              <DashboardMessageBubble
                agentLabel={projectLabel}
	                key={messageId}
                message={message}
                index={index}
                isReceiptProcessing={isReceiptProcessing}
                isHovered={isHovered}
	                onHover={() => setHoveredMessage(messageId)}
	                onLeave={() => setHoveredMessage(null)}
	                onDelete={onDeleteMessage ? () => onDeleteMessage(messageId) : undefined}
	                onCopy={onCopyMessage ? () => onCopyMessage(messageId) : undefined}
                onDownload={onDownloadMessage ? () => onDownloadMessage(messageId) : undefined}
                onFeedback={onFeedback}
                onRegenerate={replayPrompt ? () => handleRegenerateMessage(replayPrompt) : undefined}
                regenerateDisabled={isStreaming || disabled || composerDisabled}
                contentType={contentType}
                roleColor={roleColor}
                sidebar={sidebar}
                mediaUrl={mediaUrl}
                isHistoricalTurn={sidebar && index < activeTurnStartIndex}
              />
            )
          })
        )}

        {/* Thinking indicator */}
        {isStreaming && (
          resolvedChatDistanceMode === 'lean-in' ? (
	            <div style={{
	              margin: '2px 0 32px',
	              fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
	              minWidth: 0,
	            }}>
	              <div style={{ minWidth: 0 }}>
                <ConsoleExecutionTraceLog
                  steps={liveTraceSteps}
                  receiptId={activeProcessingTurnId ?? activeProcessingMessageId ?? undefined}
                  isGenerating
                />
              </div>
            </div>
          ) : (
            <ThinkingTrace
              steps={liveTraceSteps}
              title={liveDisclosure.title}
              label={liveDisclosure.label}
              currentLabel={liveDisclosure.liveStatusLabel}
              disclosureVariant={liveDisclosure.disclosureVariant}
              leadingIcon={liveDisclosure.leadingIcon}
              placement="header"
              displayMode="full"
              isStreaming={isStreaming}
              dataQid="shared-chat:live-thinking-trace"
            />
          )
        )}

      </div>

      {actionSlot ?? null}

      {/* Composer — sticky bottom, gold-standard density */}
      {showComposer && (
        <div
          data-qid={`${qid}:composer`}
          style={{
            padding: compactComposer ? 12 : '12px 16px 16px',
            position: 'sticky',
            bottom: 0,
            background: compactComposer ? 'var(--surface-deep)' : '#101014',
            borderTop: compactComposer ? '1px solid #1f2937' : undefined,
            flexShrink: 0,
            zIndex: 20,
          }}
        >
          {isHotMic ? (
            <VoiceRecordingState
              onAbort={() => onVoiceToggle?.(false)}
              onTransmit={() => {
                onVoiceToggle?.(false)
                executeComposerText(draft)
              }}
            />
          ) : (
            <>
          {sidebar && renderedMessages.length > 0 && starterChips.length > 0 && (
            <QuickActionChips
              chips={starterChips}
              onChip={handleStarterChip}
              disabled={disabled || composerDisabled || isStreaming || !onSend}
            />
          )}

          {/* Context attachment pill — Gemini style */}
          {contextPills.length > 0 && (
            <div
              style={{
                display: 'flex',
                gap: 6,
                marginBottom: 8,
                marginLeft: 6,
                flexWrap: 'wrap',
              }}
            >
              {contextPills.map((pill) => (
                <span
                  key={pill}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    height: 36,
                    padding: '0 12px',
                    borderRadius: 14,
                    background: '#202127',
                    color: '#a5a8b3',
                    fontSize: 12,
                    border: 0,
                  }}
                >
                  <span>Sharing "{pill}"</span>
                  <button
                    type="button"
                    data-qid={`${qid}:context-pill:${pill}:remove`}
                    data-qs-action="SHARED_CHAT_REMOVE_CONTEXT_PILL"
                    title={`Remove shared context ${pill}`}
                    onClick={() => handleRemoveContextPill(pill)}
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: 4,
                      border: 0,
                      background: 'transparent',
                      color: '#7f8798',
                      display: 'grid',
                      placeItems: 'center',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {showCommandMenu && (
            <div
              data-qid={`${qid}:command-menu`}
              aria-label="Shared chat command autocomplete"
              style={{
                position: 'absolute',
                bottom: 'calc(100% - 4px)',
                left: 16,
                right: 16,
                marginBottom: 8,
                backgroundColor: 'var(--surface-base)',
                border: '1px solid var(--border-default)',
                borderRadius: 4,
                boxShadow: '0 -4px 16px rgba(0,0,0,0.8)',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                zIndex: 50,
                minWidth: 0,
                maxWidth: 'calc(100vw - 32px)',
              }}
            >
              {filteredCommands.map((command, index) => {
                const isSelected = index === selectedCommandIndex
                return (
                  <button
                    key={command.cmd}
                    type="button"
                    data-qid={`${qid}:command-menu:${command.cmd.slice(1)}`}
                    data-qs-action="SHARED_CHAT_EXECUTE_COMMAND_AUTOCOMPLETE"
                    title={`Execute ${command.cmd}`}
                    onMouseEnter={() => setSelectedCommandIndex(index)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => {
                      setDraft(`${command.cmd} `)
                      setSelectedCommandIndex(0)
                      window.setTimeout(() => document.getElementById(composerInputId)?.focus(), 0)
                    }}
                    style={{
                      minHeight: 44,
                      width: '100%',
                      minWidth: 0,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '8px 12px',
                      backgroundColor: isSelected ? 'var(--surface-raised)' : 'transparent',
                      border: 0,
                      borderLeft: isSelected ? '2px solid #00cc00' : '2px solid transparent',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ color: isSelected ? '#00cc00' : 'var(--text-primary)', fontFamily: '"SF Mono", Consolas, monospace', fontSize: 11, fontWeight: 800 }}>
                      {command.cmd}
                    </span>
                    <span style={{ flex: 1, minWidth: 0, color: 'var(--text-muted)', fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {command.desc}
                    </span>
                    {isSelected && (
                      <span style={{ color: '#484f58', fontSize: 9, fontFamily: '"SF Mono", Consolas, monospace', whiteSpace: 'nowrap', flexShrink: 0 }}>
                        [TAB] TO EXECUTE
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {fileError && (
            <div
              data-qid={`${qid}:file-error`}
              style={{
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                color: '#ff7b72',
                fontSize: 12,
                padding: '0 4px',
              }}
            >
              <AlertTriangle size={14} aria-hidden="true" />
              <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fileError}</span>
            </div>
          )}

          {/* Minimalist assistant composer shell */}
          <div
            onDragEnter={handleComposerDragEnter}
            onDragLeave={handleComposerDragLeave}
            onDragOver={handleComposerDragOver}
            onDrop={handleComposerDrop}
            style={{
              background: compactComposer ? 'var(--surface-raised)' : '#0A0A0A',
              borderRadius: compactComposer ? 2 : 12,
              padding: pendingFiles.length > 0 ? '10px 12px 12px' : compactComposer ? 6 : '0 8px',
              border: `1px solid ${isDragActive ? '#3b82f6' : fileError ? 'rgba(248, 81, 73, 0.55)' : compactComposer ? '#374151' : '#333'}`,
              boxShadow: compactComposer ? 'inset 0 1px 0 rgba(255,255,255,0.03)' : '0 4px 24px rgba(0,0,0,0.5)',
              display: 'flex',
              flexDirection: 'column',
              gap: pendingFiles.length > 0 ? 10 : 0,
              position: 'relative',
              transition: 'border-color 0.2s ease',
              minWidth: 0,
              width: '100%',
            }}
          >
            {!isAtBottom && newMessageCount > 0 && (
              <button
                type="button"
                data-qid={`${qid}:snap-to-present`}
                data-qs-action="SHARED_CHAT_SNAP_TO_PRESENT"
                title="Snap to present"
                style={{
                  position: 'absolute',
                  top: -28,
                  right: 8,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  minHeight: 26,
                  padding: '5px 10px',
                  borderRadius: 999,
                  border: '1px solid rgba(125, 211, 252, 0.22)',
                  background: 'rgba(15, 23, 42, 0.92)',
                  color: '#7dd3fc',
                  fontSize: 11,
                  cursor: 'pointer',
                  boxShadow: '0 8px 20px rgba(0,0,0,0.32)',
                  fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
                }}
                onClick={() => {
                  if (messagesRef.current) {
                    messagesRef.current.scrollTop = messagesRef.current.scrollHeight
                    setNewMessageCount(0)
                    setIsAtBottom(true)
                  }
                }}
              >
                <ArrowDown size={12} />
                <span>Snap to present</span>
              </button>
            )}
            {pendingFiles.length > 0 && (
              <div
                data-qid={`${qid}:pending-files`}
                className="terminal-scrollbar"
                style={{
                  maxHeight: 96,
                  overflowY: 'auto',
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 6,
                  paddingBottom: 8,
                  borderBottom: '1px solid #222',
                  width: '100%',
                  minWidth: 0,
                  overflowX: 'hidden',
                }}
              >
                {pendingFiles.map((file, index) => (
                  <FileChip
                    key={`${file.name}:${file.size}:${file.lastModified}:${index}`}
                    file={file}
                    disabled={disabled || composerDisabled || isStreaming}
                    onRemove={() => handleRemoveFile(index)}
                  />
                ))}
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: compactComposer ? 8 : 0, width: '100%', minWidth: 0 }}>
              <div style={{ position: 'relative', flexShrink: 0, marginBottom: compactComposer ? 2 : 4 }} ref={attachMenuRef}>
                <button
                  type="button"
	                  data-qid={`${qid}:attach`}
	                  data-qs-action="SHARED_CHAT_OPEN_ATTACH_MENU"
	                  title="Add files or tools"
	                  aria-disabled={disabled || composerDisabled || isStreaming}
	                  onClick={(event) => {
	                    if (disabled || composerDisabled || isStreaming) {
	                      event.preventDefault()
	                      return
	                    }
	                    setShowAttachMenu(!showAttachMenu)
	                  }}
                  style={{
                    width: compactComposer ? 28 : 48,
                    height: compactComposer ? 28 : 48,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'transparent',
                    border: 0,
                    color: '#888',
                    cursor: disabled || composerDisabled || isStreaming ? 'not-allowed' : 'pointer',
                    padding: 0,
                    borderRadius: compactComposer ? 4 : 0,
                    transition: 'color 0.2s',
                  }}
                  onMouseEnter={(event) => {
                    event.currentTarget.style.color = '#FFF'
                  }}
                  onMouseLeave={(event) => {
                    event.currentTarget.style.color = '#888'
                  }}
                >
                  <Plus size={compactComposer ? 16 : 19} strokeWidth={1.8} />
                </button>
                {showAttachMenu && (
                  <div style={{
                    position: 'absolute',
                    bottom: 'calc(100% + 8px)',
                    left: 0,
                    width: 180,
                    background: '#0A0A0A',
                    borderRadius: 8,
                    border: '1px solid #333',
                    boxShadow: '0 10px 40px rgba(0,0,0,0.4)',
                    zIndex: 100,
                    padding: '6px 0',
                  }}>
                  <button
                    type="button"
                    data-qid={`${qid}:attach-file`}
                    data-qs-action="SHARED_CHAT_ATTACH_FILE"
                    title="Attach file"
                    onClick={() => {
                      setShowAttachMenu(false)
                      openFilePicker()
                    }}
                    style={attachMenuItemStyle}
                  >
                    <FileText size={14} />
                    <span>File</span>
                  </button>
                  <button
                    type="button"
                    data-qid={`${qid}:attach-log`}
                    data-qs-action="SHARED_CHAT_ATTACH_LOG"
                    title="Attach log"
                    style={attachMenuItemStyle}
                  >
                    <FileText size={14} />
                    <span>Log</span>
                  </button>
                  <button
                    type="button"
                    data-qid={`${qid}:attach-code`}
                    data-qs-action="SHARED_CHAT_ATTACH_CODE"
                    title="Attach code"
                    style={attachMenuItemStyle}
                  >
                    <Code size={14} />
                    <span>Code</span>
                  </button>
                </div>
              )}
              </div>
              <div
                className="forensic-chat-code-editor"
                data-qid={`${qid}:input-shell`}
                title="Chat composer editor shell"
                data-editor-mode={composerEditorMode}
                data-compact-composer={compactComposer ? 'true' : 'false'}
                onPaste={handleComposerPaste}
                style={{
                  flex: 1,
                  height: compactComposer ? 'auto' : composerHeight,
                  minHeight: composerMinHeight,
                  maxHeight: composerMaxHeight,
                  minWidth: 0,
                  overflowY: 'auto',
                }}
              >
	                <Editor
	                  value={draft}
	                  onValueChange={(nextValue) => {
	                    if (disabled || composerDisabled || isStreaming) return
	                    setDraft(nextValue)
	                  }}
	                  highlight={highlightComposerDraft}
	                  onKeyDown={handleComposerKeyDown}
	                  placeholder={pendingFiles.length > 0 ? 'Add context or send attached files...' : resolvedPlaceholder}
	                  textareaId={composerInputId}
                  textareaClassName="forensic-chat-composer-input forensic-chat-code-editor__textarea"
                  preClassName="forensic-chat-code-editor__pre"
                  padding={compactComposer ? 6 : 12}
                  style={{
                    minHeight: composerHeight,
                    maxHeight: composerMaxHeight,
                    fontSize: composerFontSize,
                    lineHeight: compactComposer ? '22px' : '24px',
                    color: '#EDEDED',
                  }}
                />
              </div>

              <div
                data-qid={`${qid}:composer-actions`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: compactComposer ? 4 : 6,
                  paddingLeft: compactComposer ? 0 : 8,
                  flexShrink: 0,
                  marginBottom: compactComposer ? 2 : 4,
                }}
              >
                {onVoiceToggle && (
                  <button
                    type="button"
	                    data-qid={`${qid}:voice-mode`}
	                    data-qs-action="SHARED_CHAT_TOGGLE_VOICE_MODE"
	                    aria-pressed={voiceEnabled}
	                    aria-disabled={disabled || composerDisabled || isStreaming}
	                    title={voiceEnabled ? `Disable ${voiceLabel}` : `Enable ${voiceLabel}`}
	                    onClick={(event) => {
	                      if (disabled || composerDisabled || isStreaming) {
	                        event.preventDefault()
	                        return
	                      }
	                      onVoiceToggle(!voiceEnabled)
	                    }}
                    style={{
                      width: compactComposer ? 28 : 32,
                      height: compactComposer ? 28 : 32,
                      borderRadius: compactComposer ? 4 : 8,
                      border: 0,
                      background: 'transparent',
                      color: voiceEnabled ? '#0070F3' : '#888',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: disabled || composerDisabled || isStreaming ? 'not-allowed' : 'pointer',
                      opacity: disabled || composerDisabled || isStreaming ? 0.45 : 1,
                      transition: 'color 0.2s, opacity 0.2s',
                    }}
                  >
                    <Mic size={compactComposer ? 16 : 17} strokeWidth={1.9} />
                  </button>
                )}

                <button
                  type="button"
                  data-qid={`${qid}:send`}
                  data-qs-action="SHARED_CHAT_SEND"
                  aria-disabled={disabled || composerDisabled || isStreaming || (!draft.trim() && pendingFiles.length === 0)}
                  title={draft.trim() || pendingFiles.length > 0 ? 'Send' : 'Enter a message or attach a file before sending'}
                  onClick={(event) => {
                    if (disabled || composerDisabled || isStreaming || (!draft.trim() && pendingFiles.length === 0)) {
                      event.preventDefault()
                      return
                    }
                    void submit(event)
                  }}
                  style={{
                    width: compactComposer ? 28 : 32,
                    height: compactComposer ? 28 : 32,
                    borderRadius: compactComposer ? 4 : 8,
                    border: 0,
                    background: (draft.trim() || pendingFiles.length > 0) && !isStreaming ? '#EDEDED' : 'transparent',
                    color: (draft.trim() || pendingFiles.length > 0) && !isStreaming ? '#000' : '#525252',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: (draft.trim() || pendingFiles.length > 0) && !isStreaming ? 'pointer' : 'not-allowed',
                    transition: 'opacity 0.2s',
                  }}
                >
                  <CornerDownLeft size={compactComposer ? 15 : 16} strokeWidth={2} />
                </button>
              </div>
            </div>
            {isDragActive && (
              <div
                data-qid={`${qid}:drop-overlay`}
                style={{
                  position: 'absolute',
                  inset: 0,
                  borderRadius: 12,
                  background: 'rgba(5, 5, 5, 0.86)',
                  border: '2px dashed #0070F3',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#58A6FF',
                  fontSize: 13,
                  fontWeight: 650,
                  pointerEvents: 'none',
                  zIndex: 20,
                }}
              >
                Drop file to attach
              </div>
            )}
          </div>
            </>
	        )}
	      </div>
	    )}

      {/* CSS */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        @keyframes shared-chat-idle-voice-timer {
          0% { transform: scaleX(0); opacity: 0.18; }
          12% { opacity: 0.56; }
          100% { transform: scaleX(1); opacity: 0.56; }
        }
        .markdown-table-wrapper { overflow-x: auto; }
        .markdown-table-wrapper table { width: 100%; border-collapse: collapse; font-size: 12px; }
        .markdown-table-wrapper th, .markdown-table-wrapper td { padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); white-space: nowrap; }
        .markdown-table-wrapper th { background: rgba(255,255,255,0.04); color: #a5a8b3; font-weight: 600; text-align: left; }
        .chat-prose--sidebar .chat-prose-table {
          max-width: 100%;
          overflow-x: auto;
          padding-bottom: 4px;
        }
        .chat-prose--sidebar .chat-prose-table table {
          width: max-content;
          min-width: min(680px, 170vw);
          table-layout: auto;
          border-collapse: collapse;
        }
        .chat-prose--sidebar .chat-prose-table th,
        .chat-prose--sidebar .chat-prose-table td {
          padding: 8px 10px;
          font-size: 11px;
          line-height: 1.4;
          white-space: normal;
          overflow-wrap: break-word;
          word-break: normal;
          vertical-align: top;
          min-width: 150px;
          max-width: 340px;
        }
        .chat-prose--sidebar .chat-prose-table table:has(th:nth-child(2):last-child) th:last-child,
        .chat-prose--sidebar .chat-prose-table table:has(td:nth-child(2):last-child) td:last-child {
          width: 72px;
          text-align: right;
          white-space: nowrap;
        }
        .chat-structured-table .chat-prose-table {
          max-width: 100%;
          overflow-x: auto;
          padding-bottom: 4px;
        }
        .chat-structured-table .chat-prose-table table {
          width: max-content;
          min-width: min(720px, 180vw);
          table-layout: auto;
          border-collapse: collapse;
        }
        .chat-structured-table .chat-prose-table th,
        .chat-structured-table .chat-prose-table td {
          padding: 8px 10px;
          font-size: 11px;
          line-height: 1.4;
          white-space: normal;
          overflow-wrap: break-word;
          word-break: normal;
          vertical-align: top;
          min-width: 160px;
          max-width: 360px;
        }
        .chat-structured-table .chat-prose-table th:first-child,
        .chat-structured-table .chat-prose-table td:first-child {
          min-width: 72px;
          max-width: 90px;
          width: 78px;
          text-align: right;
          white-space: nowrap;
        }
      `}</style>
    </section>
  )
}

const attachMenuItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  minHeight: 44,
  padding: '10px 14px',
  border: 0,
  background: 'transparent',
  color: '#e2e8f0',
  fontSize: 13,
  cursor: 'pointer',
  textAlign: 'left',
}

function QuickActionChips({
  chips,
  onChip,
  disabled,
}: {
  chips: StarterChip[]
  onChip: (prompt: string) => void
  disabled: boolean
}): JSX.Element {
  return (
    <div
      className="chat-quick-actions"
      data-qid="shared-chat:quick-actions"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        overflowX: 'auto',
        padding: '0 0 8px',
        scrollbarWidth: 'none',
      }}
    >
      {chips.slice(0, 3).map((chip) => (
        <button
          key={chip.label}
          type="button"
          data-qid={chip.dataQid ?? `shared-chat:quick-action:${qidToken(chip.label)}`}
          data-qs-action={chip.action ?? 'SHARED_CHAT_QUICK_ACTION'}
          title={chip.title ?? `Ask: ${chip.label}`}
          onClick={() => onChip(chip.prompt)}
          disabled={disabled}
          className="chat-quick-actions__chip"
          style={{
            flex: '0 0 auto',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            border: '1px solid rgba(148, 163, 184, 0.16)',
            borderRadius: 999,
            background: 'rgba(255, 255, 255, 0.04)',
            color: '#b8c2d0',
            padding: '6px 9px',
            fontSize: 11,
            lineHeight: 1,
            cursor: disabled ? 'not-allowed' : 'pointer',
            opacity: disabled ? 0.45 : 1,
            whiteSpace: 'nowrap',
          }}
        >
          {chip.icon}
          <span>{chip.label}</span>
        </button>
      ))}
    </div>
  )
}

function EmptyState({
  title,
  description,
  chips,
  onChip,
  sidebar,
  recentChats,
  promptTemplates,
  surface,
  chatDistanceMode,
  voiceStatus,
  voiceLabel,
  onTemplateClick,
}: {
  title: string
  description: string
  chips: StarterChip[]
  onChip: (prompt: string) => void
  sidebar?: boolean
  recentChats?: { id: string; title: string; timestamp: number }[]
  promptTemplates?: string[]
  surface?: string
  chatDistanceMode?: string
  voiceStatus?: 'off' | 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
  voiceLabel?: string
  onTemplateClick?: (template: string) => void
}): JSX.Element {
  const voicePrompts = useMemo(() => [
    { label: 'What blocks readiness?', prompt: 'What blocks readiness?', qid: 'shared-chat:idle-voice:readiness', action: 'SHARED_CHAT_IDLE_ASK_READINESS' },
    { label: 'Open QRA review queue', prompt: 'Open QRA review queue', qid: 'shared-chat:idle-voice:qras', action: 'SHARED_CHAT_IDLE_OPEN_QRAS' },
    { label: 'Show Coverage', prompt: 'Show Coverage', qid: 'shared-chat:idle-voice:coverage', action: 'SHARED_CHAT_IDLE_SHOW_COVERAGE' },
    { label: 'Show URLs', prompt: 'Show URLs', qid: 'shared-chat:idle-voice:urls', action: 'SHARED_CHAT_IDLE_SHOW_URLS' },
    { label: 'Show Global Posture', prompt: 'Show Global Posture', qid: 'shared-chat:idle-voice:posture', action: 'SHARED_CHAT_IDLE_SHOW_POSTURE' },
    { label: 'Open top blocker', prompt: 'Open top blocker', qid: 'shared-chat:idle-voice:top-blocker', action: 'SHARED_CHAT_IDLE_OPEN_TOP_BLOCKER' },
  ], [])
  const [voicePromptIndex, setVoicePromptIndex] = useState(0)
  const [voiceProjection, setVoiceProjection] = useState<EmbryVoiceListenerProjection | null>(null)
  const [voiceProjectionError, setVoiceProjectionError] = useState<string | null>(null)
  const replayableAudioRef = useRef<HTMLAudioElement | null>(null)
  const [replayableAudioElement, setReplayableAudioElement] = useState<HTMLAudioElement | null>(null)
  const [replayableAudioPlaying, setReplayableAudioPlaying] = useState(false)
  const [replayableSpeechStartedAtMs, setReplayableSpeechStartedAtMs] = useState<number | undefined>(undefined)
  const showSpartaLeanInIdle = surface === 'sparta-explorer' && chatDistanceMode === 'lean-in'
  const showSpartaVoiceIdle = surface === 'sparta-explorer' && !showSpartaLeanInIdle
  const activeVoicePrompt = voicePrompts[voicePromptIndex % voicePrompts.length]
  const latestReplayableTurn = voiceProjection?.latestReplayableTurn ?? null
  const latestReplayableAudioSrc = latestReplayableTurn?.audio?.url
    ? resolveVoiceAudioSrc(latestReplayableTurn.audio.url, defaultMediaUrl)
    : null
  const orbVoiceStatus = replayableAudioPlaying ? 'speaking' : voiceStatus ?? 'off'
  const bindReplayableAudioRef = useCallback((element: HTMLAudioElement | null) => {
    replayableAudioRef.current = element
    setReplayableAudioElement(element)
  }, [])
  const markReplayableAudioActive = useCallback((audio: HTMLAudioElement | null) => {
    if (!audio) return
    const currentTime = audio.currentTime ?? 0
    setReplayableSpeechStartedAtMs(performance.now() - currentTime * 1000)
    setReplayableAudioPlaying(!audio.paused)
  }, [])
  const markReplayableAudioInactive = useCallback(() => {
    setReplayableAudioPlaying(false)
  }, [])
  const playLatestReplayableAudio = useCallback(() => {
    const audio = replayableAudioRef.current
    if (!audio || !latestReplayableAudioSrc) return
    audio.currentTime = 0
    setReplayableSpeechStartedAtMs(performance.now())
    setReplayableAudioPlaying(true)
    void audio.play().catch(() => {
      setReplayableAudioPlaying(false)
      setReplayableSpeechStartedAtMs(undefined)
    })
  }, [latestReplayableAudioSrc])

  useRegisterAction('shared-chat:idle-voice:readiness', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_ASK_READINESS', label: 'Ask what blocks readiness', description: 'Ask Console what currently blocks readiness' })
  useRegisterAction('shared-chat:idle-voice:qras', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_OPEN_QRAS', label: 'Open QRA review queue', description: 'Ask Console to open the QRA review queue' })
  useRegisterAction('shared-chat:idle-voice:coverage', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_SHOW_COVERAGE', label: 'Show Coverage', description: 'Ask Console to show Coverage' })
  useRegisterAction('shared-chat:idle-voice:urls', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_SHOW_URLS', label: 'Show URLs', description: 'Ask Console to show URLs' })
  useRegisterAction('shared-chat:idle-voice:posture', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_SHOW_POSTURE', label: 'Show Global Posture', description: 'Ask Console to show Global Posture' })
  useRegisterAction('shared-chat:idle-voice:top-blocker', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_OPEN_TOP_BLOCKER', label: 'Open top blocker', description: 'Ask Console to open the current top blocker' })
  useRegisterAction('shared-chat:idle-voice-replay', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_REPLAY_LATEST_LISTENER', label: 'Replay latest listener audio', description: 'Replay the latest listener turn when playback evidence exists' })
  useRegisterAction('shared-chat:idle-voice-replayable-audio', { app: surface ?? 'shared-chat', action: 'SHARED_CHAT_IDLE_PLAY_REPLAYABLE_AUDIO', label: 'Play replayable Chatterbox audio', description: 'Play the latest complete journaled Chatterbox voice turn' })

  useEffect(() => {
    if (!showSpartaVoiceIdle) return undefined
    const interval = window.setInterval(() => {
      setVoicePromptIndex((current) => (current + 1) % voicePrompts.length)
    }, 7000)
    return () => window.clearInterval(interval)
  }, [showSpartaVoiceIdle, voicePrompts.length])

  useEffect(() => {
    if (!showSpartaVoiceIdle) return undefined
    let cancelled = false
    async function loadVoiceProjection(): Promise<void> {
      try {
        setVoiceProjectionError(null)
        const response = await fetch('/api/projects/embry-voice/listener/latest', { cache: 'no-store' })
        const payload = await response.json().catch(() => null) as EmbryVoiceListenerProjection | { error?: string } | null
        if (!response.ok) {
          const message = payload && 'error' in payload && typeof payload.error === 'string'
            ? payload.error
            : `Voice journal projection failed with HTTP ${response.status}`
          throw new Error(message)
        }
        if (!cancelled) setVoiceProjection(payload as EmbryVoiceListenerProjection)
      } catch (error) {
        if (!cancelled) {
          setVoiceProjection(null)
          setVoiceProjectionError(error instanceof Error ? error.message : String(error))
        }
      }
    }
    void loadVoiceProjection()
    const interval = window.setInterval(() => { void loadVoiceProjection() }, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [showSpartaVoiceIdle])

  useEffect(() => {
    setReplayableAudioPlaying(false)
    setReplayableSpeechStartedAtMs(undefined)
  }, [latestReplayableAudioSrc])

  if (showSpartaLeanInIdle) {
    return (
      <EmbryEmptyState
        voiceStatus={voiceStatus}
        onExecute={onChip}
        promptTemplates={promptTemplates}
        onTemplateClick={onTemplateClick}
      />
    )
  }

  return (
    <div
      data-qid="shared-chat:empty"
      style={{
        margin: 'auto',
        maxWidth: sidebar ? 320 : 560,
        textAlign: 'center',
        padding: sidebar ? '32px 8px' : '42px 12px'
      }}
    >
      {/* Recent context */}
      {recentChats && recentChats.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: 10,
            textAlign: 'left',
          }}>
            Recent Diligence
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {recentChats.slice(0, 3).map((chat) => (
              <div
                key={chat.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.06)',
                  background: 'rgba(255,255,255,0.03)',
                  color: '#94a3b8',
                  fontSize: 12,
                  textAlign: 'left',
                }}
              >
                <Clock size={12} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  {chat.title}
                </span>
                <ChevronRight size={12} />
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="embry-chat-empty-icon" style={{
        display: 'inline-grid',
        placeItems: 'center',
        width: 40,
        height: 40,
        borderRadius: 999,
        background: 'rgba(255,255,255,0.035)',
        boxShadow: 'none',
        filter: 'drop-shadow(0 0 5px rgba(3, 218, 198, 0.14))',
        marginBottom: 16
      }}>
        <Terminal size={20} strokeWidth={1.7} aria-hidden="true" color="#a3a3a3" />
      </div>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#e2e8f0', letterSpacing: '-0.02em' }}>
        {title}
      </h2>
      <p style={{ margin: '8px auto 0', color: '#64748b', lineHeight: 1.5, fontSize: 13 }}>
        {description}
      </p>

      {showSpartaVoiceIdle && (
        <div
          data-qid="shared-chat:idle-voice-panel"
          aria-label="Console idle voice suggestions"
          style={{
            margin: '22px auto 0',
            width: 'min(100%, 300px)',
            borderRadius: 20,
            border: '1px solid rgba(148,163,184,0.16)',
            background: 'linear-gradient(180deg, rgba(15,23,42,0.78), rgba(3,7,18,0.88))',
            boxShadow: '0 20px 60px rgba(0,0,0,0.26), inset 0 1px 0 rgba(255,255,255,0.04)',
            padding: 18,
            display: 'grid',
            justifyItems: 'center',
            gap: 12,
          }}
        >
          <div data-qid="shared-chat:idle-voice-orb" style={{ width: 96, height: 96 }}>
            <EmbryVoiceOrb
              voiceStatus={orbVoiceStatus}
              isStreaming={orbVoiceStatus === 'processing' || orbVoiceStatus === 'speaking'}
              tone={orbVoiceStatus !== 'off' ? 'good' : undefined}
              speechAudioElement={replayableAudioElement}
              speechAudioUrl={latestReplayableAudioSrc ?? undefined}
              speechSourceId={latestReplayableTurn?.turnId}
              speechStartedAtMs={replayableSpeechStartedAtMs}
              speechEnvelope={latestReplayableTurn?.voiceEnvelope ?? undefined}
              size={96}
              surface="toolbar"
              phaseSpeedMs={650}
            />
          </div>
          <div style={{ color: '#64748b', fontSize: 11, fontWeight: 900, letterSpacing: '0.26em', textTransform: 'uppercase' }}>
            Try asking
          </div>
          <button
            key={activeVoicePrompt.qid}
            type="button"
            data-qid={activeVoicePrompt.qid}
            data-qs-action={activeVoicePrompt.action}
            title={`Ask Console: ${activeVoicePrompt.label}`}
            onClick={() => onChip(activeVoicePrompt.prompt)}
            style={{
              border: 0,
              background: 'transparent',
              color: '#f8fafc',
              fontSize: sidebar ? 24 : 28,
              fontWeight: 900,
              letterSpacing: '-0.04em',
              lineHeight: 1.05,
              cursor: 'pointer',
              textAlign: 'center',
              padding: 0,
              minHeight: 44,
            }}
          >
            "{activeVoicePrompt.label}"
          </button>
          <div style={{ width: 70, height: 3, borderRadius: 999, overflow: 'hidden', background: 'rgba(51,65,85,0.82)' }}>
            <div key={`${activeVoicePrompt.qid}:timer`} style={{ width: '100%', height: '100%', background: '#2563eb', transformOrigin: 'left', animation: 'shared-chat-idle-voice-timer 7s linear' }} />
          </div>
          {(voiceProjection || voiceProjectionError) && (
            <div
              data-qid="shared-chat:idle-voice-provenance"
              style={{
                width: '100%',
                borderRadius: 12,
                border: voiceProjection?.degraded || voiceProjectionError
                  ? '1px solid rgba(245,158,11,0.28)'
                  : '1px solid rgba(20,184,166,0.30)',
                background: voiceProjection?.degraded || voiceProjectionError
                  ? 'rgba(120,53,15,0.16)'
                  : 'rgba(20,184,166,0.10)',
                padding: 10,
                textAlign: 'left',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <span
                  style={{
                    color: voiceProjection?.degraded || voiceProjectionError ? '#fbbf24' : '#5eead4',
                    fontSize: 10,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    fontWeight: 900,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                  }}
                >
                  {voiceProjectionError ? 'Journal unavailable' : voiceProjection?.degraded ? 'Journal degraded' : 'Journal linked'}
                </span>
                <span
                  data-qid="shared-chat:idle-voice-provenance-authority"
                  style={{
                    color: '#64748b',
                    fontSize: 9,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: 132,
                  }}
                  title={voiceProjection?.authority}
                >
                  {voiceProjection?.authority ?? 'no-authority'}
                </span>
              </div>
              <div
                data-qid="shared-chat:idle-voice-provenance-transcript"
                style={{
                  marginTop: 7,
                  color: '#cbd5e1',
                  fontSize: 11,
                  lineHeight: 1.4,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {voiceProjectionError || voiceProjection?.transcript || 'No live transcript projected.'}
              </div>
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span
                  data-qid="shared-chat:idle-voice-provenance-status"
                  style={{
                    color: '#94a3b8',
                    fontSize: 10,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {voiceProjection?.sessionId
                    ? `${voiceProjection.status ?? 'unknown'} · ${voiceProjection.missingEvents?.length ?? 0}+${voiceProjection.missingPlaybackEvents?.length ?? 0} missing`
                    : 'fail-closed'}
                </span>
                <button
                  type="button"
                  data-qid="shared-chat:idle-voice-replay"
                  data-qs-action="SHARED_CHAT_IDLE_REPLAY_LATEST_LISTENER"
                  disabled={!voiceProjection || voiceProjection.degraded || !voiceProjection.playbackEvidencePresent}
                  onClick={playLatestReplayableAudio}
                  title={voiceProjection?.playbackEvidencePresent ? 'Replay journaled Chatterbox audio' : 'Replay disabled until playback proof exists for this turn'}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    borderRadius: 999,
                    border: '1px solid rgba(148,163,184,0.16)',
                    background: voiceProjection?.playbackEvidencePresent && !voiceProjection.degraded ? 'rgba(20,184,166,0.16)' : 'rgba(15,23,42,0.5)',
                    color: voiceProjection?.playbackEvidencePresent && !voiceProjection.degraded ? '#99f6e4' : '#64748b',
                    padding: '5px 10px',
                    minHeight: 44,
                    fontSize: 10,
                    fontWeight: 800,
                    cursor: voiceProjection?.playbackEvidencePresent && !voiceProjection.degraded ? 'pointer' : 'not-allowed',
                  }}
                >
                  <PlayCircle size={12} strokeWidth={1.8} />
                  Replay
                </button>
              </div>
            </div>
          )}
          {latestReplayableTurn && (
            <div
              data-qid="shared-chat:idle-voice-replayable"
              style={{
                width: '100%',
                borderRadius: 12,
                border: '1px solid rgba(20,184,166,0.28)',
                background: 'rgba(6,95,70,0.14)',
                padding: 10,
                textAlign: 'left',
                display: 'grid',
                gap: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <span
                  style={{
                    color: '#5eead4',
                    fontSize: 10,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    fontWeight: 900,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                  }}
                >
                  Last replayable
                </span>
                <span
                  data-qid="shared-chat:idle-voice-replayable-status"
                  style={{
                    color: '#94a3b8',
                    fontSize: 9,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: 142,
                  }}
                  title={`${latestReplayableTurn.sessionId ?? 'no-session'} / ${latestReplayableTurn.turnId ?? 'no-turn'}`}
                >
                  {latestReplayableTurn.status ?? 'replayable'} · playback proof
                </span>
              </div>
              <div
                data-qid="shared-chat:idle-voice-replayable-transcript"
                style={{
                  color: '#d1fae5',
                  fontSize: 11,
                  lineHeight: 1.4,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {latestReplayableTurn.transcript || 'Replayable journal turn has no transcript text.'}
              </div>
              {latestReplayableAudioSrc ? (
                <audio
                  ref={bindReplayableAudioRef}
                  data-qid="shared-chat:idle-voice-replayable-audio"
                  data-qs-action="SHARED_CHAT_IDLE_PLAY_REPLAYABLE_AUDIO"
                  data-turn-id={latestReplayableTurn.turnId}
                  data-embry-session-audio="true"
                  title="Play latest replayable Chatterbox audio"
                  controls
                  preload="metadata"
                  src={latestReplayableAudioSrc}
                  onPlay={(event) => markReplayableAudioActive(event.currentTarget)}
                  onPlaying={(event) => markReplayableAudioActive(event.currentTarget)}
                  onTimeUpdate={(event) => markReplayableAudioActive(event.currentTarget)}
                  onPause={markReplayableAudioInactive}
                  onEnded={markReplayableAudioInactive}
                  style={{ width: '100%', height: 30 }}
                />
              ) : (
                <div
                  data-qid="shared-chat:idle-voice-replayable-audio-missing"
                  style={{
                    color: '#64748b',
                    fontSize: 10,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}
                >
                  Replay file unavailable from guarded artifact route.
                </div>
              )}
            </div>
          )}
          <div aria-label="Console idle voice shortcuts" style={{ display: 'none' }}>
            {voicePrompts.map((command) => (
              <button
                key={command.qid}
                type="button"
                data-qid={command.qid}
                data-qs-action={command.action}
                title={`Ask Console: ${command.label}`}
                onClick={() => onChip(command.prompt)}
              >
                {command.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Intent chips with icons */}
      {chips.length > 0 && (
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 8,
          marginTop: 16
        }}>
          {chips.map((chip) => (
            <button
              key={chip.label}
              type="button"
              data-qid={chip.dataQid ?? `shared-chat:starter-chip:${qidToken(chip.label)}`}
              data-qs-action={chip.action ?? 'SHARED_CHAT_STARTER_PROMPT'}
              title={chip.title ?? `Ask: ${chip.label}`}
              onClick={() => onChip(chip.prompt)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(255,255,255,0.04)',
                color: '#94a3b8',
                padding: '8px 12px',
                minHeight: 44,
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              {chip.icon}
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Prompt templates */}
      {promptTemplates && promptTemplates.length > 0 && (
        <div style={{ marginTop: 20, textAlign: 'left' }}>
          <div style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: 8,
          }}>
            Prompt Templates
          </div>
          {promptTemplates.map((template, i) => (
            <button
              key={i}
              type="button"
              data-qid={`shared-chat:prompt-template:${i}`}
              data-qs-action="SHARED_CHAT_APPLY_TEMPLATE"
              title={`Use prompt template: ${template}`}
              onClick={() => onTemplateClick?.(template)}
              style={{
                display: 'block',
                width: '100%',
                padding: '8px 12px',
                minHeight: 44,
                borderRadius: 6,
                border: '1px solid rgba(255,255,255,0.04)',
                background: 'transparent',
                color: '#64748b',
                fontSize: 12,
                cursor: 'pointer',
                textAlign: 'left',
                marginBottom: 4,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {template}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function compactTurnSummary(value: string, maxLength = 120): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLength) return normalized
  return `${normalized.slice(0, maxLength - 1)}…`
}

function DashboardMessageBubble({
  message,
  isReceiptProcessing = false,
  isHovered,
  onHover,
  onLeave,
  onDelete,
  onCopy,
  onDownload,
  onFeedback,
  onRegenerate,
  regenerateDisabled = false,
  contentType,
  roleColor,
  sidebar,
  mediaUrl,
  isHistoricalTurn = false,
  agentLabel = 'SPARTA DAEMON',
}: {
  message: ChatMessage
  index?: number
  isReceiptProcessing?: boolean
  isHovered: boolean
  onHover: () => void
  onLeave: () => void
  onDelete?: () => void
  onCopy?: () => void
  onDownload?: () => void
  onFeedback?: (messageId: string, feedback: 'up' | 'down', details?: FeedbackDetailPayload) => void
  onRegenerate?: () => void
  regenerateDisabled?: boolean
  contentType: string | null
  roleColor: string
  sidebar: boolean
  mediaUrl?: (path: string) => string
  isHistoricalTurn?: boolean
  agentLabel?: string
}): JSX.Element {
  const [escalatedArtifact, setEscalatedArtifact] = useState<UnknownRecord | null>(null)
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false)
  const [localFeedback, setLocalFeedback] = useState<'up' | 'down' | null | undefined>(message.feedback)
  const [historicalExpanded, setHistoricalExpanded] = useState(false)
  const { user } = useRBAC()
  const isUser = message.role === 'user'
  const userInitials = useMemo(() => initialsForName(user.name), [user.name])
  const messageTime = formatMessageTime(message)
  const messageId = String(message.id ?? message.createdAt ?? message.timestamp ?? 'message')
  const branch = branchFromMessage(message)
  const steps = thinkingStepsForMessage(message)
  const disclosure = thinkingTraceDisclosureParts({ message, branch })
  const meta = (message.metadata ?? {}) as UnknownRecord
  const isError = message.role === 'error' || message.alertType === 'error' || Boolean(meta.error || meta.clientTransportFailClosed)

  const topLevelEvidenceCase = isRecord(message.evidenceCase) ? message.evidenceCase : undefined
  const evidenceCaseData = (meta.evidenceCase ?? meta.evidence_case ?? topLevelEvidenceCase ?? evidenceCaseFromMemoryAnswerV2Metadata(message, meta)) as EvidenceCaseData | undefined
  const matrixSummary = (meta.matrixSummary ?? meta.matrix_summary) as ThreatMatrixSummary | undefined
  const recallItems = (meta.recallItems ?? meta.recall_items ?? meta.recall) as RecallItem[] | undefined
  const resultCount = meta.resultCount ?? meta.result_count
  const entities = meta.entities as Array<EntityArtifact | string> | undefined

  useEffect(() => {
    setLocalFeedback(message.feedback)
  }, [message.feedback])
  const entitySpans = extractEntitySpansFromMessage(message, meta)
  const verdict = meta.verdict as VerdictArtifact | undefined
	  const querySpec = (meta._querySpec ?? meta.querySpec ?? meta.query_spec) as UnknownRecord | undefined
	  const figureArtifact = (meta.figureArtifact ?? meta.figure_artifact) as FigureArtifact | undefined
	  const tableData = (meta.tableData ?? meta.table_data) as TableArtifact | undefined
	  const audioArtifacts = normalizeAudioArtifacts(meta.audioArtifacts ?? meta.audio_artifacts)
	  const watchEvidenceCards = Array.isArray(meta.watchEvidenceCards) ? meta.watchEvidenceCards : Array.isArray(meta.watch_evidence_cards) ? meta.watch_evidence_cards : []
	  const hasHighRisk = tableData && Array.isArray(tableData.rows) && tableData.rows.some((row) =>
	    row.some((cell) => typeof cell === 'string' && (cell.includes('DIFF') || cell.includes('HIGH') || cell.includes('CRITICAL')))
	  )
  const qidRole = isUser ? 'user' : isError ? 'error' : 'assistant'
  const provenanceLabel = isUser
    ? 'Human input'
    : branch === 'watch'
      ? 'Watch Agent'
      : message.skillUsed
        ? `Agent /${message.skillUsed}`
        : 'Agent analysis'

  // Extract code blocks
  const codeBlocks = message.content ? extractCodeBlocks(message.content) : []
  const textContent = message.content ? removeCodeBlocks(message.content) : ''
  const messageTurnId = firstMetadataString(
    message.id,
    meta.turnId,
    meta.turn_id,
    meta.turnID,
    meta.turnAuthority && isRecord(meta.turnAuthority) ? meta.turnAuthority.turnId : undefined,
  )
  const responsePlanId = firstMetadataString(meta.responsePlanId, meta.response_plan_id)
  const chatRenderReceiptId = firstMetadataString(meta.chatRenderReceiptId, meta.chat_render_receipt_id)
  const evidenceCaseOwnAnswer = evidenceCaseData
    ? stripCitationListEcho(String(evidenceCaseData.answer ?? evidenceCaseData.description ?? ''))
    : ''
  const dedupedTextContent = dedupeRepeatedParagraphs(textContent)
  const isTerminalFailure = !isUser && isTerminalFailureText(dedupedTextContent)
  const renderedTextContent = evidenceCaseData && evidenceCaseOwnAnswer
    ? ''
    : evidenceCaseData
      ? stripCitationListEcho(dedupedTextContent)
      : isTerminalFailure
        ? ''
        : dedupedTextContent
  const executionTraceLog = !isUser && steps.length > 0 ? (
    <ConsoleExecutionTraceLog
      steps={steps}
      receiptId={chatRenderReceiptId ?? responsePlanId ?? messageTurnId}
      isGenerating={isReceiptProcessing}
    />
  ) : null

  if (isHistoricalTurn && !historicalExpanded) {
    const compactRole = isUser ? 'GM' : isError || isTerminalFailure ? 'ERR' : 'OK'
    const compactColor = isUser ? '#3b82f6' : isError || isTerminalFailure ? '#ef4444' : '#10b981'
    const summary = isTerminalFailure
      ? 'TERMINAL FAILURE: Answer route constrained.'
      : compactTurnSummary(renderedTextContent || dedupedTextContent || message.content)
    return (
      <article
        data-qid={`shared-chat:message:${qidRole}:historical`}
        data-branch={branch ?? message.role}
        data-turn-id={messageTurnId}
        onClick={() => setHistoricalExpanded(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setHistoricalExpanded(true)
          }
        }}
        role="button"
        tabIndex={0}
        title="Expand historical Console turn"
        style={{
          width: '100%',
          minWidth: 0,
          maxWidth: '100%',
          display: 'grid',
          gap: 4,
          padding: sidebar ? '10px 16px' : '12px 20px',
          borderBottom: '1px solid rgba(31, 41, 55, 0.7)',
          background: 'var(--surface-deep)',
          cursor: 'pointer',
          overflow: 'visible',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, minWidth: 0 }}>
          <span style={{ color: '#64748b', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
            {messageTime ? `${messageTime} · ` : ''}{isUser ? userInitials : agentLabel}
          </span>
          <span style={{ color: '#475569', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
            Expand
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
          <span style={{ color: compactColor, fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 800, letterSpacing: '0.1em', flexShrink: 0 }}>
            [{compactRole}]
          </span>
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#cbd5e1', fontSize: 13, fontWeight: 600 }}>
            {compactTurnSummary(message.content, 96)}
          </span>
        </div>
        {!isUser ? (
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: isError || isTerminalFailure ? '#ef4444' : '#64748b', fontSize: 11, fontFamily: 'var(--font-mono, monospace)' }}>
            &gt; {summary}
          </span>
        ) : null}
      </article>
    )
  }

  return (
    <article
      data-qid={`shared-chat:message:${qidRole}`}
      data-branch={branch ?? message.role}
      data-turn-id={messageTurnId}
      data-response-plan-id={responsePlanId}
      data-chat-render-receipt-id={chatRenderReceiptId}
      data-entity-span-count={entitySpans.length}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      style={{
        padding: 0,
        borderBottom: '1px solid rgba(31, 41, 55, 0.82)',
        background: isUser ? 'var(--surface-deep)' : isError ? 'rgba(127, 29, 29, 0.12)' : 'var(--surface-base)',
        minWidth: 0,
        maxWidth: '100%',
        overflow: 'visible',
      }}
    >
      {/* User: command echo. Assistant: daemon output. */}
			      {isUser ? (
				        <div
				          data-qid="shared-chat:message:user-command"
				          style={{
				            display: 'flex',
				            flexDirection: 'column',
				            alignItems: 'stretch',
				            gap: 8,
				            fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
				            width: '100%',
                    // High-density console (sparta#43): py-2 px-3 equivalent, down
                    // from 14-16px vertical padding.
                    padding: sidebar ? '8px 12px' : '8px 12px',
				          }}
				        >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <User size={14} color="#3b82f6" aria-hidden="true" />
                    <span style={{ color: '#64748b', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                      {messageTime ? `${messageTime} · ` : ''}{userInitials}
                    </span>
                    {/* sparta#43: copy action lives in the header row (progressive
                        disclosure on hover) instead of a dedicated action row that
                        reserved ~24-32px per turn. Same qid + action as before. */}
                    <span
                      style={{
                        marginLeft: 'auto',
                        display: 'inline-flex',
                        alignItems: 'center',
                        opacity: isHovered ? 1 : 0,
                        transition: 'opacity 160ms ease',
                      }}
                    >
                      <CopyButton
                        content={message.content}
                        qid={`shared-chat:message:${messageId}:copy-user-request`}
                        action="SHARED_CHAT_COPY_USER_REQUEST"
                        title="Copy user request"
                        label="Copy user request"
                      />
                    </span>
                  </div>
				          <div
				            className={isReceiptProcessing ? 'embry-receipt embry-receipt--processing' : 'embry-receipt'}
				            data-qid={isReceiptProcessing ? 'embry-receipt:processing' : 'embry-receipt:user'}
			            style={{
			            width: '100%',
			            background: 'transparent',
			            border: 0,
			            borderRadius: 0,
				            padding: 0,
				            boxShadow: 'none',
				            display: 'block',
	                  minWidth: 0,
				          }}>
				            <div style={{
				              color: '#cbd5e1',
				              fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
				              fontSize: sidebar ? 15 : COMPOSER_TEXTAREA_FONT_SIZE,
				              fontWeight: 500,
				              lineHeight: '24px',
				              // sparta#43: right padding reserved so long prompt text wraps
				              // before reaching the hover-revealed header copy button.
				              padding: '4px 32px 4px 6px',
			              minWidth: 0,
			              wordBreak: 'break-word',
			            }}>
		                <MarkdownRenderer content={message.content} sidebarMode={sidebar} entitySpans={entitySpans} mediaUrl={mediaUrl ?? defaultMediaUrl} />
		            </div>
		          </div>
		        </div>
			      ) : (
	        <div
	          className={isReceiptProcessing ? 'embry-receipt embry-receipt--processing' : 'embry-receipt'}
	          data-qid={isError ? 'embry-receipt:error' : isReceiptProcessing ? 'embry-receipt:processing' : 'embry-receipt:assistant'}
			          style={{
				          background: 'transparent',
				          border: 0,
				          borderRadius: 0,
				          padding: sidebar ? '14px 18px' : '16px 20px',
				          margin: 0,
				          boxShadow: 'none',
		                  display: 'block',
                  minWidth: 0,
                  maxWidth: '100%',
                  overflow: 'visible',
				        }}>
	              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 0, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                {isError ? <AlertTriangle size={14} color="#ef4444" aria-hidden="true" /> : <Terminal size={14} color="#10b981" aria-hidden="true" />}
                <span style={{ color: '#64748b', fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  {isError ? `${agentLabel} · ERROR` : agentLabel}
                </span>
                {entities && Array.isArray(entities) && entities.length > 0 ? (
                  <span style={{ marginLeft: 'auto', color: '#94a3b8', background: 'var(--surface-raised)', border: '1px solid rgba(31, 41, 55, 0.95)', padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 800 }}>
                    {entities.length} ENTITY{entities.length === 1 ? '' : 'S'}
                  </span>
                ) : null}
              </div>
              {isError && (
                <div style={{ display: 'grid', gap: 4 }}>
                  <span style={{ color: '#ff7b72', fontSize: 12, fontWeight: 750 }}>System Error</span>
                  {meta.error ? <span style={{ color: '#fca5a5', fontSize: 12 }}>{String(meta.error)}</span> : null}
                </div>
              )}
          {executionTraceLog}

	          {/* Sources / Context pill */}
          {!isUser && recallItems && Array.isArray(recallItems) && recallItems.length > 0 && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 10,
              flexWrap: 'wrap',
            }}>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  borderRadius: 4,
                  background: '#22232a',
                  color: '#a5a8b3',
                  fontSize: 10,
                  fontWeight: 500,
                }}>
                  <BarChart3 size={10} />
                  {recallItems.length} sources
                </span>
            </div>
          )}

          {/* Content */}
          <div>
          {/* Tool action line */}
          {!isUser && message.skillUsed && !evidenceCaseData && <ToolAction label={`Ran /${message.skillUsed}`} qid={`chat:skill:${message.skillUsed}`} />}

	          {/* Evidence Case */}
		          {!isUser && evidenceCaseData && <ConsoleEvidenceCaseBlock data={evidenceCaseData as EvidenceCaseData} isGenerating={isReceiptProcessing} />}

          {/* Figure artifact */}
          {!isUser && figureArtifact && (
            <div data-qid="shared-chat:figure" style={{ marginTop: 8 }}>
	              <img
	                src={figureArtifact.url ?? figureArtifact.src}
	                alt={figureArtifact.alt ?? 'Figure'}
	                style={{ maxWidth: '100%', borderRadius: 12 }}
	              />
            </div>
          )}

          {/* Divergence Card for tables */}
          {tableData && (
            <div
              data-qid="shared-chat:table"
              className="chat-structured-table"
              style={{
                marginTop: 8,
                overflowX: 'auto',
                maxHeight: 300,
                overflowY: 'auto',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.04)',
                border: hasHighRisk ? '1px solid rgba(245, 158, 11, 0.3)' : '1px solid rgba(255,255,255,0.06)',
                boxShadow: hasHighRisk ? '0 0 12px rgba(245, 158, 11, 0.1)' : 'none',
              }}
            >
              <div style={{
                padding: '8px 12px',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Divergence Data
                </span>
                {hasHighRisk && (
                  <span style={{
                    padding: '1px 6px',
                    borderRadius: 4,
                    background: 'rgba(245, 158, 11, 0.15)',
                    color: '#f59e0b',
                    fontSize: 9,
                    fontWeight: 700,
                  }}>
                    [!] HIGH RISK
                  </span>
                )}
	              </div>
	              <div style={{ padding: 8 }}>
                <MarkdownRenderer content={renderTable({
	                  headers: Array.isArray(tableData.headers) ? tableData.headers.filter((value): value is string => typeof value === 'string') : undefined,
	                  rows: Array.isArray(tableData.rows) ? tableData.rows.map((row) => row.map((cell) => String(cell))) : undefined,
	                })} />
	              </div>
            </div>
          )}

	          {!isUser && watchEvidenceCards.length > 0 && (
	            <WatchEvidenceCardStack cards={watchEvidenceCards as UnknownRecord[]} mediaUrl={mediaUrl ?? defaultMediaUrl} onEscalate={setEscalatedArtifact} />
	          )}

          {/* Text content */}
          {isTerminalFailure && (
            <ConsoleTerminalAlert message={dedupedTextContent} />
          )}
          {renderedTextContent && message.supersededDiagnostic ? (
            <details
              data-qid="shared-chat:message:superseded-diagnostic"
              style={{ marginTop: 8, border: '1px solid rgba(139,148,158,0.3)', borderRadius: 8, padding: '6px 10px', background: 'rgba(139,148,158,0.06)' }}
            >
              <summary
                title="Legacy diagnostic-only turn tombstoned on load; not a current substantive answer"
                style={{ cursor: 'pointer', color: 'var(--text-muted)', fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}
              >
                Superseded diagnostic — not a current answer
              </summary>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', lineHeight: 1.5, marginTop: 6, opacity: 0.75, overflowX: 'auto', maxWidth: '100%' }}>
                <MarkdownRenderer content={renderedTextContent} sidebarMode={sidebar} entitySpans={entitySpans} mediaUrl={mediaUrl ?? defaultMediaUrl} />
              </div>
            </details>
          ) : renderedTextContent ? (
            <div style={{
              color: '#f2f2f3',
              fontSize: '0.85rem',
              lineHeight: 1.6,
              marginTop: (!isUser && (evidenceCaseData || figureArtifact || tableData)) ? 12 : 0,
              overflowX: 'auto',
              maxWidth: '100%',
              WebkitOverflowScrolling: 'touch',
            }}>
                <MarkdownRenderer content={renderedTextContent} sidebarMode={sidebar} entitySpans={entitySpans} mediaUrl={mediaUrl ?? defaultMediaUrl} />
            </div>
          ) : null}

          {!isUser && audioArtifacts.length > 0 && (
            <VoiceAudioArtifacts artifacts={audioArtifacts} mediaUrl={mediaUrl ?? defaultMediaUrl} parentTurnId={messageTurnId} />
          )}

          {/* Code blocks */}
          {codeBlocks.map((block, i) => (
            <CodeBlock key={i} code={block.code} language={block.language} qid={`shared-chat:message:${messageId}:code-block:${i}`} />
          ))}

	          {/* Recall cards */}
	          {!isUser && recallItems && Array.isArray(recallItems) && recallItems.length > 0 && (
	            <RecallCard items={recallItems as RecallItem[]} resultCount={typeof resultCount === 'number' ? resultCount : recallItems.length} />
	          )}

	          {/* Threat matrix card */}
	          {!isUser && matrixSummary && (
	            <ThreatMatrixCard summary={matrixSummary as ThreatMatrixSummary} />
	          )}

          {/* Entity pills */}
	          {!isUser && entities && Array.isArray(entities) && entities.length > 0 && (
	            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
	              {(entities as Array<EntityArtifact | string>).map((e, i: number) => (
	                <span key={i} style={{
                  padding: '3px 8px',
                  borderRadius: 6,
                  border: '1px solid rgba(255,255,255,0.08)',
                  background: 'rgba(255,255,255,0.04)',
                  fontSize: 11,
                  color: '#94a3b8'
	                }}>
	                  {typeof e === 'string' ? e : e.label ?? e.id ?? ''}
	                </span>
	              ))}
	            </div>
	          )}

	          {/* Gate chain */}
	          {!isUser && verdict && !evidenceCaseData && (
	            <GateChain
	              gates={(verdict as VerdictArtifact).gates ?? []}
	              verdict={(verdict as VerdictArtifact).state ?? 'INCONCLUSIVE'}
	              tier={(verdict as VerdictArtifact).tier}
	            />
	          )}

          {/* QuerySpec collapsible */}
          {!isUser && querySpec && (
            <details style={{ marginTop: 6, fontSize: 11 }}>
              <summary
                data-qid={`shared-chat:message:${messageId}:queryspec-toggle`}
                data-qs-action="SHARED_CHAT_TOGGLE_QUERYSPEC"
                title="Toggle QuerySpec details"
                style={{ color: '#9ba8b8', cursor: 'pointer' }}
              >
                QuerySpec
              </summary>
              <pre style={{ color: '#9ba8b8', fontSize: 11, whiteSpace: 'pre-wrap', marginTop: 4, padding: 6, background: 'rgba(0,0,0,0.3)', borderRadius: 6, overflow: 'auto', maxHeight: 150 }}>
                {JSON.stringify(querySpec, null, 2)}
              </pre>
            </details>
          )}

	          {/* Footer */}
		          {!isUser && (
		            <>
		              {!evidenceCaseData && <MessageFooter message={message} />}
				              <div
				                data-qid="shared-chat:message-response-actions"
                        className="shared-chat-message-actions"
			                style={{
			                  display: 'flex',
			                  alignItems: 'center',
                        flexWrap: 'wrap',
			                  gap: 12,
			                  marginTop: 12,
			                  color: '#9aa3b5',
                        minWidth: 0,
                        maxWidth: '100%',
                        overflowX: 'hidden',
			                }}
			              >
                <CopyButton
                  content={message.content}
                  qid={`shared-chat:message:${messageId}:copy-response`}
                  action="SHARED_CHAT_COPY_MESSAGE"
                  title="Copy response"
                  label="Copy message response"
                />
	                <ActionTooltip content={onRegenerate ? (regenerateDisabled ? 'Regenerate response after current run finishes' : 'Regenerate response') : 'Regenerate response requires a prior user request'}>
	                  <button
	                    type="button"
	                    data-qid={`shared-chat:message:${messageId}:regenerate-response`}
	                    data-qs-action="SHARED_CHAT_REGENERATE_RESPONSE"
	                    aria-label={onRegenerate ? 'Regenerate response' : 'Regenerate response requires a prior user request'}
	                    onClick={onRegenerate}
	                    disabled={!onRegenerate || regenerateDisabled}
	                    style={{
	                      ...actionButtonStyle,
	                      cursor: !onRegenerate || regenerateDisabled ? 'not-allowed' : 'pointer',
	                      opacity: !onRegenerate || regenerateDisabled ? 0.42 : 1,
	                    }}
	                  >
	                    {regenerateDisabled && onRegenerate ? <Loader2 size={14} className="animate-spin" /> : <RotateCw size={14} />}
	                  </button>
	                </ActionTooltip>
                <span
                  aria-hidden="true"
                  style={{
                    width: 1,
                    height: 14,
                    background: 'var(--border-default)',
                    margin: '0 2px',
                  }}
                />
		                <ActionTooltip content="Good response">
		                  <button
		                    type="button"
		                    data-qid={`shared-chat:message:${messageId}:feedback-up`}
	                    data-qs-action="SHARED_CHAT_FEEDBACK_HELPFUL"
		                    aria-label="Good response"
		                    aria-pressed={localFeedback === 'up'}
		                    onClick={() => {
		                      setLocalFeedback('up')
		                      onFeedback?.(messageId, 'up')
		                    }}
		                    onMouseEnter={(event) => { event.currentTarget.style.color = '#4ade80' }}
		                    onMouseLeave={(event) => { event.currentTarget.style.color = localFeedback === 'up' ? '#b7fff6' : '#7f8798' }}
		                    style={{
	                      ...actionButtonStyle,
	                      ...(localFeedback === 'up' ? activeActionButtonStyle : {}),
	                    }}
	                  >
	                    <ThumbsUp size={14} />
	                  </button>
	                </ActionTooltip>
	                <ActionTooltip content="Report issue">
	                  <button
	                    type="button"
	                    data-qid={`shared-chat:message:${messageId}:feedback-down`}
	                    data-qs-action="SHARED_CHAT_FEEDBACK_NOT_HELPFUL"
			                    aria-label="Report issue"
			                    aria-pressed={localFeedback === 'down'}
	                    onClick={() => {
	                      setLocalFeedback('down')
	                      onFeedback?.(messageId, 'down')
	                      setFeedbackModalOpen(true)
	                    }}
			                    onMouseEnter={(event) => { event.currentTarget.style.color = '#f87171' }}
			                    onMouseLeave={(event) => { event.currentTarget.style.color = localFeedback === 'down' ? '#b7fff6' : '#7f8798' }}
		                    style={{
	                      ...actionButtonStyle,
	                      ...(localFeedback === 'down' ? activeActionButtonStyle : {}),
	                    }}
		                  >
		                    <ThumbsDown size={14} />
		                  </button>
		                </ActionTooltip>
		              </div>
	            </>
	          )}
	        </div>
	        {escalatedArtifact && (
	          <WatchCanvasOverlay artifact={escalatedArtifact} mediaUrl={mediaUrl ?? defaultMediaUrl} onClose={() => setEscalatedArtifact(null)} />
	        )}
	        {feedbackModalOpen && (
	          <FeedbackModal
	            messageId={messageId}
	            onClose={() => setFeedbackModalOpen(false)}
	            onSubmit={(payload) => {
	              onFeedback?.(messageId, 'down', payload)
	            }}
	          />
	        )}
	      </div>
      </div>
    )}
    </article>
  )
}

function WatchEvidenceCardStack({
  cards,
  mediaUrl,
  onEscalate,
}: {
  cards: UnknownRecord[]
  mediaUrl: (path: string) => string
  onEscalate: (artifact: UnknownRecord) => void
}): JSX.Element {
  return (
    <div data-qid="watch:chat:evidence-card-stack" style={{ display: 'grid', gap: 10, marginTop: 10 }}>
      {cards.map((card, index) => (
        <React.Fragment key={`${String(card.timecode ?? 'row')}-${index}`}>
          {index > 0 && <EvidenceBreak previousCard={cards[index - 1]} card={card} />}
          <WatchEvidenceCard card={card} mediaUrl={mediaUrl} onEscalate={onEscalate} />
        </React.Fragment>
      ))}
    </div>
  )
}

type VoiceAudioArtifact = {
  id: string
  label: string
  url: string
  path?: string
  turnId?: string
}

function normalizeAudioArtifacts(value: unknown): VoiceAudioArtifact[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item, index) => {
    if (!isRecord(item)) return []
    const rawUrl = item.url ?? item.src ?? item.href ?? item.path
    if (typeof rawUrl !== 'string' || !rawUrl.trim()) return []
    const label = item.label ?? item.title ?? item.id ?? `audio_${index + 1}`
    return [{
      id: String(item.id ?? `audio-${index}`),
      label: String(label),
      url: rawUrl,
      path: typeof item.path === 'string' ? item.path : undefined,
      turnId: firstMetadataString(item.turnId, item.turn_id, item.parentTurnId, item.parent_turn_id),
    }]
  })
}

function resolveVoiceAudioSrc(url: string, mediaUrl: (path: string) => string): string {
  if (url.startsWith('/chatterbox-artifacts')) {
    if (typeof window === 'undefined') return url
    const apiOrigin = window.location.port === '3002'
      ? `${window.location.protocol}//${window.location.hostname}:3001`
      : window.location.origin
    return `${apiOrigin}${url}`
  }
  return url.startsWith('/') ? mediaUrl(url) : url
}

function VoiceAudioArtifacts({
  artifacts,
  mediaUrl,
  parentTurnId,
}: {
  artifacts: VoiceAudioArtifact[]
  mediaUrl: (path: string) => string
  parentTurnId?: string
}): JSX.Element {
  return (
    <div data-qid="shared-chat:voice-audio-artifacts" style={{ display: 'grid', gap: 8, marginTop: 10 }}>
      {artifacts.map((artifact) => {
        const src = resolveVoiceAudioSrc(artifact.url, mediaUrl)
        return (
          <div
            key={artifact.id}
            style={{
              display: 'grid',
              gap: 6,
              padding: 8,
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.075)',
              background: 'rgba(0,0,0,0.22)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#aeb7c6', fontSize: 11 }}>
              <PlayCircle size={13} />
              <span>{artifact.label}</span>
            </div>
            <audio
              data-qid={`shared-chat:voice-audio:${artifact.id}`}
              data-turn-id={artifact.turnId ?? parentTurnId}
              data-embry-session-audio="true"
              controls
              preload="metadata"
              src={src}
              style={{ width: '100%', height: 30 }}
            />
          </div>
        )
      })}
    </div>
  )
}

function EvidenceBreak({ previousCard, card }: { previousCard?: UnknownRecord; card: UnknownRecord }): JSX.Element {
  const marker = evidenceBreakMarker(previousCard, card)
  const Icon = marker.icon
  return (
    <div className="watch-chat-evidence-divider" data-qid="watch:chat:evidence-divider">
      <span className="watch-chat-evidence-divider__line" />
      <span className="watch-chat-evidence-divider__badge">
        <span className="watch-chat-evidence-divider__icon" data-kind={marker.kind}>
          <Icon size={12} strokeWidth={1.8} aria-hidden="true" />
        </span>
        <span>{marker.label}</span>
      </span>
      <span className="watch-chat-evidence-divider__line" />
    </div>
  )
}

function evidenceBreakMarker(previousCard: UnknownRecord | undefined, card: UnknownRecord): { kind: string; label: string; icon: typeof GitCommit } {
  const previousSeconds = parseTimecodeSeconds(typeof previousCard?.timecode === 'string' ? previousCard.timecode : '')
  const nextSeconds = parseTimecodeSeconds(typeof card.timecode === 'string' ? card.timecode : '')
  if (previousSeconds != null && nextSeconds != null && Math.abs(nextSeconds - previousSeconds) > 120) {
    return { kind: 'time', label: `Time shift ${String(card.timecode ?? '')}`.trim(), icon: Clock }
  }
  const previousEntity = firstEvidenceEntity(previousCard)
  const nextEntity = firstEvidenceEntity(card)
  if (previousEntity && nextEntity && previousEntity !== nextEntity) {
    return { kind: 'entity', label: `Entity pivot ${nextEntity}`, icon: User }
  }
  return { kind: 'thread', label: `Evidence shift ${String(card.timecode ?? '')}`.trim(), icon: GitCommit }
}

function parseTimecodeSeconds(value: string): number | null {
  const parts = value.split(':').map((part) => Number(part))
  if (!parts.length || parts.some((part) => Number.isNaN(part))) return null
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return null
}

function firstEvidenceEntity(card: UnknownRecord | undefined): string | undefined {
  const entities = Array.isArray(card?.entities) ? card.entities : []
  for (const entity of entities) {
    if (!entity || typeof entity !== 'object') continue
    const name = (entity as UnknownRecord).name
    if (typeof name === 'string' && name.trim()) return name.trim()
  }
  return undefined
}

function WatchEvidenceCard({
  card,
  mediaUrl,
  onEscalate,
}: {
  card: UnknownRecord
  mediaUrl: (path: string) => string
  onEscalate: (artifact: UnknownRecord) => void
}): JSX.Element {
  const entities = Array.isArray(card.entities) ? card.entities as UnknownRecord[] : []
  const image = typeof card.image === 'string' ? card.image : ''
  const clip = typeof card.clip === 'string' ? card.clip : ''
  const timecode = typeof card.timecode === 'string' ? card.timecode : 'Evidence'
  const segment = typeof card.segment === 'string' ? card.segment : ''
  const text = typeof card.text === 'string' ? card.text : ''
  const visual = typeof card.visual === 'string' ? card.visual : ''
  const evidenceRange = segment ? segment.replace(/\s*-\s*/, ' — ') : timecode

  return (
    <section data-qid="watch:chat:evidence-card" className="watch-chat-evidence-card" style={{
      position: 'relative',
      border: '1px solid rgba(147, 166, 185, 0.28)',
      borderRadius: 7,
      background: '#111820',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.035)',
      overflow: 'hidden',
    }}>
      <div className="watch-chat-evidence-card__data-strip" data-qid="watch:chat:evidence-card:data-strip">
        <span className="watch-chat-evidence-card__status">[!]</span>
        <span className="watch-chat-evidence-card__range">{evidenceRange}</span>
        <button
          type="button"
          data-qid="watch:chat:evidence-card:expand"
          data-qs-action="WATCH_EVIDENCE_OPEN_CANVAS"
          className="watch-chat-evidence-card__expand"
          aria-label={`Expand evidence ${timecode}`}
          title="Open in canvas"
          onClick={() => onEscalate(card)}
        >
          <Maximize2 size={14} strokeWidth={1.7} aria-hidden="true" />
        </button>
      </div>

      {(image || clip) && (
        <div className="watch-chat-evidence-card__visual" data-qid="watch:chat:evidence-card:visual">
          <div className="watch-chat-evidence-card__zone-label">Frame</div>
          {image && (
            <img
              src={mediaUrl(image)}
              alt={`${timecode} evidence frame`}
              className="chat-prose__img"
              loading="lazy"
            />
          )}
          {clip && (
            <video
              src={mediaUrl(clip)}
              controls
              preload="metadata"
              className="chat-prose__video"
            />
          )}
        </div>
      )}

      <div className="watch-chat-evidence-card__transcript" data-qid="watch:chat:evidence-card:transcript">
        <div className="watch-chat-evidence-card__zone-label">SRT / Transcript</div>
        {text && <p style={{ margin: 0, color: '#f4f7fa', fontSize: 13, lineHeight: 1.52 }}>{text}</p>}
        {visual && <p style={{ margin: 0, color: '#a8b6c7', fontSize: 11.5, lineHeight: 1.48 }}>{visual}</p>}
        {entities.length > 0 && (
          <div data-qid="watch:chat:entity-strip" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingTop: 2 }}>
            {entities.map((entity, index) => (
              <WatchEntityTag key={`${String(entity.name ?? 'entity')}-${index}`} entity={entity} />
            ))}
          </div>
        )}
      </div>
      <div className="watch-chat-evidence-card__footer" data-qid="watch:chat:evidence-card:footer">
        <button
          type="button"
          data-qid="watch:chat:evidence-card:play"
          data-qs-action="WATCH_EVIDENCE_PLAY_CLIP"
          className="watch-chat-evidence-card__footer-action"
          title="Play clip"
        >
          <PlayCircle size={15} strokeWidth={1.7} aria-hidden="true" />
          <span>Play</span>
        </button>
        <button
          type="button"
          data-qid="watch:chat:evidence-card:locate"
          data-qs-action="WATCH_EVIDENCE_LOCATE_ROW"
          className="watch-chat-evidence-card__footer-action"
          title="Locate row"
        >
          <Search size={14} strokeWidth={1.7} aria-hidden="true" />
          <span>Locate</span>
        </button>
      </div>
	    </section>
  )
}

function WatchCanvasOverlay({
  artifact,
  mediaUrl,
  onClose,
}: {
  artifact: UnknownRecord
  mediaUrl: (path: string) => string
  onClose: () => void
}): JSX.Element {
  const image = typeof artifact.image === 'string' ? artifact.image : ''
  const clip = typeof artifact.clip === 'string' ? artifact.clip : ''
  const timecode = String(artifact.timecode ?? 'Watch evidence')
  const text = String(artifact.text ?? '')
  const visual = String(artifact.visual ?? '')
  const entities = Array.isArray(artifact.entities) ? artifact.entities as UnknownRecord[] : []
  return (
    <div data-qid="watch:canvas-overlay-backdrop" className="watch-canvas-overlay__backdrop" role="dialog" aria-modal="true">
      <section data-qid="watch:canvas-overlay" className="watch-canvas-overlay">
        <header className="watch-canvas-overlay__header">
          <div>
            <div className="watch-canvas-overlay__eyebrow">Watch Evidence Canvas</div>
            <div className="watch-canvas-overlay__title">{timecode}</div>
          </div>
          <button
            type="button"
            data-qid="watch:canvas-overlay:close"
            data-qs-action="WATCH_CANVAS_CLOSE"
            className="watch-canvas-overlay__close"
            onClick={onClose}
            aria-label="Close canvas"
            title="Close canvas"
          >×</button>
        </header>
        <div className="watch-canvas-overlay__content">
          <div className="watch-canvas-overlay__media">
            {image && <img src={mediaUrl(image)} alt={`${timecode} evidence frame`} />}
            {clip && <video src={mediaUrl(clip)} controls preload="metadata" />}
          </div>
          <aside className="watch-canvas-overlay__detail">
            {text && <p>{text}</p>}
            {visual && <p>{visual}</p>}
            {entities.length > 0 && (
              <div className="watch-canvas-overlay__entities">
                {entities.map((entity, index) => <WatchEntityTag key={`${String(entity.name ?? 'entity')}-${index}`} entity={entity} />)}
              </div>
            )}
          </aside>
        </div>
      </section>
    </div>
  )
}

function WatchEntityTag({ entity }: { entity: UnknownRecord }): JSX.Element {
  const name = String(entity.name ?? entity.label ?? 'Entity')
  const type = String(entity.type ?? 'context')
  return (
    <button
      type="button"
      data-qid="watch:chat:entity-tag"
      data-qs-action="WATCH_FILTER_ENTITY"
      title={`Filter Watch table by ${name}`}
      onClick={() => {
        window.dispatchEvent(new CustomEvent('watch:entity-filter', { detail: { entity: name, type } }))
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        border: '1px solid rgba(187,134,252,0.34)',
        borderRadius: 10,
        background: 'rgba(187,134,252,0.08)',
        color: '#e9ddff',
        padding: '2px 7px',
        fontSize: 11,
        cursor: 'pointer',
      }}
    >
      {type === 'location' ? <MapPin size={11} strokeWidth={1.7} aria-hidden="true" /> : type === 'character' ? <User size={11} strokeWidth={1.7} aria-hidden="true" /> : <Tag size={11} strokeWidth={1.7} aria-hidden="true" />}
      {name}
    </button>
  )
}

const actionButtonStyle: React.CSSProperties = {
  width: 22,
  height: 22,
  borderRadius: 5,
  border: 0,
  background: '#22232a',
  color: '#7f8798',
  display: 'grid',
  placeItems: 'center',
  cursor: 'pointer',
}

const activeActionButtonStyle: React.CSSProperties = {
  background: 'rgba(3,218,198,0.14)',
  color: '#b7fff6',
}

function extractCodeBlocks(content: string): { code: string; language: string }[] {
  const blocks: { code: string; language: string }[] = []
  const regex = /```(\w+)?\n([\s\S]*?)```/g
  let match
  while ((match = regex.exec(content)) !== null) {
    blocks.push({
      language: match[1] || 'text',
      code: match[2].trim(),
    })
  }
  return blocks
}

function removeCodeBlocks(content: string): string {
  return content.replace(/```(\w+)?\n[\s\S]*?```/g, '').trim()
}

function renderTable(data: { headers?: string[]; rows?: string[][] }): string {
  if (!data.headers || !data.rows) return ''
  const header = `| ${data.headers.join(' | ')} |`
  const separator = `| ${data.headers.map(() => '---').join(' | ')} |`
  const body = data.rows.map(row => `| ${row.join(' | ')} |`).join('\n')
  return `${header}\n${separator}\n${body}`
}

export default ComplianceChatWell
