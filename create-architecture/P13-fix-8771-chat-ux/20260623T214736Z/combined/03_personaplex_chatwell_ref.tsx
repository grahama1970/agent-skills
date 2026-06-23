import React, { useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import * as PersonaPlexVoiceTracePanelModule from '../sparta/explorer/PersonaPlexVoiceTracePanel'
import './PersonaPlexChatWell.css'
import {
  DEFAULT_PERSONAPLEX_PERSONA_ID,
  DEFAULT_PERSONAPLEX_WS_URL,
  makeSessionId,
  sendPersonaPlexSpeechFinalBestEffort,
  traceRowsFromEvents,
} from './personaplexProtocol'
import type { PersonaPlexChatMode, PersonaPlexTraceRow } from './personaplexProtocol'
import { useDeepgramVoiceInput } from './useDeepgramVoiceInput'


// Public mode contract for the shared ChatWell extension: 'personaplex' | 'compliance'.
const REQUIRED_PERSONAPLEX_REAL_FLAGS = [
  'real_personaplex_ws',
  'real_turn_gate',
  'real_memory_intent',
  'real_memory_recall',
  'real_evidence_case',
  'real_gpu_personaplex',
  'real_memory_upsert',
  'real_session_compaction',
]

const PersonaPlexVoiceTracePanel =
  ((PersonaPlexVoiceTracePanelModule as Record<string, unknown>).PersonaPlexVoiceTracePanel ??
    (PersonaPlexVoiceTracePanelModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>> | undefined

export interface UnifiedChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  createdAt?: string
  audioUrl?: string
}

export interface PersonaPlexChatWellProps {
  mode?: PersonaPlexChatMode
  defaultMode?: PersonaPlexChatMode
  onModeChange?: (mode: PersonaPlexChatMode) => void
  onSend?: (text: string, mode: PersonaPlexChatMode) => Promise<void> | void
  piChat?: { send: (text: string) => Promise<unknown> | unknown }
  messages?: UnifiedChatMessage[]
  initialMessages?: UnifiedChatMessage[]
  initialTraceRows?: PersonaPlexTraceRow[]
  isStreaming?: boolean
  streamingSteps?: React.ReactNode
  wsUrl?: string
  personaId?: string
  sessionId?: string
  deepgramApiKey?: string
  showModeToggle?: boolean
  showTracePanel?: boolean
  placeholder?: string
  title?: string
}

function makeMessage(role: UnifiedChatMessage['role'], content: string, audioUrl?: string): UnifiedChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    audioUrl,
    createdAt: new Date().toISOString(),
  }
}

function statusText(row: PersonaPlexTraceRow): string {
  return `${row.realFlag}=${row.real ? 'true' : 'false'}`
}

export function PersonaPlexChatWell(props: PersonaPlexChatWellProps) {
  const controlledMode = props.mode
  const [internalMode, setInternalMode] = useState<PersonaPlexChatMode>(props.defaultMode ?? 'compliance')
  const mode = controlledMode ?? internalMode
  const [input, setInput] = useState('')
  const [localMessages, setLocalMessages] = useState<UnifiedChatMessage[]>(props.initialMessages ?? [])
  const [traceRows, setTraceRows] = useState<PersonaPlexTraceRow[]>(props.initialTraceRows ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | undefined>()
  const sessionIdRef = useRef(props.sessionId ?? makeSessionId())
  const turnRef = useRef(0)

  const messages = props.messages ?? localMessages
  const personaId = props.personaId ?? DEFAULT_PERSONAPLEX_PERSONA_ID
  const wsUrl = props.wsUrl ?? DEFAULT_PERSONAPLEX_WS_URL

  const voice = useDeepgramVoiceInput({
    apiKey: props.deepgramApiKey,
    onTranscript: (text, final) => {
      if (final) setInput((current) => `${current} ${text}`.trim())
    },
    onError: setError,
  })

  const headerDetail = useMemo(() => {
    return mode === 'personaplex'
      ? `PersonaPlex voice • ${personaId} • ${wsUrl}`
      : 'SPARTA compliance • piChat.send()'
  }, [mode, personaId, wsUrl])

  function switchMode(nextMode: PersonaPlexChatMode) {
    setInternalMode(nextMode)
    props.onModeChange?.(nextMode)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setError(undefined)
    setBusy(true)
    setLocalMessages((current) => [...current, makeMessage('user', text)])

    try {
      if (mode === 'personaplex') {
        const turnId = ++turnRef.current
        const result = await sendPersonaPlexSpeechFinalBestEffort(text, {
          wsUrl,
          personaId,
          sessionId: sessionIdRef.current,
          turnId,
          onEvent: (evt) => setTraceRows((current) => traceRowsFromEvents([...current.map((row) => ({
            type: row.id,
            status: row.status,
            real_flags: { [row.realFlag]: row.real },
          })), evt])),
        })
        const nextRows = traceRowsFromEvents(result.events)
        setTraceRows(nextRows)
        if (result.generatedText || result.audioUrl) {
          setLocalMessages((current) => [
            ...current,
            makeMessage('assistant', result.generatedText ?? 'Embry audio response received.', result.audioUrl),
          ])
        }
        if (result.audioUrl) {
          const audio = new Audio(result.audioUrl)
          void audio.play().catch(() => undefined)
        }
        if (result.error && !result.generatedOutputReceived) setError(result.error)
      } else {
        if (props.onSend) {
          await props.onSend(text, mode)
        } else if (props.piChat) {
          await props.piChat.send(text)
        } else {
          setLocalMessages((current) => [
            ...current,
            makeMessage('system', 'Compliance mode is ready, but no piChat adapter was supplied.'),
          ])
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ppx-chat-shell" data-testid="personaplex-chat-well" data-mode={mode}>
      <header className="ppx-chat-header">
        <div>
          <p className="ppx-eyebrow">Unified ChatWell</p>
          <h2>{props.title ?? 'PersonaPlex + SPARTA Chat'}</h2>
          <p className="ppx-subtitle">{headerDetail}</p>
        </div>
        {(props.showModeToggle ?? true) && (
          <div className="ppx-mode-toggle" role="tablist" aria-label="Chat mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'compliance'}
              className={mode === 'compliance' ? 'active' : ''}
              onClick={() => switchMode('compliance')}
            >
              Compliance
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'personaplex'}
              className={mode === 'personaplex' ? 'active' : ''}
              onClick={() => switchMode('personaplex')}
            >
              PersonaPlex
            </button>
          </div>
        )}
      </header>

      <div className="ppx-chat-grid">
        <main className="ppx-card ppx-conversation" aria-label="Conversation">
          <div className="ppx-message-list">
            {messages.length === 0 ? (
              <div className="ppx-empty-state">
                <span className="material-symbols-rounded" aria-hidden="true">forum</span>
                <strong>Ask Embry by voice or type a compliance question.</strong>
                <p>PersonaPlex mode sends speech_final to golden_state_server. Compliance mode preserves piChat.send().</p>
              </div>
            ) : (
              messages.map((message) => (
                <article className={`ppx-message ${message.role}`} key={message.id}>
                  <div className="ppx-message-role">{message.role}</div>
                  <p>{message.content}</p>
                  {message.audioUrl && <audio controls src={message.audioUrl} />}
                </article>
              ))
            )}
          </div>

          {props.streamingSteps && <div className="ppx-streaming-steps">{props.streamingSteps}</div>}
          {props.isStreaming && <div className="ppx-pulse">Streaming…</div>}
          {voice.partialTranscript && <div className="ppx-transcript">{voice.partialTranscript}</div>}
          {(error || voice.error) && <div className="ppx-error" role="alert">{error ?? voice.error}</div>}

          <form className="ppx-input-row" onSubmit={handleSubmit}>
            <button
              type="button"
              className={`ppx-icon-button ${voice.isRecording ? 'recording' : ''}`}
              aria-label={voice.isRecording ? 'Stop microphone' : 'Start microphone'}
              title={voice.isRecording ? 'Stop microphone' : 'Start microphone'}
              onClick={() => (voice.isRecording ? voice.stop() : void voice.start())}
              disabled={voice.isConnecting}
            >
              <span className="material-symbols-rounded" aria-hidden="true">{voice.isRecording ? 'stop_circle' : 'mic'}</span>
            </button>
            <textarea
              value={input}
              onChange={(event) => setInput(event.currentTarget.value)}
              placeholder={props.placeholder ?? (mode === 'personaplex' ? 'Speak or type to Embry…' : 'Ask a SPARTA compliance question…')}
              rows={2}
            />
            <button type="submit" className="ppx-send-button" disabled={busy || !input.trim()}>
              <span className="material-symbols-rounded" aria-hidden="true">send</span>
              Send
            </button>
          </form>
        </main>

        <aside className="ppx-card ppx-tool-trace" aria-label="Tool trace">
          <div className="ppx-trace-heading">
            <h3>Tool trace</h3>
            <span>{mode === 'personaplex' ? 'live PersonaPlex' : 'compliance adapter'}</span>
          </div>
          <div className="ppx-trace-table" data-testid="real-flag-table">
            {(traceRows.length === 0
              ? REQUIRED_PERSONAPLEX_REAL_FLAGS.map((flag) => ({
                  id: flag,
                  label: flag.replace(/^real_/, '').replaceAll('_', ' '),
                  status: 'pending' as const,
                  realFlag: flag,
                  real: false,
                  detail: 'waiting for live turn',
                }))
              : traceRows
            ).map((row) => (
              <div className={`ppx-trace-row ${row.real ? 'real' : 'fallback'}`} key={row.id}>
                <span>{row.label}</span>
                <code>{statusText(row)}</code>
                {row.detail && <small>{row.detail}</small>}
              </div>
            ))}
          </div>
          {mode === 'personaplex' && (props.showTracePanel ?? true) && PersonaPlexVoiceTracePanel && (
            <div className="ppx-native-trace-panel" data-testid="personaplex-voice-trace-panel">
              <PersonaPlexVoiceTracePanel wsUrl={wsUrl} sessionId={sessionIdRef.current} personaId={personaId} />
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}

export default PersonaPlexChatWell
