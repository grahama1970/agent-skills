/**
 * dream helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React from 'react'

export function dreamStringField(doc: Record<string, unknown>, fields: string[]): string {
  for (const field of fields) {
    const value = doc[field]
    if (typeof value === 'string' && value.trim().length > 0) return value.trim()
  }
  return ''
}

export function dreamExtractPathFromText(text: string): string {
  const match = text.match(/\/(?:mnt|home)\/[^\s"'<>)]*\.(?:png|jpe?g|webp|gif|mp4|mov|webm|wav|mp3|ogg)\b/i)
  return match?.[0] ?? ''
}

export function dreamInferMediaType(path: string, explicit?: string): string {
  const normalized = String(explicit ?? '').trim().toLowerCase()
  if (normalized === 'image' || normalized === 'photo') return 'png'
  if (normalized === 'audio') return 'wav'
  if (normalized === 'video') return 'mp4'
  const ext = path.match(/\.([a-z0-9]+)(?:$|\?)/i)?.[1]?.toLowerCase()
  return ext ?? normalized
}

export function dreamRenderableMediaUrl(value?: string): boolean {
  const url = String(value ?? '').trim()
  if (!url) return false
  if (/^\/(?:api|assets)\//i.test(url)) return true
  return /\.(?:png|jpe?g|webp|gif|svg|avif|mp4|mov|webm|wav|mp3|ogg|flac|m4a)(?:[?#].*)?$/i.test(url)
}

export function dreamNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function dreamBooleanLabel(value: unknown): string {
  if (value === true) return 'true'
  if (value === false) return 'false'
  return 'missing'
}

export function dreamList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []
}

export function dreamDisplayCode(value: string): string {
  return value.replace(/_/g, ' ')
}

export function parseDreamJson(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

export function shouldIgnoreDreamPaneArrowKey(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return true
  const target = event.target
  if (!(target instanceof Element)) return false
  return Boolean(target.closest([
    'input',
    'textarea',
    'select',
    'button',
    '[contenteditable="true"]',
    '[role="button"]',
    '[role="combobox"]',
    '[role="dialog"]',
    '[role="listbox"]',
    '[role="menu"]',
    '[role="slider"]',
    '[role="spinbutton"]',
    '[role="tab"]',
    '[role="textbox"]',
    '[data-arrow-key-scope="local"]',
  ].join(',')))
}
