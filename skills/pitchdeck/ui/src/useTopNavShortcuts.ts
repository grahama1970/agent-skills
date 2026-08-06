import { useCallback, useEffect } from 'react'

export type ShortcutMap = Record<string, () => void>

interface UseTopNavShortcutsOptions {
  enabled?: boolean
}

/**
 * Bind keyboard shortcuts for top-bar navigation (Gemini top-nav spec).
 * - Focus guard: ignores keystrokes while INPUT/TEXTAREA/SELECT/contentEditable is focused.
 * - `mod` normalizes metaKey (⌘) and ctrlKey so one map serves both platforms.
 * - Combos like 'mod+1' are best-effort in a browser: Chrome reserves Ctrl+1..8
 *   for tab switching, so single-key entries ('p', 'd', …) are the reliable tier.
 */
export function useTopNavShortcuts(shortcuts: ShortcutMap, options: UseTopNavShortcutsOptions = {}) {
  const { enabled = true } = options

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled) return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      const isMod = event.metaKey || event.ctrlKey
      const key = event.key.toLowerCase()
      const comboParts: string[] = []
      if (isMod) comboParts.push('mod')
      if (event.shiftKey) comboParts.push('shift')
      if (event.altKey) comboParts.push('alt')
      comboParts.push(key)
      const combo = comboParts.join('+')
      const action = shortcuts[combo] || (combo === key ? shortcuts[key] : undefined)
      if (action) {
        event.preventDefault()
        action()
      }
    },
    [shortcuts, enabled],
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}
