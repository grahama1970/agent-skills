import React, { useMemo } from 'react'

const PdfLabView = React.lazy(() =>
  import('./components/pdf-lab/PdfLabView').then((module) => ({ default: module.PdfLabView })),
)

function resolvePdfLabSubpath(): string | undefined {
  const hash = window.location.hash.replace(/^#/, '')
  const [route] = hash.split('?')
  if (!route || route === 'pdf-lab') return undefined
  if (!route.startsWith('pdf-lab/')) return undefined
  return route.slice('pdf-lab/'.length) || undefined
}

export default function App() {
  const params = useMemo(() => new URLSearchParams(window.location.hash.split('?')[1] || window.location.search), [])
  const initialSubpath = useMemo(() => resolvePdfLabSubpath(), [])

  return (
    <div className="pdf-lab-app-shell">
      <React.Suspense fallback={<div className="pdf-lab-loading">Loading PDF Lab...</div>}>
        <PdfLabView
          initialSubpath={initialSubpath}
          pdfUrl={params.get('pdf') || undefined}
          extractionUrl={params.get('extraction') || undefined}
        />
      </React.Suspense>
    </div>
  )
}
