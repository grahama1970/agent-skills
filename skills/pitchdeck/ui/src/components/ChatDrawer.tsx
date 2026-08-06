import { useRef } from 'react'
import { MessageSquare, StickyNote, X } from 'lucide-react'
import { useRegisterAction } from '../hooks'

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

export type RightSheetTab = 'chat' | 'notes'

export function RightSheet({
  collapsed,
  tab,
  onTab,
  onCollapse,
  chat,
  notes,
}: {
  collapsed: boolean
  tab: RightSheetTab
  onTab: (tab: RightSheetTab) => void
  onCollapse: () => void
  chat: React.ReactNode
  notes: React.ReactNode
}) {
  useRegisterAction('deck:chat:collapse', {
    app: 'pitchdeck',
    action: 'DECK_CHAT_COLLAPSE',
    label: 'Collapse right sheet',
    description: 'Collapse the right auxiliary sheet (chat/notes) from its own header',
  })
  const ref = useRef<HTMLElement | null>(null)

  const tabButton = (id: RightSheetTab, label: string, icon: React.ReactNode, badge?: string) => (
    <button
      type="button"
      data-qid={`deck:sheet:tab:${id}`}
      data-qs-action={id === 'chat' ? 'DECK_SHEET_TAB_CHAT' : 'DECK_SHEET_TAB_NOTES'}
      title={id === 'chat' ? 'Chat — propose edits conversationally' : 'Speaker notes for the current slide'}
      aria-pressed={tab === id}
      onClick={() => onTab(id)}
      className={`flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm transition ${
        tab === id ? 'bg-slate-800 font-semibold text-slate-100' : 'text-slate-400 hover:text-slate-200'
      }`}
    >
      {icon} {label}
      {badge && tab === id ? (
        <span className="rounded bg-slate-700/80 px-1.5 py-0.5 text-[10px] font-normal text-slate-400">{badge}</span>
      ) : null}
    </button>
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
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-slate-800 px-2">
          <div className="flex items-center gap-1">
            {tabButton('chat', 'Chat', <MessageSquare aria-hidden className="h-3.5 w-3.5" />, 'proposes · you apply')}
            {tabButton('notes', 'Notes', <StickyNote aria-hidden className="h-3.5 w-3.5" />)}
          </div>
          <button
            type="button"
            data-qid="deck:chat:collapse"
            data-qs-action="DECK_CHAT_COLLAPSE"
            aria-label="Collapse panel"
            title="Collapse this panel (Esc)"
            onClick={onCollapse}
            className="cursor-pointer rounded-md p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        {/* Both panes stay mounted; the hidden one keeps its state. */}
        <div className={`min-h-0 flex-1 ${tab === 'chat' ? '' : 'hidden'}`}>{chat}</div>
        <div className={`min-h-0 flex-1 ${tab === 'notes' ? '' : 'hidden'}`}>{notes}</div>
      </div>
    </aside>
  )
}
