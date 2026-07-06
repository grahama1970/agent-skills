import type { EvidenceCaseData } from './types'

type ReceiptTone = 'satisfied' | 'blocked' | 'pending'

export function deriveArtifactStateLine(data: EvidenceCaseData): string {
  const artifact = data.artifact?.name || data.bound_artifact
  return artifact ? `Artifact: ${artifact}` : 'Artifact pending'
}

export function deriveEvidenceTierBadge(data: EvidenceCaseData): string {
  const tier = data.evidence_tier || data.metadata?.evidence_tier
  return String(tier || 'evidence').toUpperCase()
}

export function deriveReceiptRailTone(data: EvidenceCaseData): ReceiptTone {
  const verdict = String(data.verdict || '').toLowerCase()
  const trace = String(data.trace_state || '').toLowerCase()
  if (verdict === 'fail' || verdict === 'failed' || verdict === 'not_satisfied') return 'blocked'
  if (trace === 'bound' || verdict === 'pass' || verdict === 'passed' || verdict === 'satisfied') return 'satisfied'
  return 'pending'
}

export function deriveReceiptReason(data: EvidenceCaseData): string {
  return data.gate_summary || data.metadata?.gate_summary || 'Receipt details pending.'
}

export function deriveReceiptStateLine(data: EvidenceCaseData): string {
  const tone = deriveReceiptRailTone(data)
  if (tone === 'satisfied') return 'Evidence receipt bound'
  if (tone === 'blocked') return 'Evidence receipt blocked'
  return 'Evidence receipt pending'
}

export function deriveReceiptSummary(data: EvidenceCaseData): string {
  if (data.summary) return data.summary
  if (Array.isArray(data.claims) && data.claims[0]) return data.claims[0]
  return 'Evidence case generated; open workspace for full trace.'
}

export function evidenceTierBadgeTone(tier: string): { color: string; bg: string; border: string } {
  const normalized = tier.toLowerCase()
  if (normalized.includes('blocked') || normalized.includes('fail')) {
    return { color: '#ff6b7a', bg: 'rgba(255,107,122,0.12)', border: 'rgba(255,107,122,0.35)' }
  }
  if (normalized.includes('bound') || normalized.includes('pass')) {
    return { color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)', border: 'rgba(45,212,191,0.35)' }
  }
  return { color: '#ffd166', bg: 'rgba(255,209,102,0.12)', border: 'rgba(255,209,102,0.35)' }
}

export function receiptShowsDraftToken(data: EvidenceCaseData): boolean {
  const state = String(data.approval_state || data.human_review_state || '').toLowerCase()
  return !state || state === 'draft' || state === 'pending'
}
