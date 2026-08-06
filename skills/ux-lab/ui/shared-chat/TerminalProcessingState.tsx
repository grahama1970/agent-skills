import React, { useEffect, useMemo, useState } from 'react'

export default function TerminalProcessingState(): JSX.Element {
  const statuses = useMemo(() => [
    'PARSING_COMMAND_SYNTAX',
    'QUERYING_EVIDENCE_GRAPH',
    'COMPILING_TELEMETRY',
    'AWAITING_DAEMON_RESPONSE',
  ], [])
  const [statusIndex, setStatusIndex] = useState(0)

  useEffect(() => {
    const interval = window.setInterval(() => {
      setStatusIndex((current) => (current + 1) % statuses.length)
    }, 800)
    return () => window.clearInterval(interval)
  }, [statuses.length])

  return (
    <div
      data-qid="shared-chat:terminal-processing"
      aria-label="Console daemon processing"
      style={{
        display: 'flex',
        flexDirection: 'column',
        padding: '8px 16px',
        borderLeft: '2px solid #e3b341',
        backgroundColor: 'rgba(227, 179, 65, 0.05)',
        borderBottom: '1px solid var(--surface-raised)',
        gap: 4,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <span
          style={{
            color: '#e3b341',
            fontSize: 9,
            fontFamily: '"SF Mono", Consolas, monospace',
            fontWeight: 800,
            letterSpacing: 1,
          }}
        >
          DAEMON.EMBRY // PROCESSING
        </span>
        <span style={{ color: '#484f58', fontSize: 9, fontFamily: '"SF Mono", Consolas, monospace' }}>
          T-MINUS
        </span>
      </div>

      <div
        style={{
          color: 'var(--text-muted)',
          fontSize: 12,
          lineHeight: 1.5,
          fontFamily: '"SF Mono", Consolas, monospace',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 4,
        }}
      >
        <span>{`[${statuses[statusIndex]}]`}</span>
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 14,
            backgroundColor: '#e3b341',
            animation: 'terminal-blink 1s steps(1) infinite',
          }}
        />
      </div>
    </div>
  )
}
