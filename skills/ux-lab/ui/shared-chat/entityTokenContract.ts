/**
 * entityTokenContract — the single visual contract for inline entity tokens
 * (grahama1970/sparta#48). Both EntityToken (explorerUtils.tsx) and the chat
 * renderer's StructuredEntityToken delegate their token styling here, so the
 * two implementations can no longer diverge.
 *
 * Colour comes from the semantic tokens in styles/design-tokens.css
 * (--entity-threat/hardware/framework/default), never from raw colour props.
 *
 * Zero layout shift on hover: the horizontal padding is applied in BOTH states
 * and cancelled by an equal negative margin, so the token's contribution to
 * line layout is byte-identical hovered and unhovered; hover changes paint only
 * (border-style, background tint, radius).
 */
import type { CSSProperties } from 'react'

export type EntityTokenType = 'threat' | 'hardware' | 'framework' | 'default'

export function entityTokenColor(type: EntityTokenType): string {
  return `var(--entity-${type})`
}

/** Map loose upstream entity/framework labels onto the shared vocabulary. */
export function entityTokenTypeFrom(raw: string | undefined): EntityTokenType {
  const value = (raw ?? '').toLowerCase()
  if (/cwe|cve|attack|att&ck|threat|weakness|vulnerab/.test(value)) return 'threat'
  if (/hardware|component|asset|device|bus|sensor/.test(value)) return 'hardware'
  if (/sparta|nist|control|framework|d3fend|iso|esa/.test(value)) return 'framework'
  return 'default'
}

export function entityTokenStyle(type: EntityTokenType, hovered: boolean, clickable: boolean): CSSProperties {
  const color = entityTokenColor(type)
  return {
    display: 'inline',
    fontFamily: '"SF Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    fontSize: '0.92em',
    fontWeight: 650,
    color,
    cursor: clickable ? 'crosshair' : 'help',
    // Padding present in BOTH states, cancelled by equal negative margin →
    // zero layout shift on hover.
    padding: '0 3px',
    margin: '0 -3px',
    borderBottomWidth: 1,
    borderBottomStyle: hovered ? 'solid' : 'dashed',
    borderBottomColor: color,
    backgroundColor: hovered ? `color-mix(in srgb, ${color} 12%, transparent)` : 'transparent',
    borderRadius: hovered ? 3 : 0,
    transition: 'background-color 120ms ease, border-bottom-color 120ms ease',
    overflowWrap: 'break-word',
  }
}
