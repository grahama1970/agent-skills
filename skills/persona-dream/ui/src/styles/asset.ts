/**
 * asset styles, split out of the 4,439-line `nvis` object.
 *
 * Styles live beside the surface that uses them so a panel can be extracted
 * with its own visual vocabulary instead of reaching into one global bag.
 */
import type { CSSProperties } from 'react'

export const assetStyles: Record<string, CSSProperties> = {
  assetStrip: {
    marginTop: 30,
    paddingTop: 24,
    borderTop: '1px solid rgba(255,255,255,0.08)',
  },
  assetStripTitle: {
    margin: '0 0 14px',
    color: '#64748b',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.2em',
    textTransform: 'uppercase',
  },
  assetStripEmpty: {
    color: '#64748b',
    fontSize: 12,
    padding: '12px 0',
  },
  assetTable: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    tableLayout: 'fixed' as const,
  },
  assetTableHeaderRow: {
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  assetTableTh: {
    padding: '0 10px 9px 0',
    color: '#64748b',
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    textAlign: 'left' as const,
  },
  assetTableRow: {
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  assetTableThumbCell: {
    width: 86,
    padding: '12px 14px 12px 0',
    verticalAlign: 'top',
  },
  assetTableDescription: {
    padding: '12px 14px 12px 0',
    verticalAlign: 'top',
  },
  assetTableTitle: {
    display: 'block',
    color: '#e2e8f0',
    fontSize: 12,
    lineHeight: 1.35,
    fontWeight: 650,
    marginBottom: 5,
  },
  assetTableCaption: {
    display: 'block',
    color: '#94a3b8',
    fontSize: 11,
    lineHeight: 1.45,
  },
  assetTableSource: {
    width: 160,
    padding: '12px 0',
    verticalAlign: 'top',
    color: '#64748b',
    fontSize: 10,
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    overflowWrap: 'anywhere' as const,
  },
  assetThumbButton: {
    width: 72,
    height: 52,
    display: 'flex',
    padding: 0,
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: 10,
    background: '#141414',
    cursor: 'pointer',
    overflow: 'hidden',
  },
  assetThumbImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover' as const,
    display: 'block',
  },
}
