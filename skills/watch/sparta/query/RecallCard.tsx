import React from 'react'

export function RecallCard({
  items,
  resultCount,
}: {
  items: unknown[]
  resultCount: number
}): JSX.Element {
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.10)', borderRadius: 8, padding: 10, background: 'rgba(255,255,255,0.03)' }}>
      <div style={{ fontSize: 10, color: '#9aa8bc', fontWeight: 800, letterSpacing: '0.10em', textTransform: 'uppercase' }}>
        Recall Results {resultCount}
      </div>
      <pre style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', color: '#c7d2e1', fontSize: 11, lineHeight: 1.45 }}>
        {JSON.stringify(items.slice(0, 3), null, 2)}
      </pre>
    </div>
  )
}
