import { useRef } from 'react'
import { MessageSquare, X } from 'lucide-react'
import { useRegisterAction } from '../hooks'

// Animated push-layout chat drawer. The panel stays MOUNTED while collapsed
// (width animates to 0), so the chat transcript and composer draft survive
// collapse/expand. Exits run faster than entrances (200ms vs 250ms,
// ease-out cubic-bezier(0.16,1,0.3,1)) so dismissal feels snappy while the
// expand stays trackable; the inner pane keeps its fixed width during the
// animation so chat content never reflows mid-slide. Esc collapses while
// focus is anywhere inside the drawer (the top-nav toggle stays available,
// but dismissal shouldn't require a trip back to the navbar).

const DRAWER_WIDTH = 380
const EASE = 'cubic-bezier(0.16, 1, 0.3, 1)'

export function ChatDrawer({
  collapsed,
  onCollapse,
  children,
}: {
  collapsed: boolean
  onCollapse: () => void
  children: React.ReactNode
}) {
  useRegisterAction('deck:chat:collapse', {
    app: 'pitchdeck',
    action: 'DECK_CHAT_COLLAPSE',
    label: 'Collapse chat',
    description: 'Collapse the deck chat drawer from its own header',
  })
  const ref = useRef<HTMLElement | null>(null)

  return (
    <aside
      ref={ref}
      aria-label="Deck chat"
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
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-slate-800 px-3">
          <div className="flex items-center gap-2">
            <MessageSquare aria-hidden className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-sm font-semibold text-slate-100">Chat</span>
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">proposes · you apply</span>
          </div>
          <button
            type="button"
            data-qid="deck:chat:collapse"
            data-qs-action="DECK_CHAT_COLLAPSE"
            aria-label="Collapse chat"
            title="Collapse the chat drawer (Esc)"
            onClick={onCollapse}
            className="cursor-pointer rounded-md p-1.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </aside>
  )
}
