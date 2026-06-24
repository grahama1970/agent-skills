import React, { useMemo, useRef, useState } from 'react'
import { Mic, Shield } from 'lucide-react'
import ComplianceChatWell, { type ComplianceChatWellProps, type StarterChip } from './ComplianceChatWell'
import {
  createAdapterRegistry,
  errorToMessage,
  isAsyncIterable,
  makeMessageId,
  type ChatMessage,
  type MemoryTurnAdapter,
  type PersonaPlexAdapterOptions,
  type SpartaComplianceAdapterOptions,
  type StreamingStep,
  type TurnInput,
  type TurnSurface,
  type WatchChatAdapterOptions,
} from './memory-turn'

export type PersonaPlexChatMode = 'compliance' | 'personaplex'

export type SharedChatAdapterOptions = {
  sparta?: SpartaComplianceAdapterOptions
  watch?: WatchChatAdapterOptions
  personaplex?: PersonaPlexAdapterOptions
}

export type SharedChatShellProps = Omit<
  ComplianceChatWellProps,
  'messages' | 'onSend' | 'starterChips'
> & {
  projectLabel?: string
  messages?: ChatMessage[]
  initialMessages?: ChatMessage[]
  onMessagesChange?: (messages: ChatMessage[]) => void
  onSend?: (text: string) => void | Promise<void>
  streamingSteps?: StreamingStep[]
  isStreaming?: boolean
  activeBranch?: TurnBranch
  showModeToggle?: boolean
  defaultMode?: PersonaPlexChatMode
  onModeChange?: (mode: PersonaPlexChatMode) => void
  surface?: TurnSurface
  adapter?: MemoryTurnAdapter
  adapterOptions?: SharedChatAdapterOptions
  shellQid?: string
  hideHeader?: boolean
  context?: TurnInput['context']
  matrixContext?: TurnInput['matrixContext']
  starterChips?: StarterChip[]
}

export function SharedChatShell({
  projectLabel = 'SPARTA Chat',
  messages,
  initialMessages = [],
  onMessagesChange,
  onSend,
  streamingSteps: externalStreamingSteps,
  isStreaming: externalIsStreaming,
  activeBranch: externalActiveBranch,
  showModeToggle = true,
  defaultMode = 'compliance',
  onModeChange,
  surface = 'shared-chat',
  adapter,
  adapterOptions,
  shellQid,
  hideHeader = false,
  context,
  matrixContext,
  starterChips,
  placeholder,
  disabled,
  composerDisabled,
  showComposer,
  emptyTitle,
  emptyDescription,
  qid,
  className,
}: SharedChatShellProps): JSX.Element {
  const [mode, setModeState] = useState<PersonaPlexChatMode>(defaultMode)
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>(initialMessages)
  const [internalStreamingSteps, setInternalStreamingSteps] = useState<StreamingStep[]>([])
  const [internalIsStreaming, setIsInternalStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const controlled = messages !== undefined
  const isExternalMode = onSend !== undefined
  const displayMessages = messages ?? internalMessages
  const displayStreamingSteps = isExternalMode && externalStreamingSteps ? externalStreamingSteps : internalStreamingSteps
  const displayIsStreaming = isExternalMode ? (externalIsStreaming ?? false) : internalIsStreaming
  const displayActiveBranch = externalActiveBranch ?? (surface === 'watch' ? 'watch' : mode === 'personaplex' ? 'personaplex' : undefined)

  const registry = useMemo(
    () =>
      createAdapterRegistry({
        surface,
        mode,
        sparta: adapterOptions?.sparta,
        watch: adapterOptions?.watch,
        personaplex: adapterOptions?.personaplex,
      }),
    [adapterOptions?.personaplex, adapterOptions?.sparta, adapterOptions?.watch, mode, surface],
  )

  function setMode(nextMode: PersonaPlexChatMode): void {
    setModeState(nextMode)
    onModeChange?.(nextMode)
  }

  function replaceMessages(nextMessages: ChatMessage[]): void {
    if (!controlled) setInternalMessages(nextMessages)
    onMessagesChange?.(nextMessages)
  }


  async function handleSend(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return

    if (onSend) {
      await onSend(trimmed)
      return
    }

    const userMessage: ChatMessage = {
      id: makeMessageId('user'),
      role: 'user',
      content: trimmed,
      createdAt: new Date().toISOString(),
      metadata: { surface, mode },
    }

    const baseMessages = [...displayMessages, userMessage]
    replaceMessages(baseMessages)
    setInternalStreamingSteps([])
    setIsInternalStreaming(true)

    const abortController = new AbortController()
    abortRef.current = abortController

    try {
      const activeAdapter =
        adapter ??
        registry.getAdapter({
          text: trimmed,
          mode,
          surface,
          branchHint: surface === 'watch' ? 'watch' : undefined,
        })

      const result = activeAdapter.sendTurn({
        text: trimmed,
        mode,
        surface,
        messages: baseMessages,
        context,
        matrixContext,
        abortSignal: abortController.signal,
      })

      let finalMessage: ChatMessage | undefined
      const awaited = await result
      if (isAsyncIterable<StreamingStep>(awaited)) {
        const iterator = awaited[Symbol.asyncIterator]()
        for (;;) {
          const next = await iterator.next()
          if (next.done) {
            const returned = next.value as ChatMessage | void
            if (returned) finalMessage = returned
            break
          }
          const step = next.value as StreamingStep
          setInternalStreamingSteps((previous) => [...previous, step])
          if (step.kind === 'final' && step.message) finalMessage = step.message
        }
      } else {
        finalMessage = awaited as ChatMessage
      }

      if (finalMessage) replaceMessages([...baseMessages, finalMessage])
    } catch (error) {
      replaceMessages([
        ...baseMessages,
        {
          id: makeMessageId('assistant-error'),
          role: 'assistant',
          content: `I could not complete that turn: ${errorToMessage(error)}`,
          createdAt: new Date().toISOString(),
          metadata: { surface, mode, error: errorToMessage(error), branch: mode === 'personaplex' ? 'personaplex' : 'compliance' },
        },
      ])
    } finally {
      setIsInternalStreaming(false)
      abortRef.current = null
    }
  }
  const shellId = shellQid ?? (surface === 'watch' ? 'watch:chat:shell' : surface === 'sparta-explorer' ? 'sparta:chat:shell:slideover' : 'shared-chat:shell')

  return (
    <section
      data-qid={shellId}
      data-surface={surface}
      data-mode={mode}
      className={className}
      style={{ minHeight: 0, height: '100%', display: 'grid', gridTemplateRows: hideHeader ? '1fr' : 'auto 1fr', gap: hideHeader ? 0 : 12 }}
    >
      {!hideHeader && (
        <header
          data-qid={`${shellId}:header`}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            minWidth: 0,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ color: '#eef5ff', fontWeight: 760, letterSpacing: '-0.02em' }}>{projectLabel}</div>
            <div style={{ marginTop: 2, color: '#8e9aab', fontSize: 12 }}>Shared ComplianceChatWell renderer</div>
          </div>
          {showModeToggle && <ModeToggle mode={mode} onModeChange={setMode} />}
        </header>
      )}

      {hideHeader && showModeToggle && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', paddingBottom: 10 }}>
          <ModeToggle mode={mode} onModeChange={setMode} />
        </div>
      )}

      <ComplianceChatWell
        messages={displayMessages}
        streamingSteps={displayStreamingSteps}
        isStreaming={displayIsStreaming}
        activeBranch={displayActiveBranch}
        onSend={(value) => void handleSend(value)}
        placeholder={placeholder ?? (mode === 'personaplex' ? 'Ask Embry…' : 'Ask SPARTA…')}
        disabled={disabled}
        composerDisabled={composerDisabled}
        showComposer={showComposer}
        emptyTitle={emptyTitle ?? (surface === 'watch' ? 'Hello, Graham' : 'Ask anything')}
        emptyDescription={emptyDescription}
        starterChips={starterChips}
        qid={qid ?? `${shellId}:well`}
        surface={surface}
      />
    </section>
  )
}

function ModeToggle({
  mode,
  onModeChange,
}: {
  mode: PersonaPlexChatMode
  onModeChange: (mode: PersonaPlexChatMode) => void
}): JSX.Element {
  return (
    <div
      role="tablist"
      aria-label="Chat mode"
      data-qid="sparta:chat:mode-toggle"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: 4,
        borderRadius: 999,
        border: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(255,255,255,0.045)',
      }}
    >
      <ModeButton mode="compliance" active={mode === 'compliance'} label="Compliance" title="SPARTA compliance chat with evidence receipts" qid="sparta:chat:mode:compliance" onClick={onModeChange} />
      <ModeButton mode="personaplex" active={mode === 'personaplex'} label="Persona" title="Embry PersonaPlex voice chat" qid="sparta:chat:mode:personaplex" onClick={onModeChange} />
    </div>
  )
}

function ModeButton({
  mode,
  active,
  label,
  title,
  qid,
  onClick,
}: {
  mode: PersonaPlexChatMode
  active: boolean
  label: string
  title: string
  qid: string
  onClick: (mode: PersonaPlexChatMode) => void
}): JSX.Element {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-qid={qid}
      data-qs-action={mode === 'compliance' ? 'CHAT_MODE_COMPLIANCE' : 'CHAT_MODE_PERSONAPLEX'}
      title={title}
      onClick={() => onClick(mode)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        border: 0,
        borderRadius: 999,
        padding: '7px 11px',
        background: active ? '#00ff88' : 'transparent',
        color: active ? '#06130d' : '#c8d2e1',
        cursor: 'pointer',
        font: 'inherit',
        fontSize: 12,
        fontWeight: 720,
      }}
    >
      {mode === 'compliance' ? <Shield size={15} strokeWidth={1.8} aria-hidden="true" /> : <Mic size={15} strokeWidth={1.8} aria-hidden="true" />}
      <span>{label}</span>
    </button>
  )
}

export default SharedChatShell
