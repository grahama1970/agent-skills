import { Command, Edit3, Layout, Monitor, X } from 'lucide-react'
import { useEffect } from 'react'

// Keyboard shortcuts cheat sheet (user spec) — documents the REAL bindings.

const GROUPS = [
  {
    category: 'Panes & workspace',
    icon: Layout,
    items: [
      { keys: ['Ctrl', 'Z'], description: 'Undo last committed change (edit mode)' },
      { keys: ['Ctrl', '\\'], description: 'Toggle deck source pane' },
      { keys: ['Ctrl', 'B'], description: 'Toggle slide navigation drawer' },
      { keys: ['Ctrl', '⇧', 'I'], description: 'Toggle inspector pane' },
      { keys: ['Ctrl', '⇧', 'F'], description: 'Focus mode (collapse/restore all panes)' },
    ],
  },
  {
    category: 'Editing',
    icon: Edit3,
    items: [
      { keys: ['Ctrl', '⇧', 'N'], description: 'Toggle speaker notes drawer' },
      { keys: ['dbl-click'], description: 'Edit freeform element text' },
      { keys: ['?'], description: 'Toggle this cheat sheet' },
      { keys: ['Ctrl', '/'], description: 'Toggle this cheat sheet' },
    ],
  },
  {
    category: 'Presentation',
    icon: Monitor,
    items: [
      { keys: ['Ctrl', 'Enter'], description: 'Start presenter view' },
      { keys: ['→', 'Space'], description: 'Next slide' },
      { keys: ['←'], description: 'Previous slide' },
      { keys: ['Esc'], description: 'Exit presenter view / dismiss modal' },
    ],
  },
]

export function ShortcutsModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!isOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  if (!isOpen) return null
  return (
    <div
      role="dialog"
      aria-label="Keyboard shortcuts"
      data-qid="deck:shortcuts:backdrop"
      data-qs-action="DECK_SHORTCUTS_DISMISS"
      title="Dismiss shortcuts"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        data-qid="deck:shortcuts:panel"
        data-qs-action="DECK_SHORTCUTS_PANEL"
        title="Keyboard shortcuts"
        className="w-full max-w-2xl overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/50 px-6 py-4">
          <span className="flex items-center gap-2">
            <Command aria-hidden className="h-4 w-4 text-cyan-400" />
            <h2 className="m-0 font-mono text-xs font-bold uppercase tracking-wider text-slate-100">
              Keyboard shortcuts
            </h2>
          </span>
          <button
            type="button"
            data-qid="deck:shortcuts:close"
            data-qs-action="DECK_SHORTCUTS_CLOSE"
            title="Close (Esc)"
            onClick={onClose}
            className="cursor-pointer rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] space-y-6 overflow-y-auto p-6">
          {GROUPS.map((group) => (
            <section key={group.category} className="space-y-2">
              <h3 className="m-0 flex items-center gap-2 border-b border-slate-800/60 pb-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-slate-400">
                <group.icon aria-hidden className="h-4 w-4 text-cyan-400" />
                {group.category}
              </h3>
              {group.items.map((item) => (
                <div
                  key={item.description}
                  className="flex items-center justify-between rounded-lg border border-slate-800/60 bg-slate-950/50 px-3 py-2"
                >
                  <span className="text-xs font-medium text-slate-300">{item.description}</span>
                  <span className="flex items-center gap-1 font-mono text-xs">
                    {item.keys.map((key) => (
                      <kbd
                        key={key}
                        className="min-w-6 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-center text-[11px] font-semibold text-slate-200 shadow-sm"
                      >
                        {key}
                      </kbd>
                    ))}
                  </span>
                </div>
              ))}
            </section>
          ))}
        </div>
        <footer className="flex items-center justify-between border-t border-slate-800 bg-slate-950 px-6 py-3 font-mono text-[11px] text-slate-500">
          <span>
            Press <kbd className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-slate-300">?</kbd> or{' '}
            <kbd className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-slate-300">Ctrl /</kbd> to toggle
          </span>
          <span>Esc to dismiss</span>
        </footer>
      </div>
    </div>
  )
}
