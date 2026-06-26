import React from 'react'

const WatchReportView = React.lazy(() =>
  import('../components/WatchReportView').then(m => ({ default: m.WatchReportView }))
)

export default function App() {
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <React.Suspense fallback={
        <div style={{ padding: 24, color: '#6b7a8f' }}>Loading Watch report...</div>
      }>
        <WatchReportView
          reportPath={new URLSearchParams(window.location.search).get('report') || undefined}
          answerModel={new URLSearchParams(window.location.search).get('model') || undefined}
        />
      </React.Suspense>
    </div>
  )
}
