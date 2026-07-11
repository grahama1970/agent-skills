import React from 'react'

export type EntityAnnotation = {
  id: string
  mention: string
  start: number
  end: number
  kind: string
  grounded: boolean
  source: string
  extractionEventId: string
  extractionResultSha256: string
}

export function EntityAnnotatedText({ content, annotations }: { content: string; annotations: EntityAnnotation[] }): JSX.Element {
  const sorted = [...annotations].sort((left, right) => left.start - right.start || left.end - right.end)
  let cursor = 0
  const nodes: React.ReactNode[] = []
  for (const annotation of sorted) {
    if (annotation.start < cursor || annotation.start < 0 || annotation.end > content.length || annotation.start >= annotation.end || content.slice(annotation.start, annotation.end) !== annotation.mention) {
      throw new Error('entity_annotation_span_invalid')
    }
    if (annotation.start > cursor) nodes.push(content.slice(cursor, annotation.start))
    nodes.push(
      <span
        key={annotation.id}
        data-qid={`shared-chat:entity:${annotation.id}`}
        data-entity-kind={annotation.kind}
        data-entity-start={annotation.start}
        data-entity-end={annotation.end}
        data-extraction-event-id={annotation.extractionEventId}
        data-extraction-result-sha256={annotation.extractionResultSha256}
        title={`${annotation.kind} · ${annotation.source}`}
        style={{ borderBottom: '1px dotted rgba(161,161,170,0.9)', cursor: 'help' }}
      >
        {annotation.mention}
      </span>,
    )
    cursor = annotation.end
  }
  if (cursor < content.length) nodes.push(content.slice(cursor))
  return <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55, fontSize: 14 }}>{nodes}</div>
}

export default EntityAnnotatedText
