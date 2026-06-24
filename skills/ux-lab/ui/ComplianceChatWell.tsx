import React, { FormEvent, useMemo, useState } from 'react'
import { ArrowUp, Shield, Sparkles } from 'lucide-react'
import type { ChatMessage, StreamingStep, TurnBranch } from './memory-turn'
import { liveStatusLabelFromSteps, streamingStepsToThinkingTrace } from './memory-turn'
import MessageFooter from './MessageFooter'
import ThinkingTrace from './ThinkingTrace'
import {
  branchFromMessage,
  branchFromSteps,
  leadingIconForBranch,
  thinkingStepsForMessage,
  thinkingTraceDisclosureParts,
} from './thinkingTraceHelpers'

export interface StarterChip {
  label: string
  prompt: string
  dataQid?: string
}

export interface ComplianceChatWellProps {
  messages?: ChatMessage[]
  streamingSteps?: StreamingStep[]
  isStreaming?: boolean
  liveAssistantMessage?: ChatMessage
  onSend?: (text: string) => void | Promise<void>
  placeholder?: string
  disabled?: boolean
  composerDisabled?: boolean
  showComposer?: boolean
  emptyTitle?: string
  emptyDescription?: string
  starterChips?: StarterChip[]
  qid?: string
  surface?: string
  className?: string
  activeBranch?: TurnBranch
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
}: ComplianceChatWellProps): JSX.Element {
  const [draft, setDraft] = useState('')
  const liveBranch = activeBranch ?? branchFromSteps(streamingSteps) ?? branchFromMessage(liveAssistantMessage) ?? 'compliance'
  const disclosure = thinkingTraceDisclosureParts({ branch: liveBranch, message: liveAssistantMessage, streamingSteps })
  const liveTraceSteps = streamingStepsToThinkingTrace(streamingSteps)
  const liveStatus = liveStatusLabelFromSteps(streamingSteps, disclosure.liveStatusLabel)

  const renderedMessages = useMemo(() => {
    if (!liveAssistantMessage) return messages
    return [...messages, liveAssistantMessage]
  }, [liveAssistantMessage, messages])

  async function submit(event?: FormEvent): Promise<void> {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || disabled || composerDisabled || !onSend) return
    setDraft('')
    await onSend(text)
  }

  return (
    <section
      className={className}
      data-qid={qid}
      data-surface={surface}
      style={{
        minHeight: 0,
        height: '100%',
        display: 'grid',
        gridTemplateRows: '1fr auto',
        background: 'linear-gradient(180deg, rgba(12,16,22,0.98), rgba(7,10,14,0.98))',
        color: '#f2f6fb',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: 22,
        overflow: 'hidden',
      }}
    >
      <div
        data-qid={`${qid}:messages`}
        style={{ overflow: 'auto', padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        {renderedMessages.length === 0 && !isStreaming ? (
          <EmptyState title={emptyTitle} description={emptyDescription} chips={starterChips} onChip={(prompt) => { setDraft(prompt); void onSend?.(prompt) }} />
        ) : (
          renderedMessages.map((message) => <MessageBubble key={message.id} message={message} />)
        )}

        {isStreaming && (
          <div
            data-qid={`${qid}:streaming`}
            style={{
              alignSelf: 'stretch',
              borderRadius: 18,
              border: '1px solid rgba(0,255,136,0.16)',
              background: 'rgba(0,255,136,0.04)',
              padding: 14,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, color: '#dce8f6', fontSize: 13, fontWeight: 700 }}>
              {liveBranch === 'watch' ? <Sparkles size={16} /> : <Shield size={16} />}
              <span>{liveStatus}</span>
            </div>
            <ThinkingTrace
              steps={liveTraceSteps}
              title={disclosure.title}
              label={disclosure.label}
              currentLabel={liveStatus}
              disclosureVariant={disclosure.disclosureVariant}
              leadingIcon={disclosure.leadingIcon}
              displayMode="current"
              defaultOpen
              isStreaming
              dataQid={`${qid}:streaming-trace`}
            />
          </div>
        )}
      </div>

      {showComposer && (
        <form
          data-qid={`${qid}:composer`}
          onSubmit={(event) => { void submit(event) }}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: 10,
            padding: 14,
            borderTop: '1px solid rgba(255,255,255,0.08)',
            background: 'rgba(0,0,0,0.22)',
          }}
        >
          <textarea
            data-qid={`${qid}:input`}
            value={draft}
            onChange={(event) => setDraft(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void submit()
              }
            }}
            placeholder={placeholder}
            disabled={disabled || composerDisabled || isStreaming}
            rows={1}
            style={{
              resize: 'none',
              minHeight: 42,
              maxHeight: 120,
              borderRadius: 16,
              border: '1px solid rgba(255,255,255,0.1)',
              background: 'rgba(255,255,255,0.045)',
              color: '#f2f6fb',
              padding: '12px 14px',
              outline: 'none',
              font: 'inherit',
            }}
          />
          <button
            type="submit"
            data-qid={`${qid}:send`}
            disabled={disabled || composerDisabled || isStreaming || !draft.trim()}
            title="Send"
            style={{
              width: 44,
              height: 44,
              borderRadius: 16,
              border: '1px solid rgba(0,255,136,0.35)',
              background: draft.trim() && !isStreaming ? '#00ff88' : 'rgba(255,255,255,0.08)',
              color: draft.trim() && !isStreaming ? '#06130d' : '#9aa6b6',
              display: 'grid',
              placeItems: 'center',
              cursor: draft.trim() && !isStreaming ? 'pointer' : 'not-allowed',
            }}
          >
            <ArrowUp size={18} strokeWidth={2} aria-hidden="true" />
          </button>
        </form>
      )}
    </section>
  )
}

function EmptyState({
  title,
  description,
  chips,
  onChip,
}: {
  title: string
  description: string
  chips: StarterChip[]
  onChip: (prompt: string) => void
}): JSX.Element {
  return (
    <div data-qid="shared-chat:empty" style={{ margin: 'auto', maxWidth: 560, textAlign: 'center', padding: '42px 12px' }}>
      <div style={{ display: 'inline-grid', placeItems: 'center', width: 46, height: 46, borderRadius: 18, background: 'rgba(0,255,136,0.1)', marginBottom: 14 }}>
        <Sparkles size={22} strokeWidth={1.7} aria-hidden="true" />
      </div>
      <h2 style={{ margin: 0, fontSize: 20, letterSpacing: '-0.02em' }}>{title}</h2>
      <p style={{ margin: '8px auto 0', color: '#9ba8b8', lineHeight: 1.5 }}>{description}</p>
      {chips.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginTop: 18 }}>
          {chips.map((chip) => (
            <button
              key={chip.label}
              type="button"
              data-qid={chip.dataQid ?? 'shared-chat:starter-chip'}
              onClick={() => onChip(chip.prompt)}
              style={{
                borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'rgba(255,255,255,0.05)',
                color: '#dce6f3',
                padding: '8px 11px',
                cursor: 'pointer',
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MessageBubble({ message }: { message: ChatMessage }): JSX.Element {
  const isUser = message.role === 'user'
  const branch = branchFromMessage(message)
  const steps = thinkingStepsForMessage(message)
  const disclosure = thinkingTraceDisclosureParts({ message, branch })
  const align = isUser ? 'flex-end' : 'flex-start'

  return (
    <article
      data-qid={`shared-chat:message:${message.role}`}
      data-branch={branch ?? message.role}
      style={{
        alignSelf: align,
        maxWidth: isUser ? '78%' : '88%',
        borderRadius: isUser ? '18px 18px 6px 18px' : '18px 18px 18px 6px',
        background: isUser ? 'rgba(0,255,136,0.14)' : 'rgba(255,255,255,0.055)',
        border: isUser ? '1px solid rgba(0,255,136,0.22)' : '1px solid rgba(255,255,255,0.08)',
        padding: '13px 14px',
        boxShadow: '0 12px 32px rgba(0,0,0,0.22)',
      }}
    >
      {!isUser && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#bcd0e7', fontSize: 12, fontWeight: 700, marginBottom: 7 }}>
          <Shield size={14} strokeWidth={1.7} aria-hidden="true" />
          <span>{message.title ?? 'Assistant'}</span>
        </div>
      )}
      <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, fontSize: 14 }}>{message.content}</div>
      {!isUser && steps.length > 0 && (
        <ThinkingTrace
          steps={steps}
          title={disclosure.title}
          label={disclosure.label}
          disclosureVariant={disclosure.disclosureVariant}
          leadingIcon={leadingIconForBranch(branch, disclosure.disclosureVariant)}
          placement="footer"
          displayMode="full"
          dataQid="shared-chat:message:thinking-trace"
        />
      )}
      {!isUser && <MessageFooter message={message} />}
    </article>
  )
}

export default ComplianceChatWell
