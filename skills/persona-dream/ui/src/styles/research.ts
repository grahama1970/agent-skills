/**
 * research styles, split out of the 4,439-line `nvis` object.
 *
 * Styles live beside the surface that uses them so a panel can be extracted
 * with its own visual vocabulary instead of reaching into one global bag.
 */
import type { CSSProperties } from 'react'

export const researchStyles: Record<string, CSSProperties> = {
  researchPane: {
    minHeight: 0,
    overflow: 'auto',
    borderLeft: '1px solid #334155',
    background: '#111111',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  researchPaneHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  researchPaneTitle: {
    color: '#4a9eff',
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  researchPaneBadge: {
    fontSize: 9,
    color: '#64748b',
    border: '1px solid #334155',
    borderRadius: 4,
    padding: '2px 6px',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  researchList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  researchAccordion: {
    border: '1px solid rgba(75, 85, 99, 0.9)',
    background: '#090909',
  },
  researchAccordionSummary: {
    minHeight: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 10px',
    color: '#d1d5db',
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    userSelect: 'none',
  },
  researchAccordionContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    borderTop: '1px solid rgba(75, 85, 99, 0.65)',
    padding: 8,
  },
  researchCard: {
    background: '#1a1a1a',
    padding: 10,
    borderRadius: 0,
    border: '1px solid rgba(255,255,255,0.08)',
  },
  researchLink: {
    color: '#4a9eff',
    fontSize: 11,
    fontWeight: 600,
    textDecoration: 'underline',
    display: 'block',
    marginBottom: 4,
  },
  researchSnippet: {
    color: '#64748b',
    fontSize: 10,
    lineHeight: 1.45,
    margin: 0,
  },
}
