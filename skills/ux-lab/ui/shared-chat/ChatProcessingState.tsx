import React, { useEffect, useMemo, useState } from 'react'

export default function ChatProcessingState(): JSX.Element {
  const statuses = useMemo(() => [
    'Reading execution context...',
    'Querying evidence graph...',
    'Compiling telemetry...',
    'Drafting response...',
  ], [])
  const [statusIndex, setStatusIndex] = useState(0)

  useEffect(() => {
    const interval = window.setInterval(() => {
      setStatusIndex((current) => (current + 1) % statuses.length)
    }, 1200)
    return () => window.clearInterval(interval)
  }, [statuses.length])

  return (
    <div
      data-qid="shared-chat:chat-processing"
      aria-label="Embry Console response in progress"
      style={{
        display: 'flex',
        flexDirection: 'column',
        padding: '14px 16px',
        borderLeft: '3px solid #58a6ff',
        backgroundColor: 'rgba(88, 166, 255, 0.03)',
        borderBottom: '1px solid var(--border-subtle)',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <span
          style={{
            color: '#58a6ff',
            fontSize: 11,
            fontFamily: '"SF Mono", Consolas, monospace',
            fontWeight: 800,
            letterSpacing: 0.5,
          }}
        >
          Embry
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: 10, fontFamily: '"SF Mono", Consolas, monospace' }}>
          Working
        </span>
      </div>

      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 13,
          lineHeight: 1.6,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginTop: 2,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: '#58a6ff',
            boxShadow: '0 0 8px rgba(88, 166, 255, 0.4)',
            animation: 'ide-pulse 0.8s ease-in-out infinite alternate',
          }}
        />
        <span key={statusIndex} style={{ animation: 'text-fade-in 0.3s ease-out forwards' }}>
          {statuses[statusIndex]}
        </span>
      </div>
    </div>
  )
}
