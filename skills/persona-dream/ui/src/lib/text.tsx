/**
 * text helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'

export function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export function parseJsonishText(text: string): unknown | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const candidates = [trimmed]
  const firstBrace = trimmed.indexOf('{')
  const lastBrace = trimmed.lastIndexOf('}')
  if (firstBrace >= 0 && lastBrace > firstBrace) candidates.push(trimmed.slice(firstBrace, lastBrace + 1))
  for (const candidate of candidates) {
    try {
      let parsed: unknown = JSON.parse(candidate)
      for (let i = 0; i < 2 && typeof parsed === 'string' && /^[\s{[]/.test(parsed); i += 1) {
        parsed = JSON.parse(parsed)
      }
      return parsed
    } catch {
      // Keep trying alternate slices; malformed memory text falls back to cleanup.
    }
  }
  return null
}

export function compactDisplayText(text: string, max = 420): string {
  const cleaned = text
    .replace(/Persona media asset key:\s*\S+\.?\s*/gi, '')
    .replace(/\\n/g, ' ')
    .replace(/\\/g, ' ')
    .replace(/["{}[\]]/g, ' ')
    .replace(/[_:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:(?:story|asset usage|asset id|description|summary|text|title)\s+){1,4}/i, '')
    .trim()
  if (cleaned.length <= max) return cleaned
  return `${cleaned.slice(0, max - 1).trim()}…`
}

export function decodeJsonStringLiteral(value: string): string {
  try {
    return JSON.parse(`"${value.replace(/"/g, '\\"')}"`)
  } catch {
    return value.replace(/\\"/g, '"').replace(/\\n/g, ' ')
  }
}

export function fileNameFromPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

export function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

export function payloadObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

export function payloadArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}
