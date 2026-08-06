import React, { useEffect, useState } from 'react'

type VoiceRecordingStateProps = {
  onAbort: () => void
  onTransmit: () => void
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  const remainingSeconds = (seconds % 60).toString().padStart(2, '0')
  return `00:${minutes}:${remainingSeconds}`
}

export default function VoiceRecordingState({
  onAbort,
  onTransmit,
}: VoiceRecordingStateProps): JSX.Element {
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => setDuration((current) => current + 1), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onAbort()
      }
      if (event.key === 'Enter') {
        event.preventDefault()
        onTransmit()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onAbort, onTransmit])

  return (
    <div
      data-qid="shared-chat:voice-recording-state"
      aria-label="Voice input listening"
      style={{
        padding: '12px 16px',
        backgroundColor: 'var(--surface-base)',
        borderTop: '1px solid #58a6ff',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            aria-hidden="true"
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: '#58a6ff',
              boxShadow: '0 0 8px rgba(88, 166, 255, 0.6)',
            }}
          />
          <span
            style={{
              color: '#58a6ff',
              fontFamily: '"SF Mono", Consolas, monospace',
              fontSize: 11,
              fontWeight: 800,
            }}
          >
            Listening...
          </span>
        </div>
        <span style={{ color: 'var(--text-muted)', fontFamily: '"SF Mono", Consolas, monospace', fontSize: 11 }}>
          {formatTime(duration)}
        </span>
      </div>

      <div
        aria-hidden="true"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          height: 24,
          padding: '0 4px',
        }}
      >
        {Array.from({ length: 8 }).map((_, index) => {
          const speed = 0.6 + (index % 3) * 0.2
          const delay = index * 0.1

          return (
            <span
              key={index}
              style={{
                flex: 1,
                backgroundColor: '#58a6ff',
                height: '40%',
                borderRadius: 12,
                animation: `freq-pulse ${speed}s ease-in-out infinite alternate`,
                animationDelay: `${delay}s`,
                opacity: 0.8,
              }}
            />
          )
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border-subtle)', paddingTop: 8 }}>
        <button
          type="button"
          data-qid="shared-chat:voice-recording-abort"
          data-qs-action="SHARED_CHAT_VOICE_ABORT"
          title="Cancel voice input with Escape"
          onClick={onAbort}
          className="voice-recording-state__control voice-recording-state__control--abort"
        >
          Cancel (Esc)
        </button>
        <button
          type="button"
          data-qid="shared-chat:voice-recording-transmit"
          data-qs-action="SHARED_CHAT_VOICE_TRANSMIT"
          title="Send voice input with Enter"
          onClick={onTransmit}
          className="voice-recording-state__control voice-recording-state__control--transmit"
        >
          Send (Enter)
        </button>
      </div>
    </div>
  )
}
