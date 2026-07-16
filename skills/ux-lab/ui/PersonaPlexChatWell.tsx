/**
 * Deprecated for production surfaces. Gallery/reference only.
 *
 * Production PersonaPlex chat must render through:
 *   SharedChatShell → PersonaPlexAdapter → ComplianceChatWell → ThinkingTrace → MessageFooter
 *
 * This wrapper intentionally contains no separate grid layout and no Google icon font usage.
 */
import React from 'react'
import SharedChatShell, { type SharedChatShellProps } from './SharedChatShell'

export type PersonaPlexChatWellProps = Omit<SharedChatShellProps, 'defaultMode' | 'surface' | 'showModeToggle'> & {
  galleryOnly?: boolean
}

export function PersonaPlexChatWell(props: PersonaPlexChatWellProps): JSX.Element {
  return (
    <SharedChatShell
      {...props}
      projectLabel={props.projectLabel ?? 'PersonaPlex gallery reference'}
      surface="final-site"
      defaultMode="personaplex"
      showModeToggle={false}
      shellQid={props.shellQid ?? 'personaplex:gallery:shared-shell'}
      emptyTitle={props.emptyTitle ?? 'PersonaPlex reference'}
      emptyDescription={props.emptyDescription ?? 'Production PersonaPlex surfaces use the shared ComplianceChatWell renderer.'}
    />
  )
}

export default PersonaPlexChatWell
