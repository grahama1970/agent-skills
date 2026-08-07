/**
 * gate styles from the legacy `styles` object.
 *
 * Split for the same reason as `nvis`: a 1,033-line literal is not reviewable,
 * and each cluster belongs with the surface that uses it.
 */
import type { CSSProperties } from 'react'

export const baseGateStyles: Record<string, CSSProperties> = {
  gateStrip: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: 14,
    background: 'rgba(13, 17, 23, 0.62)',
    padding: 12,
  },
  gateNote: {
    color: '#cbd5e1',
    fontSize: 13,
    lineHeight: 1.35,
  },
  gateStatusGroup: {
    flex: '0 1 auto',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    whiteSpace: 'nowrap',
  },
  gateStatusIcon: {
    width: 32,
    height: 32,
    flex: '0 0 auto',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    border: '1px solid rgba(248, 113, 113, 0.34)',
    background: 'rgba(248, 113, 113, 0.1)',
    color: '#fecaca',
  },
  gateStatusCopy: {
    minWidth: 0,
    display: 'block',
  },
  gateStatusText: {
    display: 'block',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: 820,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  gateBadgesRow: {
    flex: '0 1 auto',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'nowrap',
    gap: 8,
    overflowX: 'auto',
    scrollbarWidth: 'none',
  },
  gateMiniBadge: {
    height: 28,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    border: '1px solid',
    borderRadius: 999,
    padding: '0 9px',
    fontSize: 10,
    fontWeight: 760,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    lineHeight: 1,
  },
}
