import React, { useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Mic,
  PlayCircle,
  Radio,
  Volume2,
  XCircle,
} from 'lucide-react'
import SharedChatShell from './SharedChatShell'
import type { ChatMessage, MemoryTurnAdapter, UnknownRecord } from './memory-turn'
import { EmbryVoiceChatAdapter, type EmbryVoiceChatAdapterOptions } from './memory-turn'

export interface EmbryVoiceAudioArtifact {
  id?: string
  label?: string
  path?: string
  url?: string
  sha256?: string
  durationSeconds?: number
  bytes?: number
  transcript?: string
  tone?: string
}

export interface EmbryVoiceTurnEvidence {
  id: string
  userText: string
  assistantText: string
  speakerId?: string
  speakerStatus?: 'known' | 'unknown' | 'ambiguous' | string
  tone?: string
  memoryAction?: string
  memoryConfidence?: number
  qraCacheHit?: boolean
  interruptionOldBytesAfterCancel?: number
  receiptPath?: string
  audioArtifacts?: EmbryVoiceAudioArtifact[]
  latencyMs?: Record<string, number>
  mocked?: boolean
  live?: boolean
}

export interface EmbryVoiceSanityRun {
  id: string
  label: string
  receiptPath: string
  ok?: boolean
  mocked?: boolean
  live?: boolean
  failedGates?: string[]
  scenarioCount?: number
  audioCount?: number
  runCount?: number
  proves?: string[]
  doesNotProve?: string[]
  audioArtifacts?: EmbryVoiceAudioArtifact[]
  turns?: EmbryVoiceTurnEvidence[]
}

export interface EmbryVoiceChatLabProps {
  title?: string
  subtitle?: string
  adapter?: MemoryTurnAdapter
  adapterOptions?: EmbryVoiceChatAdapterOptions
  sanityRuns?: EmbryVoiceSanityRun[]
  turns?: EmbryVoiceTurnEvidence[]
  onRunSanityCheck?: (runId: string) => void | Promise<void>
  className?: string
}

export function EmbryVoiceChatLab({
  title = 'Embry Voice Chat Lab',
  subtitle = 'Memory-first chat and Chatterbox voice evidence',
  adapter,
  adapterOptions,
  sanityRuns = [],
  turns = [],
  onRunSanityCheck,
  className,
}: EmbryVoiceChatLabProps): JSX.Element {
  const resolvedAdapter = useMemo(
    () => adapter ?? new EmbryVoiceChatAdapter(adapterOptions),
    [adapter, adapterOptions],
  )
  const initialMessages = useMemo(() => turnsToMessages(turns), [turns])
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const voiceTurns = useMemo(() => mergeTurnsFromMessages(turns, messages), [messages, turns])
  const latestRun = sanityRuns[0]

  return (
    <section
      className={className}
      data-qid="embry:voice-chat-lab"
      style={{
        minHeight: 0,
        height: '100%',
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        background: '#080c0f',
        color: '#f3f7fb',
      }}
    >
      <header
        data-qid="embry:voice-chat-lab:header"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 18,
          padding: '16px 18px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, color: '#f3f7fb', fontSize: 18, fontWeight: 760 }}>
            <Mic size={19} strokeWidth={1.8} aria-hidden="true" />
            <span>{title}</span>
          </div>
          <div style={{ marginTop: 4, color: '#90a0b4', fontSize: 13 }}>{subtitle}</div>
        </div>
        <RunStatusPill run={latestRun} />
      </header>

      <div
        data-qid="embry:voice-chat-lab:body"
        style={{
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: 'minmax(420px, 1fr) minmax(360px, 0.82fr)',
          gap: 14,
          padding: 14,
        }}
      >
        <SharedChatShell
          projectLabel="Embry"
          surface="shared-chat"
          defaultMode="personaplex"
          showModeToggle={false}
          adapter={resolvedAdapter}
          messages={messages}
          onMessagesChange={setMessages}
          shellQid="embry:voice-chat:shell"
          qid="embry:voice-chat:well"
          placeholder="Talk to Embry…"
          emptyTitle="Embry is listening"
          emptyDescription="Voice turns must resolve speaker identity, memory intent, recall, Tau, and Chatterbox audio."
          starterChips={[
            { label: 'Memory check', prompt: 'What did we last talk about?' },
            { label: 'Identity check', prompt: 'Do you know who is speaking?' },
            { label: 'One at a time', prompt: 'What should you say when two people speak at once?' },
          ]}
        />

        <aside
          data-qid="embry:voice-chat-lab:evidence"
          style={{
            minHeight: 0,
            display: 'grid',
            gridTemplateRows: 'minmax(0, 1fr) minmax(220px, 0.92fr)',
            gap: 14,
          }}
        >
          <Panel title="Sanity Runs" icon={<FlaskConical size={17} strokeWidth={1.8} aria-hidden="true" />}>
            <SanityRunList runs={sanityRuns} onRunSanityCheck={onRunSanityCheck} />
          </Panel>
          <Panel title="Conversation Audio" icon={<Volume2 size={17} strokeWidth={1.8} aria-hidden="true" />}>
            <VoiceTurnList turns={voiceTurns} />
          </Panel>
        </aside>
      </div>
    </section>
  )
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }): JSX.Element {
  return (
    <section
      style={{
        minHeight: 0,
        display: 'grid',
        gridTemplateRows: 'auto 1fr',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 12,
        background: 'rgba(255,255,255,0.035)',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 13px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          color: '#dce8f6',
          fontWeight: 740,
        }}
      >
        {icon}
        <span>{title}</span>
      </header>
      <div style={{ minHeight: 0, overflow: 'auto', padding: 12 }}>{children}</div>
    </section>
  )
}

function SanityRunList({
  runs,
  onRunSanityCheck,
}: {
  runs: EmbryVoiceSanityRun[]
  onRunSanityCheck?: EmbryVoiceChatLabProps['onRunSanityCheck']
}): JSX.Element {
  if (!runs.length) {
    return <EmptyEvidence message="No sanity run receipt loaded." />
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {runs.map((run) => (
        <article
          key={run.id}
          data-qid="embry:voice-chat-lab:sanity-run"
          data-run-id={run.id}
          style={{
            borderRadius: 10,
            border: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.18)',
            padding: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 740 }}>
                <StatusIcon ok={run.ok} />
                <span>{run.label}</span>
              </div>
              <div style={{ marginTop: 5, color: '#9aa8ba', fontSize: 12, overflowWrap: 'anywhere' }}>{run.receiptPath}</div>
            </div>
            {onRunSanityCheck && (
              <button
                type="button"
                title="Run sanity check"
                onClick={() => void onRunSanityCheck(run.id)}
                style={iconButtonStyle}
              >
                <Radio size={16} strokeWidth={1.8} aria-hidden="true" />
              </button>
            )}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
            <FactPill label={run.live ? 'live' : 'live missing'} tone={run.live ? 'good' : 'bad'} />
            <FactPill label={run.mocked ? 'mocked' : 'not mocked'} tone={run.mocked ? 'bad' : 'good'} />
            {typeof run.scenarioCount === 'number' && <FactPill label={`${run.scenarioCount} scenarios`} />}
            {typeof run.runCount === 'number' && <FactPill label={`${run.runCount} runs`} />}
            {typeof run.audioCount === 'number' && <FactPill label={`${run.audioCount} audio`} />}
          </div>

          {run.failedGates?.length ? (
            <div style={{ marginTop: 10, color: '#ffb3b3', fontSize: 12 }}>
              failed gates: {run.failedGates.join(', ')}
            </div>
          ) : (
            <div style={{ marginTop: 10, color: '#9eddb9', fontSize: 12 }}>failed gates: []</div>
          )}

          <Claims run={run} />
          <AudioArtifactList artifacts={run.audioArtifacts ?? []} compact />
        </article>
      ))}
    </div>
  )
}

function VoiceTurnList({ turns }: { turns: EmbryVoiceTurnEvidence[] }): JSX.Element {
  if (!turns.length) return <EmptyEvidence message="No conversation voice artifacts loaded." />

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {turns.map((turn) => (
        <article
          key={turn.id}
          data-qid="embry:voice-chat-lab:voice-turn"
          style={{
            borderRadius: 10,
            border: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.18)',
            padding: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <div style={{ minWidth: 0, fontWeight: 740 }}>{turn.userText || 'Voice turn'}</div>
            <FactPill label={turn.live ? 'live' : 'receipt'} tone={turn.mocked ? 'bad' : undefined} />
          </div>
          <div style={{ marginTop: 8, color: '#dce8f6', lineHeight: 1.45 }}>{turn.assistantText}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
            {turn.speakerId && <FactPill label={`speaker ${turn.speakerId}`} />}
            {turn.speakerStatus && <FactPill label={turn.speakerStatus} tone={turn.speakerStatus === 'known' ? 'good' : 'warn'} />}
            {turn.tone && <FactPill label={turn.tone} />}
            {turn.memoryAction && <FactPill label={`memory ${turn.memoryAction}`} />}
            {typeof turn.memoryConfidence === 'number' && <FactPill label={`confidence ${turn.memoryConfidence.toFixed(3)}`} />}
            {typeof turn.qraCacheHit === 'boolean' && <FactPill label={turn.qraCacheHit ? 'QRA hit' : 'QRA miss'} tone={turn.qraCacheHit ? 'good' : 'warn'} />}
            {typeof turn.interruptionOldBytesAfterCancel === 'number' && (
              <FactPill
                label={`old bytes ${turn.interruptionOldBytesAfterCancel}`}
                tone={turn.interruptionOldBytesAfterCancel === 0 ? 'good' : 'bad'}
              />
            )}
          </div>
          <LatencyList latencyMs={turn.latencyMs} />
          <AudioArtifactList artifacts={turn.audioArtifacts ?? []} />
          {turn.receiptPath && <div style={{ marginTop: 8, color: '#8d9bae', fontSize: 12, overflowWrap: 'anywhere' }}>{turn.receiptPath}</div>}
        </article>
      ))}
    </div>
  )
}

function AudioArtifactList({ artifacts, compact = false }: { artifacts: EmbryVoiceAudioArtifact[]; compact?: boolean }): JSX.Element | null {
  if (!artifacts.length) return null
  return (
    <div style={{ display: 'grid', gap: compact ? 6 : 8, marginTop: compact ? 8 : 10 }}>
      {artifacts.map((artifact, index) => {
        const src = artifact.url ?? artifact.path
        return (
          <div key={artifact.id ?? artifact.path ?? artifact.url ?? index} style={{ display: 'grid', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#c9d7e8', fontSize: 12 }}>
              <PlayCircle size={14} strokeWidth={1.7} aria-hidden="true" />
              <span>{artifact.label ?? artifact.id ?? `audio ${index + 1}`}</span>
              {artifact.tone && <span style={{ color: '#8ea0b6' }}>{artifact.tone}</span>}
              {typeof artifact.durationSeconds === 'number' && <span style={{ color: '#8ea0b6' }}>{artifact.durationSeconds.toFixed(2)}s</span>}
            </div>
            {src ? (
              <audio controls preload="metadata" src={src} style={{ width: '100%', height: 34 }} />
            ) : (
              <div style={{ color: '#ffcf91', fontSize: 12 }}>Audio artifact has no browser-playable path or URL.</div>
            )}
            {artifact.sha256 && <div style={{ color: '#738397', fontSize: 11, overflowWrap: 'anywhere' }}>sha256 {artifact.sha256}</div>}
          </div>
        )
      })}
    </div>
  )
}

function Claims({ run }: { run: EmbryVoiceSanityRun }): JSX.Element | null {
  const proves = run.proves ?? []
  const doesNotProve = run.doesNotProve ?? []
  if (!proves.length && !doesNotProve.length) return null
  return (
    <div style={{ display: 'grid', gap: 5, marginTop: 10, color: '#aebbd0', fontSize: 12 }}>
      {proves.length > 0 && <div>proves: {proves.join('; ')}</div>}
      {doesNotProve.length > 0 && <div>does not prove: {doesNotProve.join('; ')}</div>}
    </div>
  )
}

function LatencyList({ latencyMs }: { latencyMs?: Record<string, number> }): JSX.Element | null {
  if (!latencyMs || !Object.keys(latencyMs).length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
      {Object.entries(latencyMs).map(([key, value]) => (
        <FactPill key={key} label={`${key} ${Math.round(value)}ms`} />
      ))}
    </div>
  )
}

function EmptyEvidence({ message }: { message: string }): JSX.Element {
  return (
    <div
      data-qid="embry:voice-chat-lab:empty-evidence"
      style={{
        display: 'grid',
        placeItems: 'center',
        minHeight: 120,
        border: '1px dashed rgba(255,255,255,0.13)',
        borderRadius: 10,
        color: '#93a2b6',
        textAlign: 'center',
        padding: 14,
      }}
    >
      {message}
    </div>
  )
}

function RunStatusPill({ run }: { run?: EmbryVoiceSanityRun }): JSX.Element {
  if (!run) return <FactPill label="no receipt" tone="warn" />
  if (run.ok) return <FactPill label="latest receipt ok" tone="good" />
  return <FactPill label="latest receipt has failures" tone="bad" />
}

function StatusIcon({ ok }: { ok?: boolean }): JSX.Element {
  if (ok === true) return <CheckCircle2 size={16} strokeWidth={1.8} color="#7ee2a8" aria-hidden="true" />
  if (ok === false) return <XCircle size={16} strokeWidth={1.8} color="#ff9f9f" aria-hidden="true" />
  return <AlertTriangle size={16} strokeWidth={1.8} color="#ffcf91" aria-hidden="true" />
}

function FactPill({ label, tone }: { label: string; tone?: 'good' | 'warn' | 'bad' }): JSX.Element {
  const color = tone === 'good' ? '#9ee8bd' : tone === 'bad' ? '#ffb3b3' : tone === 'warn' ? '#ffcf91' : '#b7c4d6'
  const border = tone === 'good' ? 'rgba(126,226,168,0.22)' : tone === 'bad' ? 'rgba(255,120,120,0.22)' : tone === 'warn' ? 'rgba(255,207,145,0.22)' : 'rgba(255,255,255,0.1)'
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        minHeight: 24,
        borderRadius: 8,
        border: `1px solid ${border}`,
        color,
        background: 'rgba(0,0,0,0.18)',
        padding: '3px 7px',
        fontSize: 12,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

function turnsToMessages(turns: EmbryVoiceTurnEvidence[]): ChatMessage[] {
  const messages: ChatMessage[] = []
  for (const turn of turns) {
    messages.push({
      id: `${turn.id}:user`,
      role: 'user',
      content: turn.userText,
      createdAt: new Date().toISOString(),
      metadata: { branch: 'personaplex', turnId: turn.id },
    })
    messages.push({
      id: `${turn.id}:assistant`,
      role: 'assistant',
      content: turn.assistantText,
      createdAt: new Date().toISOString(),
      skillUsed: 'embry-chatterbox-voice',
      metadata: {
        branch: 'personaplex',
        turnId: turn.id,
        personaId: 'embry',
        speakerId: turn.speakerId,
        tone: turn.tone,
        receiptPath: turn.receiptPath,
        audioArtifacts: turn.audioArtifacts,
        simultaneousTextVoice: true,
        memoryFirst: true,
      },
      reasoningSteps: turnToThinkingSteps(turn),
      thinkingTrace: turnToThinkingSteps(turn),
    })
  }
  return messages
}

function mergeTurnsFromMessages(turns: EmbryVoiceTurnEvidence[], messages: ChatMessage[]): EmbryVoiceTurnEvidence[] {
  const merged = [...turns]
  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]
    if (message.role !== 'assistant') continue
    const metadata = (message.metadata ?? {}) as UnknownRecord
    const audioArtifacts = normalizeAudioArtifacts(metadata.audioArtifacts ?? metadata.audio_artifacts)
    if (!audioArtifacts.length) continue
    const previous = previousUserMessage(messages, index)
    const id = stringValue(metadata.turnId ?? metadata.turn_id) ?? message.id
    if (merged.some((turn) => turn.id === id)) continue
    merged.push({
      id,
      userText: previous?.content ?? '',
      assistantText: message.content,
      speakerId: stringValue(metadata.speakerId ?? metadata.speaker_id),
      tone: stringValue(metadata.tone),
      receiptPath: stringValue(metadata.receiptPath ?? metadata.receipt_path),
      audioArtifacts,
      live: true,
      mocked: false,
    })
  }
  return merged
}

function previousUserMessage(messages: ChatMessage[], fromIndex: number): ChatMessage | undefined {
  for (let index = fromIndex - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'user') return messages[index]
  }
  return undefined
}

function turnToThinkingSteps(turn: EmbryVoiceTurnEvidence): ChatMessage['reasoningSteps'] {
  return [
    {
      id: 'speaker-resolve',
      label: 'Resolving speaker',
      status: turn.speakerStatus ? 'completed' : 'skipped',
      detail: turn.speakerId ? `${turn.speakerStatus ?? 'speaker'} ${turn.speakerId}` : undefined,
      icon: 'mic',
    },
    {
      id: 'memory-intent',
      label: 'Classifying memory intent',
      status: turn.memoryAction ? 'completed' : 'skipped',
      detail: turn.memoryAction,
      icon: 'memory',
    },
    {
      id: 'chatterbox-audio',
      label: 'Rendering Chatterbox audio',
      status: turn.audioArtifacts?.length ? 'completed' : 'skipped',
      detail: turn.audioArtifacts?.length ? `${turn.audioArtifacts.length} audio artifacts` : undefined,
      icon: 'mic',
    },
  ]
}

function normalizeAudioArtifacts(value: unknown): EmbryVoiceAudioArtifact[] {
  if (!Array.isArray(value)) return []
  return value.filter(isRecord).map((item, index) => ({
    id: stringValue(item.id) ?? `audio-${index + 1}`,
    label: stringValue(item.label),
    path: stringValue(item.path),
    url: stringValue(item.url),
    sha256: stringValue(item.sha256),
    durationSeconds: numberValue(item.durationSeconds ?? item.duration_seconds),
    bytes: numberValue(item.bytes),
    transcript: stringValue(item.transcript),
    tone: stringValue(item.tone),
  }))
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value && typeof value === 'object')
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

const iconButtonStyle: React.CSSProperties = {
  width: 34,
  height: 34,
  borderRadius: 8,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.06)',
  color: '#dce8f6',
  display: 'grid',
  placeItems: 'center',
  cursor: 'pointer',
}

export default EmbryVoiceChatLab
