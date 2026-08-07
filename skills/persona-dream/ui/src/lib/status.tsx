/**
 * status helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import type { DreamStage, StatusTone, TraceNodeKind } from '../types'

export function statusTone(status: string): StatusTone {
  const normalized = status.toUpperCase()
  if (normalized.includes('BLOCK') || normalized.includes('FAIL') || normalized.includes('STALE') || normalized.startsWith('NO_')) return 'blocked'
  if (normalized.includes('DRY_RUN')) return 'dry'
  if (
    normalized.includes('PASS')
    || normalized.includes('RETURN_RECEIVED')
    || normalized.includes('EVIDENCE_FOUND')
    || normalized.includes('READY')
    || normalized.includes('CALLED')
    || normalized.includes('AUTHORIZED')
  ) return 'pass'
  return 'unknown'
}

export function statusLabel(status: string): string {
  const normalized = status.toUpperCase()
  if (
    normalized.includes('PASS')
    || normalized.includes('EVIDENCE_FOUND')
    || normalized.includes('READY')
    || normalized.includes('CALLED')
    || normalized.includes('AUTHORIZED')
  ) return 'Pass'
  if (normalized.includes('MISSING')) return 'Missing evidence'
  if (normalized.includes('BLOCK')) return 'Blocked'
  if (normalized.includes('FAIL')) return 'Fail'
  if (normalized.includes('DRY_RUN')) return 'Dry run'
  return status.replace(/_/g, ' ')
}

export const toneStyles: Record<StatusTone, CSSProperties> = {
  pass: { borderColor: 'rgba(52, 211, 153, 0.38)', background: 'rgba(52, 211, 153, 0.1)', color: '#a7f3d0' },
  dry: { borderColor: 'rgba(56, 189, 248, 0.38)', background: 'rgba(56, 189, 248, 0.1)', color: '#bae6fd' },
  blocked: { borderColor: 'rgba(248, 113, 113, 0.38)', background: 'rgba(248, 113, 113, 0.1)', color: '#fecaca' },
  unknown: { borderColor: 'rgba(148, 163, 184, 0.38)', background: 'rgba(148, 163, 184, 0.1)', color: '#cbd5e1' },
}

export function isExecutionReceiptArtifact(artifact: DreamStage['artifacts'][number]): boolean {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  return /\.json($|\?)/.test(text) || /receipt|verdict|manifest|packet|contract|gate|ledger|mapping|audit|linter/.test(text)
}

export function nodeKindColor(kind: TraceNodeKind): string {
  switch (kind) {
    case 'idea': return '#4a9eff'
    case 'media': return '#a78bfa'
    case 'video': return '#a78bfa'
    case 'audio': return '#8b5cf6'
    case 'person': return '#60a5fa'
    case 'object': return '#4ade80'
    case 'place': return '#f59e0b'
    default: return '#94a3b8'
  }
}

export function relationshipColor(relationship: string): string {
  const rel = relationship.toLowerCase()
  if (rel.includes('tom') || rel.includes('belief') || rel.includes('relationship')) return '#f472b6'
  if (rel.includes('audio')) return nodeKindColor('audio')
  if (rel.includes('video')) return nodeKindColor('video')
  if (rel.includes('visual') || rel.includes('image')) return nodeKindColor('media')
  if (rel.includes('environment') || rel.includes('surf')) return nodeKindColor('place')
  return '#4a9eff'
}
