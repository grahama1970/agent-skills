/**
 * Gemini-style ghost action row — feedback, copy, optional workspace / regenerate.
 */
import { useCallback, useState } from 'react'
import { Copy, MoreHorizontal, RotateCw, ThumbsDown, ThumbsUp } from 'lucide-react'
import ActionTooltip from './ActionTooltip'

export interface MessageActionRowProps {
  messageId: string
  copyText?: string
  feedback?: 'up' | 'down'
  onFeedback?: (feedback: 'up' | 'down') => void
  onRegenerate?: () => void
  onOpenWorkspace?: () => void
}

export function MessageActionRow({
  messageId,
  copyText,
  feedback,
  onFeedback,
  onRegenerate,
  onOpenWorkspace,
}: MessageActionRowProps) {
  const [copied, setCopied] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const handleCopy = useCallback(async () => {
    if (!copyText?.trim()) return
    try {
      await navigator.clipboard.writeText(copyText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }, [copyText])

  const showRow = Boolean(onFeedback || copyText?.trim() || onRegenerate || onOpenWorkspace)
  if (!showRow) return null

  return (
    <div className="chat-turn-actions" data-qid={`chat:turn-actions:${messageId}`} role="group" aria-label="Message actions">
      {onFeedback ? (
        <>
          <ActionTooltip content="Helpful response">
            <button
              type="button"
              className={`chat-turn-actions__btn${feedback === 'up' ? ' chat-turn-actions__btn--active' : ''}`}
              data-qid={`chat:feedback-up:${messageId}`}
              data-qs-action="FEEDBACK_HELPFUL"
              aria-label="Helpful response"
              aria-pressed={feedback === 'up'}
              onClick={() => onFeedback('up')}
            >
              <ThumbsUp size={16} aria-hidden />
            </button>
          </ActionTooltip>
          <ActionTooltip content="Not helpful">
            <button
              type="button"
              className={`chat-turn-actions__btn${feedback === 'down' ? ' chat-turn-actions__btn--active' : ''}`}
              data-qid={`chat:feedback-down:${messageId}`}
              data-qs-action="FEEDBACK_NOT_HELPFUL"
              aria-label="Not helpful"
              aria-pressed={feedback === 'down'}
              onClick={() => onFeedback('down')}
            >
              <ThumbsDown size={16} aria-hidden />
            </button>
          </ActionTooltip>
        </>
      ) : null}

      {onRegenerate ? (
        <ActionTooltip content="Regenerate response">
          <button
            type="button"
            className="chat-turn-actions__btn"
            data-qid={`chat:regenerate:${messageId}`}
            data-qs-action="REGENERATE_RESPONSE"
            aria-label="Regenerate response"
            onClick={onRegenerate}
          >
            <RotateCw size={16} aria-hidden />
          </button>
        </ActionTooltip>
      ) : null}

      {copyText?.trim() ? (
        <ActionTooltip content={copied ? 'Copied' : 'Copy response'}>
          <button
            type="button"
            className={`chat-turn-actions__btn${copied ? ' chat-turn-actions__btn--active' : ''}`}
            data-qid={`chat:copy:${messageId}`}
            data-qs-action="COPY_RESPONSE"
            aria-label={copied ? 'Copied' : 'Copy response'}
            onClick={() => void handleCopy()}
          >
            <Copy size={16} aria-hidden />
          </button>
        </ActionTooltip>
      ) : null}

      {onOpenWorkspace ? (
        <div className="chat-turn-actions__more">
          <ActionTooltip content="More actions">
            <button
              type="button"
              className="chat-turn-actions__btn"
              data-qid={`chat:more:${messageId}`}
              data-qs-action="MESSAGE_MORE"
              aria-label="More actions"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(v => !v)}
            >
              <MoreHorizontal size={16} aria-hidden />
            </button>
          </ActionTooltip>
          {menuOpen ? (
            <div className="chat-turn-actions__menu" role="menu">
              <button
                type="button"
                role="menuitem"
                className="chat-turn-actions__menu-item"
                data-qid={`chat:open-workspace:${messageId}`}
                data-qs-action="OPEN_EVIDENCE_WORKSPACE"
                onClick={() => {
                  setMenuOpen(false)
                  onOpenWorkspace()
                }}
              >
                Open evidence workspace
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
