import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import { EMBRY } from './EmbryStyle'

type ReviewBundleStatus = 'idle' | 'generating' | 'copied' | 'error'

interface ReviewBundleButtonProps {
  app: string
  endpoint: string
  actionId: string
  action: string
  label?: string
  generatingLabel?: string
  copiedLabel?: string
  errorLabel?: string
  title: string
  description: string
  className?: string
  style?: CSSProperties
  disabled?: boolean
  requestBody?: Record<string, unknown>
  onComplete?: (result: unknown) => void
  onError?: (error: Error) => void
}

const STYLE_ID = 'review-bundle-button-style'

function getResultMessage(result: unknown): string {
  if (!result || typeof result !== 'object') return 'Copied to clipboard'
  const payload = result as Record<string, unknown>
  const path = typeof payload.path === 'string' ? payload.path : typeof payload.latestPath === 'string' ? payload.latestPath : null
  const bytes = typeof payload.bytes === 'number' ? `${Math.round(payload.bytes / 1024)} KB` : null
  if (path && bytes) return `Copied ${bytes} · ${path}`
  if (path) return `Copied · ${path}`
  return 'Copied to clipboard'
}

export function ReviewBundleButton({
  app,
  endpoint,
  actionId,
  action,
  label = 'Review Bundle',
  generatingLabel = 'Generating…',
  copiedLabel = 'Copied',
  errorLabel = 'Bundle failed',
  title,
  description,
  className,
  style,
  disabled,
  requestBody,
  onComplete,
  onError,
}: ReviewBundleButtonProps) {
  const [status, setStatus] = useState<ReviewBundleStatus>('idle')
  const [message, setMessage] = useState('')
  const resetTimerRef = useRef<number | null>(null)

  useRegisterAction(actionId, {
    app,
    action,
    label,
    description,
  })

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current)
    }
  }, [])

  const buttonLabel = useMemo(() => {
    if (status === 'generating') return generatingLabel
    if (status === 'copied') return copiedLabel
    if (status === 'error') return errorLabel
    return label
  }, [copiedLabel, errorLabel, generatingLabel, label, status])

  const generateBundle = useCallback(async () => {
    if (status === 'generating' || disabled) return
    if (resetTimerRef.current !== null) window.clearTimeout(resetTimerRef.current)
    setStatus('generating')
    setMessage('Collecting code, context, screenshots, and rationale…')

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody ?? {}),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = result && typeof result === 'object' && 'detail' in result ? String((result as Record<string, unknown>).detail) : ''
        const error = result && typeof result === 'object' && 'error' in result ? String((result as Record<string, unknown>).error) : `HTTP ${response.status}`
        throw new Error(detail ? `${error}: ${detail}` : error)
      }

      setStatus('copied')
      setMessage(getResultMessage(result))
      onComplete?.(result)
      resetTimerRef.current = window.setTimeout(() => {
        setStatus('idle')
        setMessage('')
      }, 4200)
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error))
      setStatus('error')
      setMessage(err.message)
      onError?.(err)
    }
  }, [disabled, endpoint, onComplete, onError, requestBody, status])

  return (
    <span className="review-bundle-shell">
      <style id={STYLE_ID}>{`
        @keyframes review-bundle-spin {
          to { transform: rotate(360deg); }
        }
        @keyframes review-bundle-pulse {
          0%, 100% { box-shadow: 0 0 0 rgba(124, 58, 237, 0); border-color: rgba(124, 58, 237, 0.45); }
          50% { box-shadow: 0 0 18px rgba(124, 58, 237, 0.35); border-color: rgba(124, 58, 237, 0.95); }
        }
        .review-bundle-button[data-status="generating"] {
          animation: review-bundle-pulse 900ms cubic-bezier(0.22, 1, 0.36, 1) infinite;
        }
        .review-bundle-spinner {
          width: 12px;
          height: 12px;
          border-radius: 999px;
          border: 2px solid rgba(255,255,255,0.2);
          border-top-color: ${EMBRY.accent};
          animation: review-bundle-spin 750ms linear infinite;
        }
      `}</style>
      <button
        className={['review-bundle-button', className].filter(Boolean).join(' ')}
        data-qid={actionId}
        data-qs-action={action}
        data-status={status}
        title={title}
        disabled={disabled || status === 'generating'}
        onClick={generateBundle}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          minHeight: 36,
          padding: '0 14px',
          borderRadius: 12,
          border: `1px solid ${status === 'error' ? `${EMBRY.red}66` : status === 'copied' ? `${EMBRY.green}66` : `${EMBRY.accent}55`}`,
          background: status === 'copied' ? 'rgba(16, 185, 129, 0.12)' : status === 'error' ? 'rgba(239, 68, 68, 0.12)' : 'rgba(124, 58, 237, 0.1)',
          color: status === 'copied' ? EMBRY.green : status === 'error' ? EMBRY.red : EMBRY.white,
          fontSize: 12,
          fontWeight: 800,
          cursor: disabled || status === 'generating' ? 'wait' : 'pointer',
          opacity: disabled ? 0.55 : 1,
          transition: 'border-color 160ms ease, background-color 160ms ease, transform 100ms ease',
          ...style,
        }}
      >
        {status === 'generating' && <span className="review-bundle-spinner" aria-hidden="true" />}
        <span>{buttonLabel}</span>
      </button>
      {message && (
        <span
          aria-live="polite"
          style={{
            display: 'inline-block',
            maxWidth: 280,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: status === 'error' ? EMBRY.red : status === 'copied' ? EMBRY.green : EMBRY.muted,
            fontSize: 11,
            marginLeft: 8,
            verticalAlign: 'middle',
          }}
          title={message}
        >
          {message}
        </span>
      )}
    </span>
  )
}
