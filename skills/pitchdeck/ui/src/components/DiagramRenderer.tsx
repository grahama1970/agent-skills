import { useEffect, useRef, useState } from 'react'
import katex from 'katex'
import mermaid from 'mermaid'
import 'katex/dist/katex.min.css'

// Mermaid/KaTeX renderers for manifest-typed visual kinds. Security posture:
// mermaid runs with securityLevel 'strict' ONLY — 'loose' executes embedded
// click/script directives and is an XSS channel into the exported HTML
// bundle. KaTeX renders with throwOnError:false so a bad formula degrades to
// visible source instead of a blank slide. Source text is validated by the
// compiler's visible-text scan before it ever reaches this component.

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'dark',
  fontFamily: 'var(--deck-body-font, Arial)',
})

let renderCounter = 0

export function MermaidDiagram({ source }: { source: string }) {
  const [svg, setSvg] = useState<string | null>(null)
  const [renderError, setRenderError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    renderCounter += 1
    mermaid
      .render(`deck-mermaid-${renderCounter}`, source)
      .then((result) => {
        if (!cancelled) setSvg(result.svg)
      })
      .catch((error: Error) => {
        if (!cancelled) setRenderError(error.message)
      })
    return () => {
      cancelled = true
    }
  }, [source])

  if (renderError) {
    return (
      <div role="alert" className="flex h-full w-full flex-col items-center justify-center gap-3 rounded-2xl border border-amber-500/60 bg-amber-500/5 p-8 text-amber-300">
        <p className="m-0 text-2xl font-semibold">Diagram failed to render</p>
        <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap text-sm text-amber-200/80">{renderError}</pre>
      </div>
    )
  }
  if (!svg) return <div className="flex h-full w-full items-center justify-center text-2xl text-slate-500">Rendering diagram…</div>
  return (
    <div
      data-qid="deck:visual:mermaid"
      className="flex h-full w-full items-center justify-center [&_svg]:max-h-full [&_svg]:max-w-full"
      // Safe: mermaid strict-mode output (sanitized by mermaid) — never raw manifest text.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

export function MathBlock({ source }: { source: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) {
      katex.render(source, ref.current, { displayMode: true, throwOnError: false })
    }
  }, [source])
  return (
    <div
      ref={ref}
      data-qid="deck:visual:math"
      className="flex h-full w-full items-center justify-center text-5xl text-slate-100"
    />
  )
}
