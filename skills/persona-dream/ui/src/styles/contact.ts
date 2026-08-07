/**
 * contact styles, split out of the 4,439-line `nvis` object.
 *
 * Styles live beside the surface that uses them so a panel can be extracted
 * with its own visual vocabulary instead of reaching into one global bag.
 */
import type { CSSProperties } from 'react'

export const contactStyles: Record<string, CSSProperties> = {
  contactSheetGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 16,
    padding: 0,
    background: 'transparent',
    borderRadius: 0,
  },
  contactSheetCard: {
    position: 'relative' as const,
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 14,
    overflow: 'hidden',
    background: 'rgba(255,255,255,0.025)',
    cursor: 'zoom-in',
  },
  contactSheetThumb: {
    width: '100%',
    height: 128,
    objectFit: 'cover' as const,
    opacity: 0.92,
    display: 'block',
  },
  contactSheetCaption: {
    position: 'absolute' as const,
    left: 8,
    right: 8,
    bottom: 8,
    display: 'flex',
    justifyContent: 'space-between',
    gap: 8,
    color: '#e2e8f0',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    textShadow: '0 1px 10px rgba(0,0,0,0.85)',
    pointerEvents: 'none' as const,
  },
  contactSheetOverlay: {
    position: 'absolute' as const,
    inset: 0,
    background: 'rgba(0,0,0,0.6)',
    opacity: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'opacity 200ms ease',
  },
  contactSheetAction: {
    color: '#fff',
    fontSize: 11,
    padding: '4px 10px',
    background: '#7c3aed',
    borderRadius: 6,
    border: 0,
    cursor: 'pointer',
  },
  contactSheetEmpty: {
    gridColumn: '1 / -1',
    padding: '48px 0',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    border: '1px dashed #64748b',
    borderRadius: 8,
    gap: 8,
  },
  contactSheetTrigger: {
    color: '#4a9eff',
    fontSize: 11,
    textDecoration: 'underline',
    background: 'transparent',
    border: 0,
    cursor: 'pointer',
  },
}
