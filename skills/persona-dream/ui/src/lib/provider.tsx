/**
 * provider helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'
import type { CSSProperties } from 'react'
import { nvis } from '../styles'
import type { DreamArtifact } from '../types'
import { dreamNumber } from './dream'
import { payloadObject } from './text'

export function videoProviderArtifactRole(artifact: DreamArtifact): string | null {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  if (/provider[_-]?selection|scorecard|video[_-]?provider[_-]?selection/.test(text)) return 'selection'
  if (/kling[_-]?scene[_-]?packet|scene[_-]?packet|video[_-]?provider[_-]?packet/.test(text)) return 'scene_packet'
  if (/provider[_-]?payload[_-]?mapping|request_body|dry_run.*request|provider_request|kling[_-]?request|one_scene_kling_request/.test(text)) return 'payload_mapping'
  if (/final[_-]?gate|provider[_-]?gate|readiness/.test(text)) return 'final_gate'
  if (/fal|registry|capabilit|preflight/.test(text)) return 'registry_preflight'
  return null
}

export function providerContractArtifactRole(artifact: DreamArtifact): string | null {
  const text = `${artifact.label} ${artifact.path}`.toLowerCase()
  if (/phase11[_-]?live[_-]?request\.v1\.json/.test(text)) return 'submitted_request'
  if (/phase11[_-]?provider[_-]?return[_-]?envelope\.v1\.json/.test(text)) return 'return_envelope'
  if (/shot[_-]?bible\.json/.test(text)) return 'shot_bible'
  if (/panel[_-]?distillation[_-]?contract\.json/.test(text)) return 'contract'
  if (/final[_-]?provider[_-]?payload[_-]?by[_-]?panel\.json/.test(text)) return 'payload_by_panel'
  if (/provider[_-]?payload[_-]?field[_-]?mapping\.json/.test(text)) return 'field_mapping'
  if (/provider[_-]?payload[_-]?omitted[_-]?context\.json/.test(text)) return 'omitted_context'
  if (/provider[_-]?media[_-]?publication[_-]?receipt\.json/.test(text)) return 'publication_receipt'
  if (/provider[_-]?media[_-]?probe[_-]?receipt\.json/.test(text)) return 'probe_receipt'
  if (/provider[_-]?schema[_-]?receipt\.json/.test(text)) return 'schema_receipt'
  if (/panel[_-]?distillation[_-]?review[_-]?receipt\.json/.test(text)) return 'review_receipt'
  if (/phase10[_-]?provider[_-]?contract[_-]?receipt\.json/.test(text)) return 'contract_receipt'
  if (/phase10.*check|provider[_-]?contract.*gate|dry[_-]?run[_-]?gate/.test(text)) return 'gate_receipt'
  if (/video[_-]?provider[_-]?packet/.test(text)) return 'video_provider_packet'
  if (/provider[_-]?registry[_-]?refresh|registry[_-]?refresh/.test(text)) return 'registry_refresh'
  if (/video[_-]?provider[_-]?scorecard|scorecard/.test(text)) return 'scorecard'
  return null
}

export function shortProviderHash(value: unknown): string {
  const text = typeof value === 'string' ? value : ''
  if (text.length <= 22) return text || 'missing'
  return `${text.slice(0, 14)}...${text.slice(-6)}`
}

export function providerContractStatusTone(value: unknown): CSSProperties {
  const text = String(value ?? '').toUpperCase()
  if (text.includes('PASS')) return nvis.providerContractPillPass
  if (text.includes('BLOCK') || text.includes('MISSING') || text.includes('FAIL')) return nvis.providerContractPillBlocked
  return nvis.providerContractPillDry
}

export function formatProviderContractBlocker(value: string): string {
  return value
    .replace(/^BLOCKED_/, '')
    .replace(/^NO_/, 'NO ')
    .replace(/_/g, ' ')
    .toLowerCase()
}

export function providerFitValue(provider: Record<string, unknown>, key: string): number | null {
  const fit = payloadObject(provider.fit)
  return dreamNumber(fit?.[key])
}

export function providerFitMax(providers: Array<Record<string, unknown>>, key: string): number | null {
  const values = providers.map((provider) => providerFitValue(provider, key)).filter((value): value is number => value != null)
  return values.length > 0 ? Math.max(...values) : null
}

export function providerFitDelta(provider: Record<string, unknown>, providers: Array<Record<string, unknown>>, key: string): number | null {
  const value = providerFitValue(provider, key)
  const max = providerFitMax(providers, key)
  if (value == null || max == null) return null
  return value - max
}

export function rebindProviderContractAssetPath(path: string, revisionRoot: string | null): string {
  if (!revisionRoot) return path
  const phaseIndex = path.indexOf('/phase_07_storyboard_live_tau/')
  if (phaseIndex < 0) return path
  return `${revisionRoot}${path.slice(phaseIndex)}`
}

export function highlightJsonForProviderContract(json: string): React.ReactNode[] {
  return json.split('\n').flatMap((line, lineIndex) => {
    const nodes = highlightJsonLineForProviderContract(line, lineIndex)
    return lineIndex === json.split('\n').length - 1 ? nodes : [...nodes, <br key={`json-br-${lineIndex}`} />]
  })
}

export function highlightJsonLineForProviderContract(line: string, lineIndex: number): React.ReactNode[] {
  const tokenRegex = /("(?:\\.|[^"\\])*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\],:])/g
  const nodes: React.ReactNode[] = []
  let cursor = 0
  let tokenIndex = 0
  for (const match of line.matchAll(tokenRegex)) {
    const token = match[0]
    const start = match.index ?? 0
    if (start > cursor) nodes.push(line.slice(cursor, start))
    const after = line.slice(start + token.length).trimStart()
    const style = providerContractJsonTokenStyle(token, after)
    nodes.push(<span key={`json-${lineIndex}-${tokenIndex++}`} style={style}>{token}</span>)
    cursor = start + token.length
  }
  if (cursor < line.length) nodes.push(line.slice(cursor))
  return nodes
}

export function providerContractJsonTokenStyle(token: string, after: string): CSSProperties {
  if (/^"/.test(token) && after.startsWith(':')) return nvis.providerContractSyntaxKey
  if (/^"/.test(token)) return nvis.providerContractSyntaxString
  if (/^(true|false|null)$/.test(token)) return nvis.providerContractSyntaxBoolean
  if (/^-?\d/.test(token)) return nvis.providerContractSyntaxNumber
  return nvis.providerContractSyntaxPunctuation
}

export function parseProviderContractAudioSummary(value: string): Array<{ label: string; value: string }> {
  return String(value ?? '')
    .split('/')
    .map((part) => part.trim())
    .map((part) => {
      const [label, ...rest] = part.split('=')
      return { label: label?.trim(), value: rest.join('=').trim() }
    })
    .filter((pair): pair is { label: string; value: string } => Boolean(pair.label && pair.value))
}

export function providerContractAudioValueTone(value: string): 'warning' | 'neutral' {
  return /missing|false|no_dialogue|not[_\s-]?run/i.test(value) ? 'warning' : 'neutral'
}
