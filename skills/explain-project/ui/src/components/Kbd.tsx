import type {
  ReactNode,
} from 'react'

/** Shared keycap hint (monospace, inset shadow, theme-agnostic). */
export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd-badge">{children}</kbd>
}
