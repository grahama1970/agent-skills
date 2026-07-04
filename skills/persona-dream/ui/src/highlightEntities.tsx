import type { ReactNode } from 'react'

type EntityType = 'skill' | 'control' | 'cwe' | 'attack' | 'framework' | 'sparta' | 'domain'

export type GlossaryType =
  | 'control'
  | 'cwe_weakness'
  | 'attack_technique'
  | 'attack_mobile_technique'
  | 'countermeasure'
  | 'technique'
  | 'domain_term'

export interface GlossaryTerm {
  term: string
  type: GlossaryType
}

const ENTITY_PATTERN = new RegExp(
  `(${
    [
      '\\/[a-z][\\w-]*',
      '\\b[A-Z]{2}-\\d+(?:\\.\\d+)?\\b',
      '\\bCWE-\\d+\\b',
      '\\b[TS]A?\\d{4}(?:\\.\\d{3})?\\b',
      '\\bCM-\\d{4}\\b',
      '\\bST-\\d{4}\\b',
      '\\bNIST (?:SP )?800-\\d+(?:[a-z])?(?:r\\d)?\\b',
      '\\bCMMC (?:Level )?[1-3]\\b',
      '\\bFedRAMP\\b',
      '\\bISO \\d{5}\\b',
      '\\bD3FEND\\b',
      '\\bATT&CK\\b',
      '\\bSTIG\\b',
    ].join('|')
  })`,
  'gi',
)

const ENTITY_STYLES: Record<EntityType, { color: string; bg: string }> = {
  skill: { color: '#4a9eff', bg: 'rgba(74,158,255,0.08)' },
  control: { color: '#00ff88', bg: 'rgba(0,255,136,0.08)' },
  cwe: { color: '#ff6b6b', bg: 'rgba(255,107,107,0.08)' },
  attack: { color: '#ffaa00', bg: 'rgba(255,170,0,0.08)' },
  framework: { color: '#c084fc', bg: 'rgba(192,132,252,0.08)' },
  sparta: { color: '#22d3ee', bg: 'rgba(34,211,238,0.08)' },
  domain: { color: '#f472b6', bg: 'rgba(244,114,182,0.08)' },
}

function buildGlossaryPattern(glossary: GlossaryTerm[]): RegExp | null {
  if (!glossary.length) return null
  const escaped = glossary.map((g) => g.term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  return new RegExp(`\\b(${escaped.join('|')})\\b`, 'gi')
}

function glossaryTypeToEntityType(gType: GlossaryType): EntityType {
  switch (gType) {
    case 'control':
      return 'control'
    case 'cwe_weakness':
      return 'cwe'
    case 'attack_technique':
    case 'attack_mobile_technique':
      return 'attack'
    case 'countermeasure':
    case 'technique':
      return 'sparta'
    case 'domain_term':
    default:
      return 'domain'
  }
}

function classifyEntity(token: string): EntityType {
  if (token.startsWith('/')) return 'skill'
  if (/^CWE-/.test(token)) return 'cwe'
  if (/^[TS]A?\d{4}/.test(token)) return 'attack'
  if (/^(?:CM|ST)-\d+$/.test(token)) return 'sparta'
  if (/^[A-Z]{2}-\d+/.test(token)) return 'control'
  return 'framework'
}

export function highlightEntities(text: string): ReactNode[] {
  const parts = text.split(ENTITY_PATTERN)
  return parts.map((part, i) => {
    ENTITY_PATTERN.lastIndex = 0
    if (!ENTITY_PATTERN.test(part)) return part
    const type = classifyEntity(part)
    const style = ENTITY_STYLES[type]
    return (
      <span
        key={i}
        style={{
          color: '#e2e8f0',
          fontWeight: type === 'control' || type === 'cwe' || type === 'attack' || type === 'sparta' ? 700 : 600,
          background: 'transparent',
          boxShadow: 'none',
          borderBottom: '1px dashed rgba(255,255,255,0.32)',
          padding: 0,
          fontFamily: type === 'skill' ? 'var(--font-mono, monospace)' : 'inherit',
          cursor: 'pointer',
        }}
        data-qs-action={type === 'skill' ? `SKILL_INVOKE_${part.slice(1).toUpperCase().replace(/-/g, '_')}` : `NAVIGATE_ENTITY_${part.replace(/[^A-Za-z0-9]/g, '_').toUpperCase()}`}
        data-qid={type === 'skill' ? `skill:${part.slice(1)}:ref` : `entity:${part}`}
        title={type === 'skill' ? `Skill: ${part}` : `${type}: ${part}`}
      >
        {part}
      </span>
    )
  })
}

export function highlightWithGlossary(text: string, glossary: GlossaryTerm[]): ReactNode[] {
  if (!glossary.length) return highlightEntities(text)

  const glossaryMap = new Map<string, GlossaryType>()
  glossary.forEach((g) => glossaryMap.set(g.term.toLowerCase(), g.type))
  const glossaryPattern = buildGlossaryPattern(glossary)
  const combinedPattern = new RegExp(glossaryPattern ? `${glossaryPattern.source}|${ENTITY_PATTERN.source}` : ENTITY_PATTERN.source, 'gi')

  const parts = text.split(combinedPattern)
  return parts.map((part, i) => {
    combinedPattern.lastIndex = 0
    if (!combinedPattern.test(part)) return part

    const glossaryType = glossaryMap.get(part.toLowerCase())
    const type = glossaryType ? glossaryTypeToEntityType(glossaryType) : classifyEntity(part)
    const style = ENTITY_STYLES[type]
    return (
      <span
        key={i}
        style={{
          color: '#e2e8f0',
          fontWeight: type === 'control' || type === 'cwe' || type === 'attack' || type === 'sparta' ? 700 : 600,
          background: 'transparent',
          boxShadow: 'none',
          borderBottom: '1px dashed rgba(255,255,255,0.32)',
          padding: 0,
          fontFamily: type === 'skill' ? 'var(--font-mono, monospace)' : 'inherit',
          cursor: 'pointer',
        }}
        data-qs-action={type === 'skill' ? `SKILL_INVOKE_${part.slice(1).toUpperCase().replace(/-/g, '_')}` : `NAVIGATE_ENTITY_${part.replace(/[^A-Za-z0-9]/g, '_').toUpperCase()}`}
        data-qid={type === 'skill' ? `skill:${part.slice(1)}:ref` : `entity:${part}`}
        title={type === 'domain' ? `Domain term: ${part}` : `${type}: ${part}`}
      >
        {part}
      </span>
    )
  })
}
