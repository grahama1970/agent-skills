/**
 * SPARTA brand shield (lambda inside a shield silhouette).
 *
 * Lucide-compatible: 24x24 viewBox, currentColor stroke, round joins — so it
 * sits next to lucide-react icons (Shield, Sparkles) without visual mismatch.
 *
 * Used as the live/disclosure marker for the compliance / evidence-case path
 * (`/create-evidence-case`), where generic reasoning surfaces use Sparkles.
 * Keep it simple at small sizes: shield outline + lambda caret, no inner ring.
 */
import type { CSSProperties } from 'react'

export interface SpartaShieldIconProps {
  size?: number
  /** Adds a subtle breathe animation (reduced-motion-safe via CSS). */
  animated?: boolean
  strokeWidth?: number
  className?: string
  style?: CSSProperties
}

export function SpartaShieldIcon({
  size = 16,
  animated = false,
  strokeWidth = 1.7,
  className,
  style,
}: SpartaShieldIconProps) {
  const cls = ['sparta-shield-icon', animated ? 'sparta-shield-icon--animated' : '', className]
    .filter(Boolean)
    .join(' ')
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cls}
      style={style}
      aria-hidden
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M9.2 15.4 12 8.4 14.8 15.4" />
    </svg>
  )
}
