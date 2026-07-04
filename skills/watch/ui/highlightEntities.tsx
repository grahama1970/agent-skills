import type { ReactNode } from 'react'
import type { EntityType } from './types'

const ENTITY_PATTERN = /\b(CMMC|NIST|SP\s*800-\d+|AC-\d+|AU-\d+|CM-\d+|IA-\d+|RA-\d+|SC-\d+|SI-\d+|CAPEC-\d+|CWE-\d+|T\d{4}(?:\.\d{3})?)\b/gi

function classifyEntity(entity: string): EntityType {
  const normalized = entity.toUpperCase()
  if (normalized.startsWith('CAPEC-')) return 'capec'
  if (normalized.startsWith('CWE-')) return 'cwe'
  if (/^T\d{4}/.test(normalized)) return 'attack-technique'
  if (/^[A-Z]{2}-\d+/.test(normalized)) return 'control'
  if (normalized.startsWith('SP')) return 'standard'
  return 'entity'
}

export function highlightEntities(
  text: string,
  onEntityClick?: (entity: string, type: EntityType) => void,
): ReactNode[] {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  ENTITY_PATTERN.lastIndex = 0
  while ((match = ENTITY_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))
    const entity = match[0]
    const type = classifyEntity(entity)
    nodes.push(
      <button
        key={`${match.index}-${entity}`}
        type="button"
        className="chat-prose__entity"
        data-entity-type={type}
        onClick={onEntityClick ? () => onEntityClick(entity, type) : undefined}
      >
        {entity}
      </button>,
    )
    lastIndex = match.index + entity.length
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}
