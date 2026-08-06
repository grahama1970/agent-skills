import type { ReactNode } from 'react'

interface ActionTooltipProps {
  children: ReactNode
  content: string
}

export function ActionTooltip({ children, content }: ActionTooltipProps) {
  return (
    <span className="shared-chat-action-tooltip">
      {children}
      <span className="shared-chat-action-tooltip__bubble" role="tooltip">
        {content}
        <span className="shared-chat-action-tooltip__caret" aria-hidden="true" />
      </span>
    </span>
  )
}

export default ActionTooltip
