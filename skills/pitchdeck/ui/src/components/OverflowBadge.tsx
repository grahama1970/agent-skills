import { TriangleAlert } from 'lucide-react'
import type { LintWarning } from '../lib/pptxLint'

// Phase 4 (Gemini spec): canvas overlay for advisory export-bounds warnings.

export function OverflowBadge({ warnings }: { warnings: LintWarning[] }) {
  if (warnings.length === 0) return null
  return (
    <aside
      aria-label="PPTX export bounds warnings"
      className="absolute right-4 top-4 z-30 max-w-xs space-y-1 rounded-lg border border-amber-500/50 bg-amber-950/90 px-3 py-2 text-xs text-amber-200 shadow-lg backdrop-blur-md"
    >
      <p className="m-0 flex items-center gap-1.5 font-bold text-amber-400">
        <TriangleAlert aria-hidden className="h-4 w-4" />
        PPTX export bounds
      </p>
      <ul className="m-0 list-disc space-y-0.5 pl-4 text-[11px] text-amber-300/90">
        {warnings.map((warning) => (
          <li key={`${warning.elementId}-${warning.type}`}>{warning.message}</li>
        ))}
      </ul>
    </aside>
  )
}
