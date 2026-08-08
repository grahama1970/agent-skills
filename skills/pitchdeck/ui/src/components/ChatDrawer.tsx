import { useRef } from 'react'
import { X } from 'lucide-react'
import { useRegisterAction } from '../hooks'
// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'

// Right side sheet (3-pane spec): auxiliary tools — Chat and Notes — anchor
// exclusively to the right as tabs of ONE drawer, pushing the canvas without
// invading it. The sheet stays MOUNTED while collapsed (width animates to 0),
// so the chat transcript, composer draft, and notes edits survive
// collapse/expand. Exits run faster than entrances (200ms vs 250ms,
// ease-out cubic-bezier(0.16, 1, 0.3, 1)); the inner pane keeps its fixed
// width during the animation so content never reflows mid-slide. Esc
// collapses while focus is anywhere inside the sheet — dismissal never
// requires a trip back to the navbar.

const DRAWER_WIDTH = 380
const EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'

export type RightSheetTab = 'chat' | 'notes' | 'layout'

export function RightSheet({
  collapsed,
  tab,
  onTab,
  onCollapse,
  chat,
  notes,
  layout,
}: {
  collapsed: boolean
  tab: RightSheetTab
  onTab: (tab: RightSheetTab) => void
  onCollapse: () => void
  chat: React.ReactNode
  notes: React.ReactNode
  /** Design-mode layout inspector; when absent the Layout tab is hidden. */
  layout?: React.ReactNode
}) {
  useRegisterAction('deck:chat:collapse', {
    app: 'pitchdeck',
    action: 'DECK_CHAT_COLLAPSE',
    label: 'Collapse right sheet',
    description: 'Collapse the right auxiliary sheet (chat/notes) from its own header',
  })
  const ref = useRef<HTMLElement | null>(null)

  const TAB_META: Record<RightSheetTab, { label: string; action: string; title: string }> = {
    chat: { label: 'Chat', action: 'DECK_SHEET_TAB_CHAT', title: 'Chat — propose edits conversationally' },
    notes: { label: 'Notes', action: 'DECK_SHEET_TAB_NOTES', title: 'Speaker notes for the current slide' },
    layout: { label: 'Layout', action: 'DECK_SHEET_TAB_LAYOUT', title: 'Layout inspector for the current slide' },
  }
  const tabButton = (id: RightSheetTab) => (
    <Button
      key={id}
      type="button"
      data-qid={`deck:sheet:tab:${id}`}
      data-qs-action={TAB_META[id].action}
      title={TAB_META[id].title}
      aria-pressed={tab === id}
      onClick={() => onTab(id)}
      className={`flex-1 cursor-pointer border-b-2 py-2.5 text-center text-xs font-medium transition ${
        tab === id
          ? 'border-cyan-500 bg-slate-900 font-semibold text-cyan-300'
          : 'border-transparent text-slate-400 hover:text-slate-200'
      }`}
    >
      {TAB_META[id].label}
    </Button>
  )

  return (
    <aside
      ref={ref}
      aria-label="Auxiliary tools"
      aria-hidden={collapsed}
      data-qid="deck:pane:chat"
      className="min-h-0 shrink-0 overflow-hidden border-l border-slate-800"
      style={{
        width: collapsed ? 0 : DRAWER_WIDTH,
        transition: `width ${collapsed ? 200 : 250}ms ${EASE}`,
        borderLeftWidth: collapsed ? 0 : 1,
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !collapsed) {
          event.stopPropagation()
          onCollapse()
        }
      }}
    >
      <div className="flex h-full flex-col" style={{ width: DRAWER_WIDTH }}>
        <div className="flex h-11 shrink-0 items-center border-b border-slate-800 bg-slate-950/60">
          {(['chat', 'notes', ...(layout ? (['layout'] as RightSheetTab[]) : [])] as RightSheetTab[]).map(tabButton)}
          <Button
            type="button"
            data-qid="deck:chat:collapse"
            data-qs-action="DECK_CHAT_COLLAPSE"
            aria-label="Collapse panel"
            title="Collapse this panel (Esc)"
            onClick={onCollapse}
            className="mx-1.5 cursor-pointer rounded-md p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X aria-hidden className="h-4 w-4" />
          </Button>
        </div>
        {/* All panes stay mounted; hidden ones keep their state. */}
        <div className={`min-h-0 flex-1 ${tab === 'chat' ? '' : 'hidden'}`}>{chat}</div>
        <div className={`min-h-0 flex-1 ${tab === 'notes' ? '' : 'hidden'}`}>{notes}</div>
        {layout ? <div className={`hover-scrollbar min-h-0 flex-1 overflow-y-auto ${tab === 'layout' ? '' : 'hidden'}`}>{layout}</div> : null}
      </div>
    </aside>
  )
}
