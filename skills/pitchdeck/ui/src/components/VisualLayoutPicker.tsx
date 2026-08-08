// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'
// Phase 3 (Gemini spec): wireframe layout gallery replacing the text dropdown.
// One thumbnail per real SlideLayout value in the manifest schema.

const Bar = ({ className }: { className: string }) => <div className={`rounded ${className}`} />

const WIREFRAMES: Record<string, React.ReactNode> = {
  cover: (
    <div className="flex h-12 w-full flex-col items-start justify-center gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-2 w-3/4 bg-cyan-500/80" />
      <Bar className="h-1 w-1/2 bg-slate-600" />
    </div>
  ),
  statement: (
    <div className="flex h-12 w-full flex-col items-center justify-center gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-1.5 w-2/3 bg-slate-300" />
      <Bar className="h-1 w-1/2 bg-cyan-500/60" />
    </div>
  ),
  split: (
    <div className="flex h-12 w-full gap-1 rounded bg-slate-950 p-1.5">
      <div className="flex w-1/2 flex-col gap-1 p-0.5">
        <Bar className="h-1.5 w-full bg-slate-400" />
        <Bar className="h-1 w-3/4 bg-slate-600" />
        <Bar className="h-1 w-2/3 bg-slate-600" />
      </div>
      <div className="w-1/2 rounded border border-cyan-500/40 bg-cyan-500/15" />
    </div>
  ),
  screenshot: (
    <div className="flex h-12 w-full flex-col gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-1 w-1/2 bg-slate-400" />
      <div className="flex-1 rounded border border-cyan-500/40 bg-cyan-500/15" />
    </div>
  ),
  flow: (
    <div className="flex h-12 w-full items-center justify-center gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-4 w-1/4 border border-cyan-500/40 bg-cyan-500/10" />
      <span className="text-[8px] text-cyan-400">→</span>
      <Bar className="h-4 w-1/4 border border-cyan-500/40 bg-cyan-500/10" />
      <span className="text-[8px] text-cyan-400">→</span>
      <Bar className="h-4 w-1/4 border border-cyan-500/40 bg-cyan-500/10" />
    </div>
  ),
  three_cards: (
    <div className="flex h-12 w-full items-center gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-8 w-1/3 border border-slate-700 bg-slate-800" />
      <Bar className="h-8 w-1/3 border border-slate-700 bg-slate-800" />
      <Bar className="h-8 w-1/3 border border-slate-700 bg-slate-800" />
    </div>
  ),
  proof_cards: (
    <div className="flex h-12 w-full flex-col justify-between gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-1.5 w-1/2 bg-emerald-500/80" />
      <div className="flex h-5 gap-1">
        <Bar className="h-full w-1/2 border border-emerald-500/30 bg-emerald-950/40" />
        <Bar className="h-full w-1/2 border border-emerald-500/30 bg-emerald-950/40" />
      </div>
    </div>
  ),
  roadmap: (
    <div className="flex h-12 w-full flex-col justify-center gap-1 rounded bg-slate-950 p-1.5">
      <div className="flex items-center gap-1">
        <Bar className="h-2 w-2 rounded-full bg-cyan-400" />
        <Bar className="h-1 flex-1 bg-slate-700" />
        <Bar className="h-2 w-2 rounded-full bg-slate-600" />
        <Bar className="h-1 flex-1 bg-slate-700" />
        <Bar className="h-2 w-2 rounded-full bg-slate-600" />
      </div>
      <Bar className="h-1 w-2/3 bg-slate-600" />
    </div>
  ),
  collaboration: (
    <div className="flex h-12 w-full items-center justify-center gap-2 rounded bg-slate-950 p-1.5">
      <Bar className="h-6 w-6 rounded-full border border-cyan-500/40 bg-cyan-500/10" />
      <Bar className="h-1 w-4 bg-slate-600" />
      <Bar className="h-6 w-6 rounded-full border border-slate-600 bg-slate-800" />
    </div>
  ),
  appendix: (
    <div className="flex h-12 w-full flex-col gap-1 rounded bg-slate-950 p-1.5">
      <Bar className="h-1 w-1/3 bg-slate-400" />
      <Bar className="h-1 w-full bg-slate-700" />
      <Bar className="h-1 w-full bg-slate-700" />
      <Bar className="h-1 w-3/4 bg-slate-700" />
    </div>
  ),
  freeform: (
    <div className="relative h-12 w-full rounded bg-slate-950 p-1.5">
      <Bar className="absolute left-2 top-1.5 h-1.5 w-1/3 bg-slate-300" />
      <Bar className="absolute bottom-2 left-5 h-1 w-1/4 bg-slate-600" />
      <div className="absolute right-2 top-3 h-6 w-1/3 rounded border border-dashed border-cyan-500/60 bg-cyan-500/10" />
    </div>
  ),
}

export function VisualLayoutPicker({
  currentLayout,
  disabled,
  onSelectLayout,
}: {
  currentLayout: string
  disabled: boolean
  onSelectLayout: (layoutId: string) => void
}) {
  return (
    <div>
      <span className="block text-xs font-medium text-slate-400">Layout</span>
      <div className="mt-1 grid grid-cols-2 gap-2">
        {Object.entries(WIREFRAMES).map(([id, wireframe]) => (
          <Button
            key={id}
            type="button"
            data-qid={`deck:inspector:layout:${id}`}
            data-qs-action="DECK_INSPECTOR_SET_LAYOUT"
            title={`Switch slide layout to ${id.replace('_', ' ')}`}
            aria-pressed={currentLayout === id}
            disabled={disabled}
            onClick={() => onSelectLayout(id)}
            className={`cursor-pointer rounded-lg border p-1.5 text-left transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
              currentLayout === id
                ? 'border-cyan-500 bg-cyan-500/10'
                : 'border-slate-800 bg-slate-900/50 hover:border-slate-600'
            }`}
          >
            {wireframe}
            <span className={`mt-1 block text-center text-[11px] font-medium ${currentLayout === id ? 'text-cyan-200' : 'text-slate-400'}`}>
              {id.replace('_', ' ')}
            </span>
          </Button>
        ))}
      </div>
    </div>
  )
}
