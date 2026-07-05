import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { EmbryVoiceChatAdapter, type EmbryTurnAuthority, type EmbryVoiceAudioAuthority, type EmbryVoiceChatAdapterOptions } from './memory-turn'

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
  audioAuthority?: EmbryVoiceAudioAuthority
  turnAuthority?: EmbryTurnAuthority
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
      {artifacts.map((artifact, index) => (
        <AudioArtifactCard key={artifact.id ?? artifact.path ?? artifact.url ?? index} artifact={artifact} index={index} compact={compact} />
      ))}
    </div>
  )
}

function AudioArtifactCard({ artifact, index, compact }: { artifact: EmbryVoiceAudioArtifact; index: number; compact: boolean }): JSX.Element {
  const [audioElement, setAudioElement] = useState<HTMLAudioElement | null>(null)
  const setAudioRef = useCallback((node: HTMLAudioElement | null) => setAudioElement(node), [])
  const src = artifact.url ?? artifact.path
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#c9d7e8', fontSize: 12 }}>
        <PlayCircle size={14} strokeWidth={1.7} aria-hidden="true" />
        <span>{artifact.label ?? artifact.id ?? `audio ${index + 1}`}</span>
        {artifact.tone && <span style={{ color: '#8ea0b6' }}>{artifact.tone}</span>}
        {typeof artifact.durationSeconds === 'number' && <span style={{ color: '#8ea0b6' }}>{artifact.durationSeconds.toFixed(2)}s</span>}
      </div>
      {src ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: compact ? '1fr' : '96px minmax(0, 1fr)',
            alignItems: 'center',
            gap: compact ? 6 : 10,
          }}
        >
          {!compact && <AnswerParticleAnimation audioElement={audioElement} artifact={artifact} />}
          <audio ref={setAudioRef} controls preload="metadata" src={src} style={{ width: '100%', height: 34 }} />
        </div>
      ) : (
        <div style={{ color: '#ffcf91', fontSize: 12 }}>Audio artifact has no browser-playable path or URL.</div>
      )}
      {artifact.sha256 && <div style={{ color: '#738397', fontSize: 11, overflowWrap: 'anywhere' }}>sha256 {artifact.sha256}</div>}
    </div>
  )
}

function AnswerParticleAnimation({ audioElement, artifact }: { audioElement: HTMLAudioElement | null; artifact: EmbryVoiceAudioArtifact }): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const energyRef = useRef(0.08)
  const lastVoiceAtRef = useRef(0)
  const toneProfile = useMemo(() => particleToneProfile(artifact), [artifact])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    let frameId = 0
    let analyserBundle: AudioAnalyserBundle | null = null
    let analyserFailed = false
    const frequencyData = new Uint8Array(512)
    const timeData = new Uint8Array(512)

    const draw = (time: number) => {
      const width = 96
      const height = 64
      const dpr = window.devicePixelRatio || 1
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
        canvas.style.width = `${width}px`
        canvas.style.height = `${height}px`
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      context.clearRect(0, 0, width, height)

      const playing = Boolean(audioElement && !audioElement.paused && !audioElement.ended)
      if (audioElement && playing && !analyserFailed) {
        try {
          analyserBundle = analyserBundle ?? getAudioAnalyserBundle(audioElement)
          if (analyserBundle.context.state === 'suspended') void analyserBundle.context.resume()
          analyserBundle.analyser.getByteFrequencyData(analyserBundle.frequencyData)
          analyserBundle.analyser.getByteTimeDomainData(analyserBundle.timeData)
          frequencyData.set(analyserBundle.frequencyData.subarray(0, frequencyData.length))
          timeData.set(analyserBundle.timeData.subarray(0, timeData.length))
        } catch {
          analyserFailed = true
        }
      }

      const audioEnergy = playing && !analyserFailed ? calculateAudioEnergy(frequencyData, timeData) : null
      if (playing && (!audioEnergy || audioEnergy.amplitude > 0.015)) lastVoiceAtRef.current = time
      const recentlyVoiced = time - lastVoiceAtRef.current < 4200
      const fallbackSpeakingEnergy = playing ? 0.13 + toneProfile.activity : recentlyVoiced ? 0.11 : 0.045
      const targetEnergy = audioEnergy
        ? Math.max(audioEnergy.amplitude, audioEnergy.low * 0.42 + audioEnergy.mid * 0.32 + audioEnergy.high * 0.22, toneProfile.activity)
        : fallbackSpeakingEnergy
      const decay = audioEnergy ? 0.72 : recentlyVoiced ? 0.985 : 0.965
      energyRef.current = Math.max(targetEnergy, energyRef.current * decay)

      const low = audioEnergy?.low ?? toneProfile.warmth * 0.12
      const mid = audioEnergy?.mid ?? toneProfile.activity * 0.12
      const high = audioEnergy?.high ?? toneProfile.jitter * 0.1
      drawParticles(context, width, height, time, energyRef.current, low, mid, high, toneProfile)
      frameId = window.requestAnimationFrame(draw)
    }

    frameId = window.requestAnimationFrame(draw)
    return () => window.cancelAnimationFrame(frameId)
  }, [audioElement, toneProfile])

  return (
    <canvas
      ref={canvasRef}
      aria-label="Embry answer voice particles"
      role="img"
      style={{
        display: 'block',
        width: 96,
        height: 64,
        borderRadius: 10,
        border: '1px solid rgba(124,228,255,0.18)',
        background: 'radial-gradient(circle at 50% 50%, rgba(124,228,255,0.12), rgba(0,0,0,0.16) 62%, rgba(0,0,0,0.26))',
      }}
    />
  )
}

type AudioAnalyserBundle = {
  context: AudioContext
  analyser: AnalyserNode
  frequencyData: Uint8Array
  timeData: Uint8Array
}

const audioAnalyserBundles = new WeakMap<HTMLAudioElement, AudioAnalyserBundle>()

function getAudioAnalyserBundle(audioElement: HTMLAudioElement): AudioAnalyserBundle {
  const cached = audioAnalyserBundles.get(audioElement)
  if (cached) return cached
  const context = new AudioContext()
  const source = context.createMediaElementSource(audioElement)
  const analyser = context.createAnalyser()
  analyser.fftSize = 1024
  analyser.smoothingTimeConstant = 0.78
  source.connect(analyser)
  analyser.connect(context.destination)
  const bundle = {
    context,
    analyser,
    frequencyData: new Uint8Array(analyser.frequencyBinCount),
    timeData: new Uint8Array(analyser.fftSize),
  }
  audioAnalyserBundles.set(audioElement, bundle)
  return bundle
}

function calculateAudioEnergy(frequencyData: Uint8Array, timeData: Uint8Array): { amplitude: number; low: number; mid: number; high: number } {
  let sumSquares = 0
  for (const sample of timeData) {
    const centered = (sample - 128) / 128
    sumSquares += centered * centered
  }
  const amplitude = Math.min(1, Math.sqrt(sumSquares / Math.max(1, timeData.length)) * 2.4)
  const low = averageBand(frequencyData, 0.02, 0.16)
  const mid = averageBand(frequencyData, 0.16, 0.48)
  const high = averageBand(frequencyData, 0.48, 0.92)
  return { amplitude, low, mid, high }
}

function averageBand(data: Uint8Array, startRatio: number, endRatio: number): number {
  const start = Math.max(0, Math.floor(data.length * startRatio))
  const end = Math.max(start + 1, Math.min(data.length, Math.floor(data.length * endRatio)))
  let total = 0
  for (let index = start; index < end; index += 1) total += data[index] ?? 0
  return Math.min(1, total / (end - start) / 255)
}

function particleToneProfile(artifact: EmbryVoiceAudioArtifact): { activity: number; warmth: number; jitter: number; laugh: number } {
  const text = `${artifact.tone ?? ''} ${artifact.transcript ?? ''}`.toLowerCase()
  const laugh = /\b(laugh|laughs|laughing|chuckle|chuckles|giggle|giggles|amused)\b/.test(text) ? 1 : 0
  const urgent = /\b(urgent|angry|sharp|fast|excited|alarm|interrupt)\b/.test(text) ? 1 : 0
  const warm = /\b(warm|soft|gentle|calm|kind|relieved|playful)\b/.test(text) ? 1 : 0
  return {
    activity: 0.035 + urgent * 0.09 + laugh * 0.08,
    warmth: 0.18 + warm * 0.22 + laugh * 0.12,
    jitter: 0.12 + urgent * 0.28 + laugh * 0.22,
    laugh,
  }
}

function drawParticles(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  energy: number,
  low: number,
  mid: number,
  high: number,
  toneProfile: { activity: number; warmth: number; jitter: number; laugh: number },
): void {
  const centerX = width / 2
  const centerY = height / 2
  const baseRadius = 15 + low * 12 + energy * 12
  const orbit = time * (0.00035 + mid * 0.0014 + toneProfile.activity * 0.001)
  const count = 46
  context.save()
  context.globalCompositeOperation = 'lighter'
  for (let index = 0; index < count; index += 1) {
    const fraction = index / count
    const angle = fraction * Math.PI * 2 + orbit * (index % 3 === 0 ? 1.35 : -0.72)
    const phraseWave = Math.sin(time * 0.0032 + index * 0.77)
    const laughHop = toneProfile.laugh ? Math.sin(time * 0.014 + index) * high * 4 : 0
    const radius = baseRadius + phraseWave * (2 + energy * 7) + ((index % 5) - 2) * high * 2
    const x = centerX + Math.cos(angle) * radius + Math.sin(time * 0.002 + index * 1.9) * toneProfile.jitter * 4
    const y = centerY + Math.sin(angle) * (radius * 0.64) + laughHop
    const size = 1.15 + energy * 2.9 + high * (index % 4 === 0 ? 2.1 : 0.7)
    const hue = 184 + toneProfile.warmth * 28 + high * 34 + (index % 7) * 2
    context.beginPath()
    context.fillStyle = `hsla(${hue}, 92%, ${62 + Math.min(18, energy * 18)}%, ${0.28 + Math.min(0.62, energy * 0.95)})`
    context.arc(x, y, size, 0, Math.PI * 2)
    context.fill()
  }
  context.strokeStyle = `rgba(124, 228, 255, ${0.1 + Math.min(0.32, energy * 0.42)})`
  context.lineWidth = 1
  context.beginPath()
  context.ellipse(centerX, centerY, baseRadius + 4, (baseRadius + 4) * 0.64, orbit * 0.08, 0, Math.PI * 2)
  context.stroke()
  context.restore()
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
        audioAuthority: turn.audioAuthority ?? turn.turnAuthority?.audioAuthority,
        turnAuthority: turn.turnAuthority ?? turnAuthorityFromEvidence(turn),
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
    const turnAuthority = normalizeTurnAuthority(metadata.turnAuthority ?? metadata.turn_authority)
    const audioAuthority = normalizeAudioAuthority(metadata.audioAuthority ?? metadata.audio_authority ?? turnAuthority?.audioAuthority)
    const audioArtifacts = normalizeAudioArtifacts(metadata.audioArtifacts ?? metadata.audio_artifacts, audioAuthority)
    if (!audioArtifacts.length) continue
    const previous = previousUserMessage(messages, index)
    const id = stringValue(metadata.turnId ?? metadata.turn_id ?? turnAuthority?.turnId) ?? message.id
    if (merged.some((turn) => turn.id === id)) continue
    merged.push({
      id,
      userText: turnAuthority?.userText ?? previous?.content ?? '',
      assistantText: turnAuthority?.assistantText ?? message.content,
      speakerId: stringValue(metadata.speakerId ?? metadata.speaker_id ?? turnAuthority?.speakerId),
      tone: stringValue(metadata.tone),
      receiptPath: stringValue(metadata.receiptPath ?? metadata.receipt_path ?? turnAuthority?.receiptPath),
      audioAuthority,
      turnAuthority,
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

function normalizeAudioArtifacts(value: unknown, audioAuthority?: EmbryVoiceAudioAuthority): EmbryVoiceAudioArtifact[] {
  const records = Array.isArray(value) ? value.filter(isRecord) : []
  if (!records.length && audioAuthority && (audioAuthority.url || audioAuthority.path)) records.push(audioAuthority as UnknownRecord)
  return records.map((item, index) => ({
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

function turnAuthorityFromEvidence(turn: EmbryVoiceTurnEvidence): EmbryTurnAuthority {
  return {
    turnId: turn.id,
    userText: turn.userText,
    assistantText: turn.assistantText,
    personaId: 'embry',
    speakerId: turn.speakerId,
    createdAt: new Date().toISOString(),
    memoryFirst: true,
    simultaneousTextVoice: true,
    receiptPath: turn.receiptPath,
    audioAuthority: turn.audioAuthority,
    audioArtifacts: (turn.audioArtifacts ?? []) as UnknownRecord[],
    live: turn.live,
    mocked: turn.mocked,
  }
}

function normalizeTurnAuthority(value: unknown): EmbryTurnAuthority | undefined {
  if (!isRecord(value)) return undefined
  const turnId = stringValue(value.turnId ?? value.turn_id)
  const userText = stringValue(value.userText ?? value.user_text)
  const assistantText = stringValue(value.assistantText ?? value.assistant_text)
  if (!turnId || !userText || !assistantText) return undefined
  return {
    turnId,
    userText,
    assistantText,
    personaId: stringValue(value.personaId ?? value.persona_id) ?? 'embry',
    speakerId: stringValue(value.speakerId ?? value.speaker_id),
    sessionId: stringValue(value.sessionId ?? value.session_id),
    createdAt: stringValue(value.createdAt ?? value.created_at) ?? new Date().toISOString(),
    memoryFirst: true,
    simultaneousTextVoice: true,
    receiptPath: stringValue(value.receiptPath ?? value.receipt_path),
    audioAuthority: normalizeAudioAuthority(value.audioAuthority ?? value.audio_authority),
    audioArtifacts: Array.isArray(value.audioArtifacts) ? value.audioArtifacts.filter(isRecord) : [],
    memoryTrace: value.memoryTrace ?? value.memory_trace,
    tauTrace: value.tauTrace ?? value.tau_trace,
    live: value.live === true,
    mocked: value.mocked === true,
  }
}

function normalizeAudioAuthority(value: unknown): EmbryVoiceAudioAuthority | undefined {
  if (!isRecord(value)) return undefined
  return {
    authority: stringValue(value.authority),
    artifactId: stringValue(value.artifactId ?? value.artifact_id),
    url: stringValue(value.url),
    path: stringValue(value.path),
    sha256: stringValue(value.sha256),
    durationMs: numberValue(value.durationMs ?? value.duration_ms),
    localPlayback: isRecord(value.localPlayback) ? value.localPlayback : isRecord(value.local_playback) ? value.local_playback : null,
    envelope: isRecord(value.envelope) ? value.envelope : undefined,
  }
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
