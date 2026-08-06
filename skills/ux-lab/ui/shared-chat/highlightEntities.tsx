/**
 * Entity highlighting — shared across Embry Terminal + SPARTA Explorer.
 * Detects compliance entities (NIST controls, CWEs, ATT&CK, SPARTA, frameworks)
 * and skill names (/skill-name) in text, returns JSX with lightweight inline emphasis.
 */
import React, { type ReactNode } from 'react';
import { entityTokenStyle, entityTokenTypeFrom } from './entityTokenContract';
import { createPortal } from 'react-dom';
import type { EntityType, EvidenceCaseSpan } from './types';
export type { EntityType } from './types';

// Glossary term types from /create-evidence-case daemon
export type GlossaryType = 'control' | 'cwe_weakness' | 'attack_technique' | 'attack_mobile_technique' | 'countermeasure' | 'technique' | 'domain_term';

export interface GlossaryTerm {
  term: string;
  type: GlossaryType;
}

const ENTITY_STYLES: Record<EntityType, { color: string; bg: string }> = {
  skill:     { color: '#4a9eff', bg: 'rgba(74,158,255,0.08)' },
  control:   { color: '#00ff88', bg: 'rgba(0,255,136,0.08)' },
  cwe:       { color: '#ff6b6b', bg: 'rgba(255,107,107,0.08)' },
  attack:    { color: '#ffaa00', bg: 'rgba(255,170,0,0.08)' },
  framework: { color: '#c084fc', bg: 'rgba(192,132,252,0.08)' },
  sparta:    { color: '#22d3ee', bg: 'rgba(34,211,238,0.08)' },
  domain:    { color: '#f472b6', bg: 'rgba(244,114,182,0.08)' },
};

// sparta#48: delegates the token visual contract to entityTokenContract so the
// chat renderer and explorerUtils EntityToken can no longer diverge. The
// legacy color/bg props are ignored for styling; type selects the semantic
// --entity-* token.
function forensicEntityStyle(_style: { color: string; bg: string }, type: EntityType, onEntityClick?: unknown, hovered = false) {
  return entityTokenStyle(entityTokenTypeFrom(String(type)), hovered, Boolean(onEntityClick))
}

// Map daemon glossary types to UI EntityType
export function glossaryTypeToEntityType(gType: GlossaryType): EntityType {
  switch (gType) {
    case 'control': return 'control';
    case 'cwe_weakness': return 'cwe';
    case 'attack_technique':
    case 'attack_mobile_technique': return 'attack';
    case 'countermeasure': return 'sparta';
    case 'technique': return 'sparta';
    case 'domain_term':
    default: return 'domain';
  }
}

export function classifyEntity(token: string): EntityType {
  if (token.startsWith('/')) return 'skill';
  const upper = token.toUpperCase();
  if (upper.startsWith('CWE-')) return 'cwe';
  if (upper.startsWith('CM-') || upper.startsWith('ST-')) return 'sparta';
  if (upper.startsWith('T') || upper.startsWith('TA')) return 'attack';
  if (token.includes('-')) return 'control';
  return 'framework';
}

export function getEntityStyle(type: EntityType) {
  return ENTITY_STYLES[type];
}

export function highlightEntities(
  text: string,
  _onEntityClick?: (entity: string, type: EntityType) => void,
): ReactNode[] {
  return [text];
}

/**
 * Legacy compatibility wrapper. Entity display must be driven by structured
 * spans from /extract-entities, not browser-side text parsing.
 */
export function highlightWithGlossary(
  text: string,
  _glossary: GlossaryTerm[],
  _onEntityClick?: (entity: string, type: EntityType) => void,
): ReactNode[] {
  return [text];
}


const FRAMEWORK_ENTITY: Record<string, EntityType> = {
  SPARTA: 'sparta',
  CWE: 'cwe',
  NIST: 'control',
  CMMC: 'framework',
};

function entityTypeForSpan(span: EvidenceCaseSpan): EntityType {
  if (span.kind === 'control_id') {
    const fw = String(span.framework ?? '').toUpperCase();
    if (fw === 'CWE') return 'cwe';
    if (fw === 'SPARTA') return 'sparta';
    return 'control';
  }
  if (span.kind === 'phrase' || span.kind === 'aerospace_term') return 'domain';
  return classifyEntity(span.text ?? '');
}

function spanMatchesRenderedText(span: EvidenceCaseSpan, slice: string): boolean {
  const expected = [
    span.text,
    span.name,
    span.mention,
    span.label,
    span.entity,
  ]
    .filter((value): value is string => typeof value === 'string' && value.length > 0);
  if (!expected.length) return false;
  return expected.some((value) => value === slice);
}

function spanStringField(span: EvidenceCaseSpan, key: string): string | undefined {
  const value = span[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : undefined;
}

function spanTooltipRows(span: EvidenceCaseSpan, slice: string, type: EntityType): Array<[string, string]> {
  const framework = spanStringField(span, 'framework');
  const control = spanStringField(span, 'control_id') ?? spanStringField(span, 'entity') ?? spanStringField(span, 'id') ?? slice;
  const definition =
    spanStringField(span, 'definition')
    ?? spanStringField(span, 'description')
    ?? spanStringField(span, 'summary')
    ?? spanStringField(span, 'name');
  const category = spanStringField(span, 'category') ?? spanStringField(span, 'kind') ?? spanStringField(span, 'type') ?? type;

  return [
    ['Category', category],
    ['Control', control],
    framework ? ['Framework', framework] : undefined,
    definition ? ['Definition', definition] : undefined,
    span.grounded_to_framework !== undefined ? ['Grounded', span.grounded_to_framework ? 'yes' : 'no'] : undefined,
  ].filter((row): row is [string, string] => Boolean(row));
}

function entityCategoryColor(type: EntityType, span?: EvidenceCaseSpan): string {
  const framework = String(span?.framework ?? '').toUpperCase();
  if (framework === 'SPARTA' || type === 'sparta') return '#22d3ee';
  if (framework === 'NIST' || type === 'control') return '#00ff88';
  if (framework === 'CWE' || type === 'cwe') return '#ff6b6b';
  if (framework.includes('ATT') || type === 'attack') return '#d4af37';
  if (type === 'framework') return '#c084fc';
  return '#94a3b8';
}

function tooltipPosition(target: HTMLElement, width: number) {
  const rect = target.getBoundingClientRect();
  const center = rect.left + rect.width / 2;
  const half = width / 2;
  const margin = 12;
  const left = Math.min(Math.max(center, margin + half), window.innerWidth - margin - half);
  const placement = rect.top > 190 ? 'top' as const : 'bottom' as const;
  const top = placement === 'top' ? rect.top - 12 : rect.bottom + 12;
  const arrowOffset = Math.min(Math.max(center - left, -half + 18), half - 18);
  return { left, top, placement, arrowOffset };
}

function StructuredEntityToken({
  slice,
  span,
  type,
  styleColor,
  onEntityClick,
  start,
  end,
}: {
  slice: string;
  span: EvidenceCaseSpan;
  type: EntityType;
  styleColor: string;
  onEntityClick?: (entity: string, type: EntityType) => void;
  start: number;
  end: number;
}) {
  const [open, setOpen] = React.useState(false);
  const [hovered, setHovered] = React.useState(false);
  const [coords, setCoords] = React.useState<ReturnType<typeof tooltipPosition> | null>(null);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipWidth = 340;
  const tooltipTitle = spanStringField(span, 'name') ?? spanStringField(span, 'label') ?? slice;
  const rows = spanTooltipRows(span, slice, type);
  const categoryColor = entityCategoryColor(type, span);

  const clearTimer = React.useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const updateCoords = React.useCallback((target: HTMLElement) => {
    setCoords(tooltipPosition(target, tooltipWidth));
  }, []);

  const handleEnter = React.useCallback((target: HTMLElement) => {
    clearTimer();
    setHovered(true);
    updateCoords(target);
    setOpen(true);
  }, [clearTimer, updateCoords]);

  const handleLeave = React.useCallback(() => {
    clearTimer();
    setHovered(false);
    setOpen(false);
  }, [clearTimer]);

  React.useEffect(() => clearTimer, [clearTimer]);

  return (
    <span
      key={`span-${start}-${end}`}
      className="chat-entity-hit sentence-entity-hit"
      data-qid={`entity-span:${start}-${end}`}
      data-entity-grounded={span.grounded_to_framework ? 'true' : 'false'}
      aria-label={`${tooltipTitle}. ${rows.map(([label, value]) => `${label}: ${value}`).join('. ')}`}
      onClick={onEntityClick ? (e) => { e.stopPropagation(); onEntityClick(slice, type); } : undefined}
      style={{
        ...forensicEntityStyle({ color: styleColor, bg: 'transparent' }, type, onEntityClick, hovered),
      }}
      onMouseEnter={(e) => handleEnter(e.currentTarget)}
      onMouseMove={(e) => updateCoords(e.currentTarget)}
      onMouseLeave={handleLeave}
      onPointerEnter={(e) => handleEnter(e.currentTarget)}
      onPointerMove={(e) => updateCoords(e.currentTarget)}
      onPointerLeave={handleLeave}
      onFocus={(e) => handleEnter(e.currentTarget)}
      onBlur={handleLeave}
    >
      {slice}
      {open && coords && typeof document !== 'undefined' && createPortal(
        <span
          data-role="chat-entity-tooltip"
          data-qid={`entity-tooltip:${start}-${end}`}
          style={{
            position: 'fixed',
            left: coords.left,
            top: coords.top,
            transform: coords.placement === 'top' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
            zIndex: 2147483647,
            width: tooltipWidth,
            maxWidth: 'min(82vw, 380px)',
            pointerEvents: 'none',
            background: '#121417',
            border: '1px solid rgba(212,175,55,0.45)',
            borderRadius: 7,
            boxShadow: '0 14px 32px rgba(0,0,0,0.48)',
            padding: '10px 12px',
            textAlign: 'left',
            color: '#e5e7eb',
            fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, color: '#f1f5f9', fontSize: 12, fontWeight: 650, lineHeight: 1.25, marginBottom: 7 }}>
            <span
              aria-hidden="true"
              style={{
                width: 7,
                height: 7,
                flex: '0 0 auto',
                borderRadius: 999,
                backgroundColor: categoryColor,
                boxShadow: `0 0 8px ${categoryColor}66`,
              }}
            />
            <span>{tooltipTitle}</span>
          </span>
          <span style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {rows.map(([label, value]) => (
              <span key={`${label}:${value}`} style={{ display: 'grid', gridTemplateColumns: '76px 1fr', gap: 8, fontSize: 11, lineHeight: 1.35 }}>
                <span style={{ color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', fontSize: 9 }}>{label}</span>
                <span style={{ color: '#dbe3ee' }}>{value}</span>
              </span>
            ))}
          </span>
          <span
            style={{
              position: 'absolute',
              left: `calc(50% + ${coords.arrowOffset}px)`,
              top: coords.placement === 'top' ? '100%' : -5,
              width: 10,
              height: 10,
              background: '#121417',
              borderRight: '1px solid rgba(212,175,55,0.45)',
              borderBottom: '1px solid rgba(212,175,55,0.45)',
              transform: coords.placement === 'top' ? 'translateX(-50%) rotate(45deg)' : 'translateX(-50%) rotate(225deg)',
            }}
          />
        </span>,
        document.body,
      )}
    </span>
  );
}

/**
 * Highlight text using pre-computed evidence_case.spans from /create-evidence-case backfill.
 * Spans take precedence over regex/glossary highlighting.
 */
export function highlightWithSpans(
  text: string,
  spans: EvidenceCaseSpan[],
  onEntityClick?: (entity: string, type: EntityType) => void,
): ReactNode[] {
  if (!spans.length) return [text];

  const sorted = [...spans]
    .filter((s): s is EvidenceCaseSpan & { span: [number, number] } => Array.isArray(s.span) && s.span.length === 2 && s.span[1] > s.span[0])
    .sort((a, b) => a.span[0] - b.span[0]);

  const nodes: ReactNode[] = [];
  let lastEnd = 0;

  for (const s of sorted) {
    const [start, end] = s.span;
    if (start < lastEnd) continue;
    if (start > text.length) break;
    const clampedEnd = Math.min(end, text.length);

    const slice = text.slice(start, clampedEnd);
    if (!spanMatchesRenderedText(s, slice)) continue;

    if (start > lastEnd) nodes.push(text.slice(lastEnd, start));

    const type = entityTypeForSpan(s);
    const style = ENTITY_STYLES[type];

    nodes.push(
      <StructuredEntityToken
        key={`span-${start}-${end}`}
        slice={slice}
        span={s}
        type={type}
        styleColor={style.color}
        onEntityClick={onEntityClick}
        start={start}
        end={end}
      />,
    );
    lastEnd = clampedEnd;
  }

  if (lastEnd < text.length) nodes.push(text.slice(lastEnd));
  return nodes;
}

export { ENTITY_STYLES };
