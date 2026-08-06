import React, { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { AlertTriangle, ThumbsDown, X } from 'lucide-react'
import { useRegisterAction } from './_support/useRegisterAction'

export interface FeedbackDetailPayload {
  messageId: string
  tags: string[]
  comments: string
  timestamp: string
}

interface FeedbackModalProps {
  messageId: string
  onClose: () => void
  onSubmit: (payload: FeedbackDetailPayload) => void | Promise<void>
}

const feedbackTags = [
  'Inaccurate / Hallucination',
  'Outdated Information',
  'Poor Formatting',
  'Incomplete Answer',
  'Not Actionable',
]

const tokenFor = (value: string): string => {
  const token = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return token || 'feedback'
}

const iconButtonStyle: CSSProperties = {
  border: 0,
  background: 'transparent',
  color: '#64748b',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 32,
  height: 32,
  borderRadius: 8,
}

export function FeedbackModal({ messageId, onClose, onSubmit }: FeedbackModalProps): JSX.Element {
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [comments, setComments] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const canSubmit = selectedTags.length > 0 || comments.trim().length > 0
  const modalTitleId = useMemo(() => `feedback-title-${tokenFor(messageId)}`, [messageId])

  const closeQid = `shared-chat:feedback-modal:${tokenFor(messageId)}:close`
  const submitQid = `shared-chat:feedback-modal:${tokenFor(messageId)}:submit`
  useRegisterAction(closeQid, {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_FEEDBACK_MODAL_CLOSE',
    label: 'Close feedback modal',
    description: 'Close the Console response feedback dialog without submitting telemetry',
    tags: ['shared-chat', 'console-feedback'],
  })
  useRegisterAction(submitQid, {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_FEEDBACK_MODAL_SUBMIT',
    label: 'Submit feedback report',
    description: 'Submit structured negative response feedback for the selected Console message',
    tags: ['shared-chat', 'console-feedback'],
  })

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag])
  }

  const submit = async () => {
    if (!canSubmit || isSubmitting) return
    setIsSubmitting(true)
    try {
      await onSubmit({
        messageId,
        tags: selectedTags,
        comments: comments.trim(),
        timestamp: new Date().toISOString(),
      })
      onClose()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div
      data-qid="shared-chat:feedback-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby={modalTitleId}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        background: 'rgba(0, 0, 0, 0.64)',
        backdropFilter: 'blur(6px)',
      }}
    >
      <button
        type="button"
        data-qid="shared-chat:feedback-modal:backdrop"
        data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_CLOSE"
        title="Close feedback dialog"
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          border: 0,
          background: 'transparent',
          cursor: 'default',
        }}
      />
      <div
        style={{
          position: 'relative',
          width: 'min(100%, 520px)',
          overflow: 'hidden',
          borderRadius: 12,
          border: '1px solid rgba(148, 163, 184, 0.18)',
          background: '#0f172a',
          boxShadow: '0 24px 80px rgba(0, 0, 0, 0.46)',
          color: '#e2e8f0',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '14px 18px',
            borderBottom: '1px solid rgba(148, 163, 184, 0.12)',
            background: 'rgba(15, 23, 42, 0.88)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <ThumbsDown size={18} color="#f87171" aria-hidden="true" />
            <h2 id={modalTitleId} style={{ margin: 0, fontSize: 14, fontWeight: 760, color: '#f8fafc' }}>
              Submit Feedback
            </h2>
          </div>
          <button
            type="button"
            data-qid={closeQid}
            data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_CLOSE"
            onClick={onClose}
            title="Close feedback dialog"
            style={iconButtonStyle}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div style={{ padding: 18 }}>
          <p style={{ margin: '0 0 14px', color: '#94a3b8', fontSize: 13, lineHeight: 1.5 }}>
            Help improve the Sparta Console. What went wrong with this response?
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
            {feedbackTags.map((tag) => {
              const selected = selectedTags.includes(tag)
              return (
                <button
                  key={tag}
                  type="button"
                  data-qid={`shared-chat:feedback-modal:tag:${tokenFor(tag)}`}
                  data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_TOGGLE_TAG"
                  title={`Toggle feedback reason: ${tag}`}
                  aria-pressed={selected}
                  onClick={() => toggleTag(tag)}
                  style={{
                    border: selected ? '1px solid rgba(248, 113, 113, 0.58)' : '1px solid rgba(148, 163, 184, 0.18)',
                    background: selected ? 'rgba(127, 29, 29, 0.34)' : 'rgba(30, 41, 59, 0.74)',
                    color: selected ? '#fecaca' : '#cbd5e1',
                    borderRadius: 999,
                    padding: '7px 10px',
                    fontSize: 12,
                    fontWeight: 650,
                    cursor: 'pointer',
                  }}
                >
                  {tag}
                </button>
              )
            })}
          </div>

          <textarea
            data-qid="shared-chat:feedback-modal:comments"
            data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_EDIT_COMMENTS"
            title="Optional feedback details"
            value={comments}
            onChange={(event) => setComments(event.currentTarget.value)}
            placeholder="Additional details (optional)..."
            style={{
              width: '100%',
              minHeight: 96,
              resize: 'vertical',
              boxSizing: 'border-box',
              borderRadius: 10,
              border: '1px solid rgba(148, 163, 184, 0.18)',
              background: 'rgba(15, 23, 42, 0.78)',
              color: '#e2e8f0',
              outline: 'none',
              padding: 12,
              fontSize: 13,
              lineHeight: 1.5,
              fontFamily: '"Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            }}
          />
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            padding: '14px 18px',
            borderTop: '1px solid rgba(148, 163, 184, 0.12)',
            background: 'rgba(15, 23, 42, 0.7)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, color: '#64748b', fontSize: 12 }}>
            <AlertTriangle size={14} aria-hidden="true" />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              Stored with the selected Console response.
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              type="button"
              data-qid={closeQid}
              data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_CLOSE"
              onClick={onClose}
              title="Cancel feedback"
              style={{
                border: 0,
                background: 'transparent',
                color: '#94a3b8',
                cursor: 'pointer',
                padding: '8px 10px',
                fontSize: 13,
                fontWeight: 650,
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              data-qid={submitQid}
              data-qs-action="SHARED_CHAT_FEEDBACK_MODAL_SUBMIT"
              disabled={!canSubmit || isSubmitting}
              onClick={submit}
              title={canSubmit ? 'Submit feedback report' : 'Select a reason or enter details before submitting'}
              style={{
                border: 0,
                borderRadius: 8,
                background: canSubmit ? '#dc2626' : 'rgba(100, 116, 139, 0.34)',
                color: '#fff',
                cursor: canSubmit && !isSubmitting ? 'pointer' : 'not-allowed',
                padding: '8px 12px',
                fontSize: 13,
                fontWeight: 760,
                opacity: isSubmitting ? 0.72 : 1,
                boxShadow: canSubmit ? '0 10px 28px rgba(127, 29, 29, 0.3)' : 'none',
              }}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Report'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default FeedbackModal
