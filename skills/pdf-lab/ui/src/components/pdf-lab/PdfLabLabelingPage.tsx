/**
 * PdfLabLabelingPage — drawing-first annotator for /review-extraction
 * expected_elements.json contracts. Built as a focused replacement for
 * Label Studio for our single-page-PDF workflow:
 *
 *   - Canvas is the primary surface (no read-only/edit-mode tabs).
 *   - 11 family chips are always visible on the left, color-coded.
 *   - Click chip → drag rect → done. No keyboard memorization required.
 *   - Right pane: live region list with per-region text_hint / label inputs.
 *   - JSON Import seeds boxes from existing expected_elements.json, VIA
 *     project exports, or LS predictions. Export emits expected_elements.json.
 *
 * Page coords are stored as normalized [0..1] xyxy so the JSON is rendering-
 * resolution independent and matches the matcher contract directly.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Circle, CircleDashed, UserCheck } from 'lucide-react'
import {
  type BreadcrumbNode,
  type BreadcrumbNodeKind,
  type ExportableRegion,
  type ExpectedElement,
  type TocEntry,
  BREADCRUMB_NODE_KINDS,
  applyKnownBreadcrumbNode,
  breadcrumbMetadataChanged,
  breadcrumbNodeIdentityKey,
  breadcrumbNodesFromRegion,
  breadcrumbPatch,
  clearBreadcrumbNodeIdentity,
  collectBreadcrumbOptions,
  formatBreadcrumb,
  normalizeBreadcrumbNodes,
  parseBreadcrumb,
  replaceBreadcrumbNodeManually,
  regionsToExpected,
} from './PdfLabLabelingExport'
import { LeftPane } from '../common/LeftPane'
import './PdfLabLabelingPage.css'

/** Human-labeling vocabulary. Link annotations (control_link /
 *  publication_link) are machine-only — captured by extract_link_chips.py
 *  in the link_sidecar and correlated at extract time with the enclosing
 *  paragraph_block / section_label / section_heading region. They are NOT
 *  human-labeling chips. */
const CANONICAL_FAMILIES = [
  { id: 'toc',                 color: '#00d4b8', hotkey: 't' },
  { id: 'section_heading',     color: '#a8ff57', hotkey: '1' },
  { id: 'section_subtitle',    color: '#7ddc6f', hotkey: 's' },
  { id: 'section_label',       color: '#fbbc04', hotkey: '2' },
  { id: 'section_link',        color: '#38bdf8', hotkey: 'k' },
  { id: 'list',                color: '#4a9eff', hotkey: '3' },
  { id: 'paragraph_block',     color: '#94a3b8', hotkey: '4' },
  { id: 'labeled_paragraph',   color: '#ff9500', hotkey: '5' },
  { id: 'labeled_controls',    color: '#6366f1', hotkey: 'c' },
  { id: 'labeled_references',  color: '#14b8a6', hotkey: 'r' },
  { id: 'table',               color: '#22d3ee', hotkey: '6' },
  { id: 'figure',              color: '#7c3aed', hotkey: '7' },
  { id: 'caption',             color: '#ec407a', hotkey: '8' },
  { id: 'footnote',            color: '#c084fc', hotkey: '9' },
  { id: 'page_chrome_noise',   color: '#9aa0a6', hotkey: '0' },
  { id: 'human_decision',      color: '#ff6b6b', hotkey: 'q' },
] as const

type FamilyId = string
type FamilyDef = { id: FamilyId; color: string; hotkey: string }

function asExportableRegions(regions: Region[]): ExportableRegion[] {
  return regions as unknown as ExportableRegion[]
}

type LabelAnchor = 'top-outside' | 'top-inside' | 'bottom-inside' | 'bottom-outside'
type OverlayMode = 'clean' | 'compact' | 'debug'

const FAMILY_ABBREVIATIONS: Record<string, string> = {
  toc: 'TOC',
  section_heading: 'HDG',
  section_subtitle: 'SUB',
  section_label: 'LBL',
  section_link: 'LNK',
  list: 'LST',
  paragraph_block: 'TXT',
  labeled_paragraph: 'LP',
  labeled_controls: 'CTL',
  labeled_references: 'REF',
  table: 'TBL',
  figure: 'FIG',
  caption: 'CAP',
  footnote: 'FNT',
  page_chrome_noise: 'CHR',
  human_decision: 'DEC',
}

const CUSTOM_FAMILY_COLOR = '#d6bcfa'
const CUSTOM_FAMILIES_STORAGE_KEY = 'pdf-lab-labeling-custom-families'
const FALLBACK_FAMILY_AFTER_CUSTOM_DELETE: FamilyId = 'labeled_paragraph'

function persistCustomFamilyIds(ids: string[]): void {
  window.localStorage.setItem(CUSTOM_FAMILIES_STORAGE_KEY, JSON.stringify(ids))
}

function loadCustomFamilyIds(): string[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(CUSTOM_FAMILIES_STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return [...new Set(parsed.map(value => normalizeFamilyId(String(value))).filter(Boolean))]
  } catch {
    return []
  }
}

function normalizeFamilyId(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9_:-]+/g, '_').replace(/^_+|_+$/g, '')
}

interface Region {
  /** Stable client-side id (not persisted directly). */
  id: string
  family: FamilyId
  /** Normalized image coords. Always x0<x1, y0<y1, all in [0,1]. */
  bbox: [number, number, number, number]
  /** Optional, mirror expected_elements.json fields. */
  label?: string
  text_hint?: string
  lead_label?: string
  breadcrumb?: string[]
  breadcrumb_nodes?: BreadcrumbNode[]
  notes?: string
  semantic_role?: string
  target_page?: number
  dot_leader?: boolean
  toc_title?: string
  toc_entries?: TocEntry[]
  extraction?: RegionExtraction
  /** Where the family tag sits relative to the bbox. Click the tag to
   *  cycle through the four anchored positions. Default `top-outside` =
   *  just above the bbox's top-left, the conventional CVAT / VIA position. */
  labelAnchor?: LabelAnchor
  /** Where the region came from. 'human' = labeler drew it; agent origins
   *  are pre-computed candidates the labeler verifies / corrects.
   *  `'agent_link_sweep'` = emitted by `extract_link_chips.py` via the PDF
   *  /Dest annotations; `'agent_dispatcher'` = emitted by the canary
   *  dispatcher (future). */
  origin?: 'human' | 'agent_link_sweep' | 'agent_dispatcher'
  /** Agent-origin metadata: where the link points (for control_link /
   *  publication_link chips). Used by the labeler to verify the link's
   *  canonical target is correct. */
  agentMeta?: {
    destPage?: number | null
    destYNorm?: number | null
    actionUrl?: string | null
  }
}

interface RegionExtraction {
  source?: string
  source_id?: string
  bbox?: [number, number, number, number]
  text?: string
  table_json?: {
    row_count?: number
    col_count?: number
    semantic_type?: string
    rows?: Array<Array<string | Record<string, unknown>>>
  }
}

const LABEL_ANCHOR_CYCLE: LabelAnchor[] = [
  'top-outside', 'top-inside', 'bottom-inside', 'bottom-outside',
]
function nextAnchor(a: LabelAnchor | undefined): LabelAnchor {
  const idx = LABEL_ANCHOR_CYCLE.indexOf(a ?? 'top-outside')
  return LABEL_ANCHOR_CYCLE[(idx + 1) % LABEL_ANCHOR_CYCLE.length]
}

function newId(): string {
  return `r_${Math.random().toString(36).slice(2, 10)}`
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v))
}

function normalizeRect(x0: number, y0: number, x1: number, y1: number): [number, number, number, number] {
  const a = Math.min(x0, x1), b = Math.max(x0, x1)
  const c = Math.min(y0, y1), d = Math.max(y0, y1)
  return [clamp01(a), clamp01(c), clamp01(b), clamp01(d)]
}

function normalizedRegionText(value: string | undefined): string {
  return (value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function hasBreadcrumbPath(region: Region): boolean {
  return (region.breadcrumb_nodes?.length ?? 0) > 0 || (region.breadcrumb?.length ?? 0) > 0
}

const HIERARCHY_UNRESOLVED_NOTE = 'Hierarchy unresolved: no TOC-backed page breadcrumb source was available when this region was labeled.'
const EXTRACTION_CAPABLE_FAMILIES = new Set(['table', 'list', 'figure', 'equation'])

function hierarchyPathText(region: Region | null): string {
  if (!region) return '(none selected)'
  const structured = breadcrumbNodesFromRegion(region).map(node => node.label).filter(Boolean)
  if (structured.length > 0) return formatBreadcrumb(structured)
  if (region.breadcrumb?.length) return region.breadcrumb.join(' › ')
  return '(missing hierarchy)'
}

function bboxDistance(a: Region, b: Region): number {
  return a.bbox.reduce((sum, value, index) => sum + Math.abs(value - b.bbox[index]), 0)
}

function sameRegionIdentity(a: Region, b: Region): boolean {
  if (a.family !== b.family) return false
  const aText = normalizedRegionText(a.text_hint)
  const bText = normalizedRegionText(b.text_hint)
  const textMatches = aText.length > 0 && bText.length > 0 && aText === bText
  return textMatches || bboxDistance(a, b) <= 0.01
}

function bboxIntersectionArea(a: [number, number, number, number], b: [number, number, number, number]): number {
  const width = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]))
  const height = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]))
  return width * height
}

function bboxArea(bbox: [number, number, number, number]): number {
  return Math.max(0, bbox[2] - bbox[0]) * Math.max(0, bbox[3] - bbox[1])
}

function extractionMatchScore(region: Region, source: Region): number {
  if (region.family !== source.family) return 0
  const overlap = bboxIntersectionArea(region.bbox, source.bbox)
  const smaller = Math.min(bboxArea(region.bbox), bboxArea(source.bbox))
  if (smaller <= 0) return 0
  return overlap / smaller
}

function tableJsonFromBlock(block: Record<string, unknown>): RegionExtraction['table_json'] {
  const raw = (block.raw && typeof block.raw === 'object') ? block.raw as Record<string, unknown> : {}
  const rawRows = Array.isArray(raw.rows) ? raw.rows as Array<Array<Record<string, unknown>>> : []
  if (rawRows.length > 0) {
    return {
      row_count: Number(raw.row_count) || rawRows.length || undefined,
      col_count: Number(raw.col_count) || Math.max(0, ...rawRows.map(row => Array.isArray(row) ? row.length : 0)) || undefined,
      semantic_type: typeof raw.semantic_type === 'string' ? raw.semantic_type : undefined,
      rows: rawRows,
    }
  }
  const text = String(block.text ?? '')
  const rows = text.split('\n')
    .map(line => line.split('|').map(cell => cell.trim()).filter(Boolean))
    .filter(row => row.length > 0)
  return {
    row_count: Number(raw.row_count) || rows.length || undefined,
    col_count: Number(raw.col_count) || Math.max(0, ...rows.map(row => row.length)) || undefined,
    semantic_type: typeof raw.semantic_type === 'string' ? raw.semantic_type : undefined,
    rows: rows.length > 0 ? rows : undefined,
  }
}

function releaseExtractionUrlFromExpected(expectedElementsUrl: string | null | undefined): string | null {
  if (!expectedElementsUrl) return null
  const slash = expectedElementsUrl.lastIndexOf('/')
  if (slash < 0) return 'release_extraction_blocks.json'
  return `${expectedElementsUrl.slice(0, slash + 1)}release_extraction_blocks.json`
}

async function fetchExtractionSourceRegions(expectedElementsUrl: string | null | undefined): Promise<Region[]> {
  const url = releaseExtractionUrlFromExpected(expectedElementsUrl)
  if (!url) return []
  try {
    const resp = await fetch(url)
    if (!resp.ok) return []
    const payload = await resp.json() as { blocks?: Array<Record<string, unknown>> }
    const regions: Region[] = []
    for (const block of payload.blocks ?? []) {
      const family = String(block.type ?? block.source_type ?? '')
      if (family !== 'table' && family !== 'figure') continue
      const bbox = block.bbox
      if (!Array.isArray(bbox) || bbox.length !== 4) continue
      regions.push({
        id: newId(),
        family: family as FamilyId,
        bbox: normalizeRect(Number(bbox[0]), Number(bbox[1]), Number(bbox[2]), Number(bbox[3])),
        label: String(block.id ?? family),
        text_hint: String(block.text ?? ''),
        extraction: {
          source: String(block.source ?? 'release_extraction_blocks'),
          source_id: String(block.id ?? ''),
          bbox: normalizeRect(Number(bbox[0]), Number(bbox[1]), Number(bbox[2]), Number(bbox[3])),
          text: String(block.text ?? ''),
          table_json: family === 'table' ? tableJsonFromBlock(block) : undefined,
        },
      })
    }
    return regions
  } catch {
    return []
  }
}

function backfillMissingExtractionPayloads(regions: Region[], source: Region[]): Region[] {
  if (source.length === 0) return regions
  return regions.map(region => {
    if (region.extraction) return region
    let best: Region | null = null
    let bestScore = 0
    for (const candidate of source) {
      const score = extractionMatchScore(region, candidate)
      if (score > bestScore) {
        best = candidate
        bestScore = score
      }
    }
    if (!best || bestScore < 0.5 || !best.extraction) return region
    return { ...region, extraction: best.extraction }
  })
}

function overlayLabelForRegion(region: Region, overlayMode: OverlayMode): string {
  if (region.semantic_role === 'toc' || region.family === 'toc') {
    return `TOC (${region.toc_entries?.length ?? 0})`
  }
  if (region.semantic_role === 'toc_entry') {
    return typeof region.target_page === 'number' ? `TOC→p.${region.target_page}` : 'TOC'
  }
  if (region.semantic_role === 'toc_heading') return 'TOC HEAD'
  if (overlayMode === 'debug') {
    return `${region.family}${region.label ? ` · ${region.label.slice(0, 24)}` : ''}`
  }
  return FAMILY_ABBREVIATIONS[region.family]
}

function flattenTocEntries(entries: TocEntry[] | undefined): TocEntry[] {
  if (!entries) return []
  const rows: TocEntry[] = []
  for (const entry of entries) {
    rows.push(entry)
    rows.push(...flattenTocEntries(entry.children))
  }
  return rows
}

function formatTocJson(entries: TocEntry[] | undefined): string {
  return JSON.stringify(entries ?? [], null, 2)
}

function isPageChromeRegion(region: Region): boolean {
  const text = normalizedRegionText(region.text_hint || region.label)
  const [x0, y0, , y1] = region.bbox
  if (y1 <= 0.08 || y0 >= 0.92) return true
  if (
    x0 <= 0.04 &&
    (
      text.includes('this publication is available free of charge') ||
      text.includes('doi.org/10.6028/nist.sp.800') ||
      text === '-53r5'
    )
  ) return true
  return false
}

function isSideChromeRegion(region: Region): boolean {
  const text = normalizedRegionText(region.text_hint || region.label)
  const [, , x1] = region.bbox
  return (
    x1 <= 0.36 &&
    (
      text.includes('this publication is available free of charge') ||
      text.includes('doi.org/10.6028/nist.sp.800') ||
      text === '-53r5'
    )
  )
}

function sideChromeBand(region: Region): Region['bbox'] {
  void region
  return [0.017, 0.072, 0.088, 0.916]
}

function isListRegion(region: Region): boolean {
  const text = region.text_hint || region.label || ''
  return /^\s*(?:\(\d+[a-z]?\)|[a-z]\.)\s+/i.test(text)
}

function isNumberedListRegion(region: Region): boolean {
  const text = region.text_hint || region.label || ''
  return /^\s*\(\d+[a-z]?\)\s+/i.test(text)
}

function isAlphaListRegion(region: Region): boolean {
  const text = region.text_hint || region.label || ''
  return /^\s*[a-z]\.\s+/i.test(text)
}

function isListSectionBoundary(region: Region): boolean {
  const text = normalizedRegionText(region.text_hint || region.label)
  return (
    region.family === 'section_heading' ||
    region.family === 'labeled_references' ||
    text.startsWith('references:') ||
    /^[a-z]{2}-\d+\s+/.test(text)
  )
}

function mergeRegionBbox(a: Region['bbox'], b: Region['bbox']): Region['bbox'] {
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])]
}

function sameChromeCluster(a: Region, b: Region): boolean {
  const [ax0, ay0, ax1, ay1] = a.bbox
  const [bx0, by0, bx1, by1] = b.bbox
  const xOverlap = Math.max(0, Math.min(ax1, bx1) - Math.max(ax0, bx0))
  const minWidth = Math.max(0.0001, Math.min(ax1 - ax0, bx1 - bx0))
  const verticallyAdjacent = Math.abs(by0 - ay1) <= 0.01 || Math.abs(ay0 - by1) <= 0.01
  const sameTopBand = ay1 <= 0.08 && by1 <= 0.08 && xOverlap / minWidth >= 0.55 && verticallyAdjacent
  const sameBottomBand = ay0 >= 0.92 && by0 >= 0.92 && xOverlap / minWidth >= 0.55 && verticallyAdjacent
  const sameLeftSide = ax1 <= 0.36 && bx1 <= 0.36
  return sameTopBand || sameBottomBand || sameLeftSide
}

function canonicalizeHumanRegions(regions: Region[]): Region[] {
  const normalized = regions.map(region => {
    if (isPageChromeRegion(region)) {
      return {
        ...region,
        family: 'page_chrome_noise' as const,
        bbox: isSideChromeRegion(region) ? sideChromeBand(region) : region.bbox,
      }
    }
    if (isListRegion(region)) return { ...region, family: 'list' as const }
    return region
  })
  const grouped: Region[] = []
  let index = 0
  while (index < normalized.length) {
    const region = normalized[index]
    if (!isNumberedListRegion(region)) {
      grouped.push(region)
      index += 1
      continue
    }
    let group = { ...region }
    let consumedAny = false
    index += 1
    while (index < normalized.length) {
      const candidate = normalized[index]
      if (candidate.family === 'page_chrome_noise') break
      if (isAlphaListRegion(candidate)) break
      if (isListSectionBoundary(candidate)) break
      const textParts = [group.text_hint, candidate.text_hint].filter((value): value is string => Boolean(value))
      group = {
        ...group,
        bbox: mergeRegionBbox(group.bbox, candidate.bbox),
        text_hint: textParts.length > 0 ? Array.from(new Set(textParts)).join('\n') : group.text_hint,
      }
      consumedAny = true
      index += 1
    }
    grouped.push(consumedAny ? group : region)
  }
  const output: Region[] = []
  for (const region of grouped) {
    if (region.family !== 'page_chrome_noise') {
      output.push(region)
      continue
    }
    const matchIndex = output.findIndex(existing => existing.family === 'page_chrome_noise' && sameChromeCluster(existing, region))
    if (matchIndex < 0) {
      output.push(region)
      continue
    }
    const existing = output[matchIndex]
    const textParts = [existing.text_hint, region.text_hint].filter((value): value is string => Boolean(value))
    output[matchIndex] = {
      ...existing,
      bbox: mergeRegionBbox(existing.bbox, region.bbox),
      text_hint: textParts.length > 0 ? Array.from(new Set(textParts)).join('\n') : existing.text_hint,
    }
  }
  return output
}

function backfillMissingBreadcrumbPaths(regions: Region[], source: Region[]): Region[] {
  const canonicalRegions = canonicalizeHumanRegions(regions)
  if (canonicalRegions.length === 0) return canonicalRegions
  if (source.length === 0) return canonicalRegions.map(withHierarchyUnresolvedNote)
  const used = new Set<number>()
  return canonicalRegions.map((region, index) => {
    if (hasBreadcrumbPath(region)) return region

    let sourceIndex = source.findIndex((candidate, candidateIndex) =>
      !used.has(candidateIndex) && hasBreadcrumbPath(candidate) && sameRegionIdentity(region, candidate),
    )
    if (
      sourceIndex < 0 &&
      canonicalRegions.length === source.length &&
      hasBreadcrumbPath(source[index]) &&
      source[index].family === region.family
    ) {
      sourceIndex = index
    }
    if (sourceIndex < 0) {
      sourceIndex = findNearestBreadcrumbSourceIndex(region, source)
    }
    if (sourceIndex < 0) return withHierarchyUnresolvedNote(region)

    used.add(sourceIndex)
    const sourceRegion = source[sourceIndex]
    return {
      ...region,
      breadcrumb: sourceRegion.breadcrumb ? [...sourceRegion.breadcrumb] : region.breadcrumb,
      breadcrumb_nodes: sourceRegion.breadcrumb_nodes
        ? sourceRegion.breadcrumb_nodes.map(node => ({ ...node }))
        : region.breadcrumb_nodes,
    }
  })
}

function regionCenter(region: Region): { x: number; y: number } {
  return {
    x: (region.bbox[0] + region.bbox[2]) / 2,
    y: (region.bbox[1] + region.bbox[3]) / 2,
  }
}

function findNearestBreadcrumbSourceIndex(region: Region, source: Region[]): number {
  const regionMid = regionCenter(region)
  const candidates = source
    .map((candidate, index) => ({ candidate, index, center: regionCenter(candidate) }))
    .filter(({ candidate }) => hasBreadcrumbPath(candidate) && candidate.family !== 'page_chrome_noise')
  if (candidates.length === 0) return -1

  const preceding = candidates
    .filter(({ center }) => center.y <= regionMid.y + 0.02)
    .sort((a, b) => {
      const yDelta = b.center.y - a.center.y
      return Math.abs(yDelta) > 0.001 ? yDelta : Math.abs(a.center.x - regionMid.x) - Math.abs(b.center.x - regionMid.x)
    })
  if (preceding.length > 0) return preceding[0].index

  candidates.sort((a, b) => Math.abs(a.center.y - regionMid.y) - Math.abs(b.center.y - regionMid.y))
  return candidates[0].index
}

function withHierarchyUnresolvedNote(region: Region): Region {
  if (hasBreadcrumbPath(region) || region.notes?.includes(HIERARCHY_UNRESOLVED_NOTE)) return region
  return {
    ...region,
    notes: region.notes ? `${region.notes}\n${HIERARCHY_UNRESOLVED_NOTE}` : HIERARCHY_UNRESOLVED_NOTE,
  }
}

function hydrateRegionMetadata(region: Region, breadcrumbSource: Region[], extractionSource: Region[]): Region {
  const withBreadcrumb = backfillMissingBreadcrumbPaths([region], breadcrumbSource)[0] ?? region
  if (!EXTRACTION_CAPABLE_FAMILIES.has(withBreadcrumb.family)) return withBreadcrumb
  return backfillMissingExtractionPayloads([withBreadcrumb], extractionSource)[0] ?? withBreadcrumb
}

async function fetchBreadcrumbSourceRegions(expectedElementsUrl: string | null | undefined): Promise<Region[]> {
  if (!expectedElementsUrl) return []
  try {
    const resp = await fetch(expectedElementsUrl)
    if (!resp.ok) return []
    const { regions: rs } = importJson(await resp.json())
    return rs.map(region => ({ ...region, origin: region.origin ?? 'human' }))
  } catch {
    return []
  }
}

async function fetchFallbackBreadcrumbSourceRegions(slug: string): Promise<Region[]> {
  return fetchBreadcrumbSourceRegions(`/pdf-lab-pages/${slug}.expected_elements.json`)
}

/** Best-effort importer: detects shape and returns regions. Supports
 *  - expected_elements.json (our v2 contract)
 *  - VIA project JSON (single image)
 *  - LS predictions / annotations result-list
 *  Anything unrecognised → empty result + warning.
 */
function importJson(raw: unknown): { regions: Region[]; warnings: string[]; format: string } {
  const warnings: string[] = []
  if (!raw || typeof raw !== 'object') {
    return { regions: [], warnings: ['Top-level JSON must be an object.'], format: 'unknown' }
  }
  const obj = raw as Record<string, unknown>

  // expected_elements.json — our schema.
  if (Array.isArray(obj.expected_elements)) {
    const rows: Region[] = []
    const tocPayload = obj.toc as { tree?: TocEntry[]; entry_count?: number } | undefined
    for (const el of obj.expected_elements as ExpectedElement[]) {
      if (!Array.isArray(el.bbox_hint) || el.bbox_hint.length !== 4) {
        warnings.push(`expected_elements: dropped row with bad bbox_hint`)
        continue
      }
      rows.push({
        id: newId(),
        family: el.family,
        bbox: normalizeRect(el.bbox_hint[0], el.bbox_hint[1], el.bbox_hint[2], el.bbox_hint[3]),
        label: el.label ?? undefined,
        text_hint: el.text_hint,
        lead_label: el.lead_label ?? el.desired_lead_label,
        breadcrumb: parseBreadcrumb(el.breadcrumb),
        breadcrumb_nodes: normalizeBreadcrumbNodes(el.breadcrumb_nodes, el.breadcrumb),
        notes: el.notes,
        semantic_role: el.semantic_role,
        target_page: el.target_page,
        dot_leader: el.dot_leader,
        toc_title: el.toc_title,
        toc_entries: el.toc_entries,
      })
    }
    if (tocPayload?.tree?.length) {
      const tocRows = rows.filter(row => row.semantic_role === 'toc_entry')
      const heading = rows.find(row => row.semantic_role === 'toc_heading')
      if (tocRows.length >= 3) {
        const x0 = Math.min(...tocRows.map(row => row.bbox[0]))
        const y0 = Math.min(heading?.bbox[1] ?? 1, ...tocRows.map(row => row.bbox[1]))
        const x1 = Math.max(...tocRows.map(row => row.bbox[2]))
        const y1 = Math.max(...tocRows.map(row => row.bbox[3]))
        rows.unshift({
          id: newId(),
          family: 'toc',
          bbox: normalizeRect(x0, y0, x1, y1),
          label: 'Table of Contents',
          text_hint: `Nested TOC with ${tocPayload.entry_count ?? flattenTocEntries(tocPayload.tree).length} entries`,
          notes: 'Primary annotation object for the Table of Contents. Child rows remain as extraction evidence.',
          semantic_role: 'toc',
          toc_entries: tocPayload.tree,
        })
      }
    }
    return { regions: rows, warnings, format: 'expected_elements.json' }
  }

  // VIA project JSON.
  const viaImg = obj._via_img_metadata as Record<string, unknown> | undefined
  if (viaImg && typeof viaImg === 'object') {
    const entries = Object.values(viaImg)
    if (entries.length !== 1) {
      warnings.push(`VIA file has ${entries.length} images; expected 1 — using first`)
    }
    const entry = entries[0] as Record<string, unknown>
    const file_attributes = (entry.file_attributes as Record<string, unknown>) || {}
    const imgW = Number(file_attributes.page_width_px) || 0
    const imgH = Number(file_attributes.page_height_px) || 0
    if (!imgW || !imgH) {
      warnings.push('VIA file_attributes missing page_width_px/page_height_px; cannot map coords')
      return { regions: [], warnings, format: 'via (rejected)' }
    }
    const regions = (entry.regions as Array<Record<string, unknown>>) || []
    const rows: Region[] = []
    for (let i = 0; i < regions.length; i++) {
      const r = regions[i]
      const shape = (r.shape_attributes as Record<string, unknown>) || {}
      const attrs = (r.region_attributes as Record<string, unknown>) || {}
      const family = String(attrs.family || '')
      let rect: [number, number, number, number] | null = null
      if (shape.name === 'rect') {
        const x = Number(shape.x), y = Number(shape.y), w = Number(shape.width), h = Number(shape.height)
        if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(w) && Number.isFinite(h)) {
          rect = [x / imgW, y / imgH, (x + w) / imgW, (y + h) / imgH]
        }
      } else if (shape.name === 'polyline') {
        const xs = (shape.all_points_x as number[]) || []
        const ys = (shape.all_points_y as number[]) || []
        if (xs.length && ys.length && xs.length === ys.length) {
          rect = [Math.min(...xs) / imgW, Math.min(...ys) / imgH, Math.max(...xs) / imgW, Math.max(...ys) / imgH]
          warnings.push(`region#${i} polyline converted to bbox`)
        }
      }
      if (!rect) { warnings.push(`region#${i} unsupported shape: ${shape.name}`); continue }
      // Family migration: legacy chrome → page_chrome_noise + label
      let migratedFamily = family
      let migratedLabel = String(attrs.label || '')
      if (family === 'footer' || family === 'running_header') {
        migratedLabel = migratedLabel || family
        migratedFamily = 'page_chrome_noise'
      }
      if (!CANONICAL_FAMILIES.some(f => f.id === migratedFamily)) {
        warnings.push(`region#${i} family=${JSON.stringify(family)} unknown; skipped`)
        continue
      }
      rows.push({
        id: newId(),
        family: migratedFamily as FamilyId,
        bbox: normalizeRect(rect[0], rect[1], rect[2], rect[3]),
        label: migratedLabel || undefined,
        text_hint: String(attrs.text_hint || '') || undefined,
        lead_label: String(attrs.lead_label || '') || undefined,
        breadcrumb: parseBreadcrumb(attrs.breadcrumb),
        breadcrumb_nodes: normalizeBreadcrumbNodes(attrs.breadcrumb_nodes, parseBreadcrumb(attrs.breadcrumb)),
        notes: String(attrs.notes || '') || undefined,
      })
    }
    return { regions: rows, warnings, format: 'VIA project' }
  }

  warnings.push('Unrecognised JSON shape — expected expected_elements.json or VIA project export.')
  return { regions: [], warnings, format: 'unknown' }
}

/** Convert a link-sidecar JSON (from extract_link_chips.py / pypdfium2)
 *  into agent-origin Regions ready for human verification.
 *
 *  Classification heuristic, using section_label regions already present
 *  from the expected_elements contract:
 *    - link Y center inside a section_label whose text_hint contains
 *      "Related Controls" → `control_link`
 *    - link Y center inside a section_label whose text_hint contains
 *      "References" → `publication_link`
 *    - link with a non-null action_url (true external URL) →
 *      `publication_link`
 *    - otherwise → `control_link` (most common: internal /Dest nav)
 *
 *  Each region carries `origin: 'agent_link_sweep'` and `agentMeta` so the
 *  labeler can see the dest_page / URL the link points to and verify it.
 */
function linksToRegions(
  sidecar: { links?: unknown[] } | null | undefined,
  contextRegions: Region[],
): { regions: Region[]; warnings: string[] } {
  const out: Region[] = []
  const warnings: string[] = []
  if (!sidecar || !Array.isArray(sidecar.links)) {
    warnings.push('link sidecar has no `links` array')
    return { regions: out, warnings }
  }
  // Build Y-band → family map from context regions (section_label entries).
  const relatedBands: Array<[number, number]> = []
  const referencesBands: Array<[number, number]> = []
  for (const r of contextRegions) {
    if (r.family !== 'section_label') continue
    const hint = (r.text_hint || r.label || '').toLowerCase()
    const [, y0, , y1] = r.bbox
    // Section labels in this corpus are single-line "Related Controls:" /
    // "References:" headers. Their span ends at the next section header,
    // but we don't know that here — instead extend by a generous chunk
    // below the header and hope it covers the immediate citation rows.
    // 12% of page height is enough for ~5 lines.
    const band: [number, number] = [y0, Math.min(1, y1 + 0.12)]
    if (hint.includes('related controls')) relatedBands.push(band)
    else if (hint.includes('reference')) referencesBands.push(band)
  }
  // control_link / publication_link are no longer human-labeling chips —
  // they live in the link_sidecar and are correlated to the enclosing
  // labeled_paragraph / section_heading / section_label region at extract
  // time. Skip per-link rectangle emission here so the Human view stays
  // uncluttered. The sidecar count is reported in warnings for visibility.
  if (sidecar && Array.isArray(sidecar.links)) {
    const n = sidecar.links.length
    if (n > 0) {
      warnings.push(`link_sidecar: ${n} link annotation${n === 1 ? '' : 's'} present (machine-only; not emitted as human chips)`)
    }
  } else {
    void relatedBands; void referencesBands
  }
  if (out.length === 0) {
    warnings.push('link sidecar contained 0 links')
  }
  return { regions: out, warnings }
}

interface DragState {
  startX: number; startY: number
  curX: number; curY: number
  family: FamilyId
}

interface SavedPage {
  slug: string
  imageDataUrl: string
  regions: Region[]
  updatedAt: string
  naturalSize?: { w: number; h: number }
}

const STORAGE_KEY = 'pdf-lab-labeling-pages-v1'

function loadSavedPages(): Record<string, SavedPage> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as Record<string, SavedPage>
  } catch {
    return {}
  }
}

function persistSavedPages(pages: Record<string, SavedPage>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(pages))
  } catch (err) {
    // Quota exceeded — likely too many pages with embedded images. Skip
    // silently; the in-memory state still works.
    console.warn('[PdfLabLabeling] localStorage save failed:', err)
  }
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result || ''))
    r.onerror = () => reject(r.error || new Error('FileReader error'))
    r.readAsDataURL(file)
  })
}

function urlToDataUrl(url: string): Promise<string> {
  return fetch(url)
    .then(r => r.blob())
    .then(blob => new Promise<string>((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(String(r.result || ''))
      r.onerror = () => reject(r.error || new Error('FileReader error'))
      r.readAsDataURL(blob)
    }))
}

/** Golden-slice manifest. Each entry is a self-contained project: a
 *  rendered PDF page PNG plus (optionally) an existing expected_elements.json
 *  contract. Click → image + prior regions both load. This is the project
 *  explorer's source of truth; localStorage tracks per-slug edits on top.
 *
 *  To add a slice:
 *    1. Drop the page PNG into `public/pdf-lab-pages/<slug>_page.png`
 *    2. (optional) Drop the contract at
 *       `public/pdf-lab-pages/<slug>.expected_elements.json`
 *    3. Append an entry here.
 */
interface KnownSlice {
  slug: string
  label: string
  imageUrl: string
  expectedElementsUrl?: string
  /** Agent-detected hyperlink candidates from the canary pipeline
   *  (extract_link_chips.py via pypdfium2 /Dest annotations). Each link
   *  becomes a pre-tagged region the human verifies / corrects. */
  linkSidecarUrl?: string
}

/** A multi-page Project — the agent's candidate queue for collaborative
 *  human-in-the-loop labeling. Each project is generated by an agent run
 *  (e.g., the phase-04-7 corpus canary) and surfaces N pending pages.
 *  The human signs off on each page; signed-off regions become fixture
 *  candidates for the NIST ledger + pdf_oxide regression suite. */
interface ProjectPage {
  slug: string
  label: string
  anchor_page: number
  control_id_declared?: string | null
  stratum?: string | null
  image_url: string
  link_sidecar_url?: string | null
  expected_elements_url?: string | null
  /** scillm second-pass refined classification (LLM-pass result), surfaced
   *  under the "Agent" view-mode. Distinct from expected_elements_url,
   *  which is the deterministic Original view. */
  second_pass_url?: string | null
  status: 'pending' | 'in_review' | 'agreed' | 'rejected'
  agent_origin?: string
  agreed_at?: string | null
  agreed_by?: string | null
  agreed_regions_url?: string | null
  notes?: string | null
}
interface Project {
  schema_version: string
  project_id: string
  name: string
  source?: string
  description?: string
  generated_at?: string
  generated_by?: string
  pages: ProjectPage[]
}
interface ProjectIndexEntry {
  project_id: string
  name: string
  url: string
  page_count: number
}
interface AgentSecondPassSummary {
  status?: string
  human_review_required?: boolean
  fix_error_request_count?: number
  captured_at?: string
}

type ProjectPageQueueState = 'human_signed_off' | 'second_pass_resolved' | 'human_needed' | 'in_review' | 'pending'

interface OnePageCandidateGuidance {
  expectedRegionCount: number
  priority: number
  reason: string
  scope: string
}

const ONE_PAGE_CANDIDATE_GUIDANCE: Record<number, OnePageCandidateGuidance> = {
  45: {
    expectedRegionCount: 25,
    priority: 100,
    reason: 'Manageable high-density control page: lists, control/reference labeled regions, headings, body text, and page chrome.',
    scope: 'Control-page list and semantic ownership extraction',
  },
  35: {
    expectedRegionCount: 23,
    priority: 85,
    reason: 'Dense fundamentals page with caption/table-adjacent structure and many paragraph regions.',
    scope: 'Table-adjacent caption and paragraph grouping',
  },
  455: {
    expectedRegionCount: 18,
    priority: 75,
    reason: 'Appendix C summary page with list structure and control semantics, smaller than page 45.',
    scope: 'Appendix list and summary ownership',
  },
  401: {
    expectedRegionCount: 31,
    priority: 45,
    reason: 'References page is valuable but too broad for the first one-page restart.',
    scope: 'References block segmentation',
  },
}

const RECENTLY_PROVEN_ANCHOR_PAGES = new Set([28])

function agentSecondPassSummary(raw: unknown): AgentSecondPassSummary | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const decision = obj.agent_decision
  if (!decision || typeof decision !== 'object') return null
  const d = decision as Record<string, unknown>
  return {
    status: typeof d.status === 'string' ? d.status : undefined,
    human_review_required: typeof d.human_review_required === 'boolean' ? d.human_review_required : undefined,
    fix_error_request_count: typeof d.fix_error_request_count === 'number' ? d.fix_error_request_count : undefined,
    captured_at: typeof obj.captured_at === 'string' ? obj.captured_at : undefined,
  }
}

function queueStateForPage(
  page: ProjectPage,
  signoff: PageSignoff | undefined,
  secondPass: AgentSecondPassSummary | undefined,
): ProjectPageQueueState {
  if (page.status === 'agreed' || signoff) return 'human_signed_off'
  if (secondPass?.human_review_required || (secondPass?.fix_error_request_count ?? 0) > 0) return 'human_needed'
  if (secondPass?.status === 'closure_rematerialized') return 'second_pass_resolved'
  if (page.status === 'in_review') return 'in_review'
  return 'pending'
}

function queueStateLabel(state: ProjectPageQueueState): string {
  switch (state) {
    case 'human_signed_off': return 'agreed'
    case 'second_pass_resolved': return '2nd pass'
    case 'human_needed': return 'human'
    case 'in_review': return 'review'
    case 'pending': return 'pending'
  }
}

function queueStateLongLabel(state: ProjectPageQueueState): string {
  switch (state) {
    case 'human_signed_off': return 'human signed off'
    case 'second_pass_resolved': return 'second-pass rematerialized; no fix requests'
    case 'human_needed': return 'human review required'
    case 'in_review': return 'in review'
    case 'pending': return 'pending'
  }
}

function recommendedOnePageCandidate(
  projects: Project[],
  signoffs: Record<string, PageSignoff>,
): { project: Project; page: ProjectPage; guidance: OnePageCandidateGuidance } | null {
  const candidates: Array<{ project: Project; page: ProjectPage; guidance: OnePageCandidateGuidance }> = []
  for (const project of projects) {
    for (const page of project.pages) {
      if (RECENTLY_PROVEN_ANCHOR_PAGES.has(page.anchor_page)) continue
      if (page.status === 'agreed' || signoffs[signoffKey(project.project_id, page.slug)]) continue
      const guidance = ONE_PAGE_CANDIDATE_GUIDANCE[page.anchor_page]
      if (!guidance) continue
      candidates.push({ project, page, guidance })
    }
  }
  candidates.sort((a, b) => b.guidance.priority - a.guidance.priority)
  return candidates[0] ?? null
}

function familyCountsFor(regions: Region[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const region of regions) {
    counts[region.family] = (counts[region.family] ?? 0) + 1
  }
  return counts
}

function isInProgressCompatibleWithSource(regions: Region[], sourceRegions: Region[]): boolean {
  const sourceCounts = familyCountsFor(sourceRegions)
  const snapshotCounts = familyCountsFor(regions)
  for (const [family, sourceCount] of Object.entries(sourceCounts)) {
    if (sourceCount >= 10 && (snapshotCounts[family] ?? 0) < Math.ceil(sourceCount * 0.5)) {
      return false
    }
  }
  return true
}

/** Per-page sign-off snapshot persisted in localStorage. The agreed
 *  regions become the human-blessed fixture for this page; the verdict
 *  and diff drive the downstream pdf_oxide PR or NIST ledger entry. */
type ProposedOwner = 'pdf_oxide_core' | 'nist_preset' | 'unclassified' | 'mixed'
interface RegionDiff {
  kind: 'added' | 'removed' | 'bbox_edited' | 'family_relabeled' | 'metadata_edited'
  region_id: string
  agent_initial?: Region
  human_final?: Region
  proposed_owner: ProposedOwner
  proposed_owner_reason: string
}
interface PageSignoff {
  project_id: string
  page_slug: string
  agreed_at: string
  agreed_by: string
  agreed_regions: Region[]
  /** Regions as the agent emitted them at page-load (deep copy, used
   *  as the diff baseline for the verdict). */
  regions_initial: Region[]
  /** Verdict: `confirmed` = no edits → positive regression fixture;
   *  `amended` = edits → bug spec drives a PR. */
  verdict: 'confirmed' | 'amended'
  diff: RegionDiff[]
  /** Where the amendment should land. Computed from the per-region
   *  proposed_owner distribution. */
  proposed_owner: ProposedOwner
}

interface PageIssueItem {
  id: string
  title: string
  owner: ProposedOwner
  rationale: string
  evidence_region_ids: string[]
}

interface PageIssueDraft {
  schema: 'pdf_oxide.github_page_issue_draft.v1'
  title: string
  labels: string[]
  body: string
  issue_items: PageIssueItem[]
  raw_diff_count: number
}

/** Diff-classification heuristics. These are first-cut rules; the
 *  signoff record stores both the verdict and the per-region rationale
 *  so a downstream agent can refine the owner-assignment. */
function classifyRegionDiff(
  agentRegion: Region | undefined,
  humanRegion: Region | undefined,
): RegionDiff | null {
  if (!agentRegion && !humanRegion) return null
  if (agentRegion && !humanRegion) {
    return {
      kind: 'removed',
      region_id: agentRegion.id,
      agent_initial: agentRegion,
      proposed_owner: agentRegion.origin === 'agent_link_sweep' ? 'pdf_oxide_core' : 'nist_preset',
      proposed_owner_reason: agentRegion.origin === 'agent_link_sweep'
        ? 'Human removed an agent-emitted control_link/publication_link — likely a false-positive in PDF /Dest enumeration (pdf_oxide_core bug) or a misclassified link (nist_preset)'
        : 'Human removed an agent region — likely a wrong classification rule in the NIST ledger',
    }
  }
  if (!agentRegion && humanRegion) {
    return {
      kind: 'added',
      region_id: humanRegion.id,
      human_final: humanRegion,
      proposed_owner: 'unclassified',
      proposed_owner_reason: 'Human added a region with no agent counterpart — pdf_oxide_core missed extraction OR NIST ledger missed a classification rule. Inspect text/bbox to decide.',
    }
  }
  if (!agentRegion || !humanRegion) return null
  // Bbox edited?
  const bboxChanged = agentRegion.bbox.some((v, i) => Math.abs(v - humanRegion.bbox[i]) > 0.002)
  // Family relabeled?
  const familyChanged = agentRegion.family !== humanRegion.family
  // Metadata edited (label, text_hint, lead_label, breadcrumb hierarchy, notes)?
  const metaChanged =
    (agentRegion.label ?? '') !== (humanRegion.label ?? '') ||
    (agentRegion.text_hint ?? '') !== (humanRegion.text_hint ?? '') ||
    (agentRegion.lead_label ?? '') !== (humanRegion.lead_label ?? '') ||
    breadcrumbMetadataChanged(agentRegion, humanRegion) ||
    (agentRegion.notes ?? '') !== (humanRegion.notes ?? '')
  if (familyChanged) {
    return {
      kind: 'family_relabeled',
      region_id: humanRegion.id,
      agent_initial: agentRegion,
      human_final: humanRegion,
      proposed_owner: 'nist_preset',
      proposed_owner_reason: `Family changed from ${agentRegion.family} → ${humanRegion.family}. NIST ledger classifier rule (text_classifier_rule / block_type_map) needs updating.`,
    }
  }
  if (bboxChanged) {
    return {
      kind: 'bbox_edited',
      region_id: humanRegion.id,
      agent_initial: agentRegion,
      human_final: humanRegion,
      proposed_owner: 'pdf_oxide_core',
      proposed_owner_reason: 'Human edited the bbox — pdf_oxide emitted geometry the human disagrees with (e.g., multi-row Body collapse, span-level bbox missing, link rect too tight/loose).',
    }
  }
  if (metaChanged) {
    return {
      kind: 'metadata_edited',
      region_id: humanRegion.id,
      agent_initial: agentRegion,
      human_final: humanRegion,
      proposed_owner: 'nist_preset',
      proposed_owner_reason: 'Human edited label / text_hint / lead_label / breadcrumb hierarchy / notes — NIST ledger field-enrichment rule needs updating.',
    }
  }
  return null  // identical → no diff entry
}

function computeVerdict(
  initial: Region[],
  final: Region[],
): { verdict: 'confirmed' | 'amended'; diff: RegionDiff[]; proposed_owner: ProposedOwner } {
  const initialById = new Map(initial.map(r => [r.id, r]))
  const finalById = new Map(final.map(r => [r.id, r]))
  const allIds = new Set<string>([...initialById.keys(), ...finalById.keys()])
  const diff: RegionDiff[] = []
  for (const id of allIds) {
    const d = classifyRegionDiff(initialById.get(id), finalById.get(id))
    if (d) diff.push(d)
  }
  if (diff.length === 0) {
    return { verdict: 'confirmed', diff: [], proposed_owner: 'unclassified' }
  }
  // Aggregate proposed_owner: if all diffs point to one owner, use it; else 'mixed'.
  const owners = new Set(diff.map(d => d.proposed_owner))
  let owner: ProposedOwner = 'unclassified'
  if (owners.size === 1) {
    owner = diff[0].proposed_owner
  } else if (owners.size > 1) {
    owner = 'mixed'
  }
  return { verdict: 'amended', diff, proposed_owner: owner }
}

function regionLabel(region: Region | undefined): string {
  return region?.label || region?.text_hint || region?.family || region?.id || 'region'
}

function buildPageIssueDraft(
  page: ProjectPage,
  project: Project | null | undefined,
  verdict: { verdict: 'confirmed' | 'amended'; diff: RegionDiff[]; proposed_owner: ProposedOwner },
  finalRegions: Region[],
): PageIssueDraft | null {
  if (verdict.diff.length === 0) return null
  const issues: PageIssueItem[] = []
  const byId = new Map(finalRegions.map(region => [region.id, region]))
  const metadataChanged = verdict.diff.filter(diff => diff.kind === 'metadata_edited')
  const removed = verdict.diff.filter(diff => diff.kind === 'removed')
  const mergedList = finalRegions.find(region => region.family === 'list' && /merged|nested|control/i.test(`${region.id} ${region.label ?? ''}`))
  const controlEnhancements = finalRegions.find(region => /control enhancements/i.test(`${region.label ?? ''} ${region.lead_label ?? ''} ${region.text_hint ?? ''}`))
  const sectionLink = finalRegions.find(region => region.family === 'section_link')
  const controlHeading = finalRegions.find(region => /AC-1.*POLICY AND PROCEDURES/i.test(`${region.label ?? ''} ${region.text_hint ?? ''}`))
  const missingToc = finalRegions.filter(region => breadcrumbNodesFromRegion(region).length === 0)
  const chrome = finalRegions.filter(region => region.family === 'page_chrome_noise')

  if (mergedList || removed.length > 0) {
    issues.push({
      id: 'page45-list-oversegmentation',
      title: 'AC-1 control list is over-segmented; nested list items should be one list region',
      owner: 'pdf_oxide_core',
      rationale: 'The human correction preserves the AC-1 a/b/c + 1/2 + (a)/(b) content as one semantic list block. Raw removed-region diffs are evidence of over-segmentation, not separate bugs.',
      evidence_region_ids: [mergedList?.id, ...removed.slice(0, 8).map(diff => diff.region_id)].filter(Boolean) as string[],
    })
  }
  if (controlEnhancements) {
    issues.push({
      id: 'page45-control-enhancements-label',
      title: 'Control Enhancements needs a NIST-specific semantic label, not generic labeled_paragraph',
      owner: 'nist_preset',
      rationale: `Region ${controlEnhancements.id} is a named NIST control field. It should be represented as labeled_enhancements or equivalent NIST preset semantics so "None." and enhancement sections are distinguishable from ordinary prose.`,
      evidence_region_ids: [controlEnhancements.id],
    })
  }
  if (sectionLink) {
    issues.push({
      id: 'page45-section-link-label',
      title: 'Visible quick-link text should be classified as section_link',
      owner: 'nist_preset',
      rationale: 'The human-labeled page distinguishes the visible in-document navigation link from section headings and prose. The NIST preset should preserve that semantic label.',
      evidence_region_ids: [sectionLink.id],
    })
  }
  if (controlHeading) {
    issues.push({
      id: 'page45-control-heading-merge',
      title: 'AC-1 control ID and title should be one control heading',
      owner: 'nist_preset',
      rationale: 'The visible heading reads "AC-1 POLICY AND PROCEDURES"; splitting AC-1 from the title creates duplicate/incorrect structure.',
      evidence_region_ids: [controlHeading.id],
    })
  }
  if (missingToc.length > 0 || metadataChanged.some(diff => breadcrumbMetadataChanged(diff.agent_initial ?? ({} as Region), diff.human_final ?? ({} as Region)))) {
    issues.push({
      id: 'page45-toc-lineage',
      title: 'All page elements need TOC lineage',
      owner: 'nist_preset',
      rationale: 'Each region on this page should carry CHAPTER THREE THE CONTROLS -> 3.1 ACCESS CONTROL so downstream fixtures know the document section, not just the local bbox label.',
      evidence_region_ids: missingToc.map(region => region.id),
    })
  } else if (finalRegions.some(region => breadcrumbNodesFromRegion(region).length > 0)) {
    issues.push({
      id: 'page45-toc-lineage',
      title: 'TOC lineage must be preserved for every corrected region',
      owner: 'nist_preset',
      rationale: 'The corrected annotation carries CHAPTER THREE THE CONTROLS -> 3.1 ACCESS CONTROL on the page regions. The preset/export path should preserve that lineage so future extraction can attach elements to their TOC section.',
      evidence_region_ids: finalRegions.map(region => region.id),
    })
  }
  if (chrome.length > 0) {
    issues.push({
      id: 'page45-page-chrome-separation',
      title: 'Running header, sidebar DOI text, and footer must remain page_chrome_noise',
      owner: 'nist_preset',
      rationale: 'The human annotation separates NIST running header/sidebar/footer from body content so those strings do not pollute section text, lists, or references.',
      evidence_region_ids: chrome.map(region => region.id),
    })
  }

  const uniqueIssues = issues.filter((issue, index, all) => all.findIndex(candidate => candidate.id === issue.id) === index)
  const projectLabel = project?.project_id ?? project?.name ?? 'pdf-lab'
  const body = [
    `Page: ${page.label}`,
    `Project: ${projectLabel}`,
    `Raw amendment diffs: ${verdict.diff.length}`,
    '',
    'This issue is generated from one human-reviewed PDF Lab page. Raw human-vs-agent diffs are grouped into page-level bugs so the project agent can fix one coherent page problem at a time.',
    '',
    'Bug list:',
    ...uniqueIssues.map((issue, index) => [
      `${index + 1}. ${issue.title}`,
      `   Owner: ${issue.owner}`,
      `   Evidence regions: ${issue.evidence_region_ids.length > 0 ? issue.evidence_region_ids.join(', ') : '(page-level)'}`,
      `   Rationale: ${issue.rationale}`,
    ].join('\n')),
    '',
    'Current human region families:',
    ...finalRegions.map(region => `- ${region.id}: ${region.family} · ${regionLabel(region)}`),
  ].join('\n')
  return {
    schema: 'pdf_oxide.github_page_issue_draft.v1',
    title: `[PDF Lab] ${page.slug}: page-level annotation bugs`,
    labels: ['pdf-lab', 'page-annotation', verdict.proposed_owner],
    body,
    issue_items: uniqueIssues,
    raw_diff_count: verdict.diff.length,
  }
}

const PROJECT_SIGNOFF_STORAGE_KEY = 'pdfLab.projectSignoffs.v1'
function loadProjectSignoffs(): Record<string, PageSignoff> {
  try {
    const raw = window.localStorage.getItem(PROJECT_SIGNOFF_STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as Record<string, PageSignoff>
  } catch {
    return {}
  }
}
function persistProjectSignoffs(value: Record<string, PageSignoff>): void {
  try {
    window.localStorage.setItem(PROJECT_SIGNOFF_STORAGE_KEY, JSON.stringify(value))
  } catch {/* quota / disabled storage — ignore */}
}
function signoffKey(projectId: string, pageSlug: string): string {
  return `${projectId}::${pageSlug}`
}

function BreadcrumbEditor({
  region,
  options,
  previousNodes,
  onChange,
}: {
  region: Region
  options: BreadcrumbNode[]
  previousNodes?: BreadcrumbNode[]
  onChange: (patch: Pick<Region, 'breadcrumb' | 'breadcrumb_nodes'>) => void
}) {
  const nodes = breadcrumbNodesFromRegion(region)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const optionKey = breadcrumbNodeIdentityKey
  const optionLabel = (node: BreadcrumbNode) => {
    const identity = [node.node_id ?? node.id, Number.isFinite(node.page) ? `p${node.page}` : ''].filter(Boolean).join(' · ')
    return identity ? `${node.label} (${identity})` : node.label
  }
  const replaceNode = (index: number, patch: Partial<BreadcrumbNode>) => {
    const nextNodes = replaceBreadcrumbNodeManually(nodes, index, patch)
    onChange(breadcrumbPatch(nextNodes))
  }
  const applyOption = (index: number, value: string) => {
    if (!value) {
      onChange(breadcrumbPatch(clearBreadcrumbNodeIdentity(nodes, index)))
      return
    }
    const option = options.find(candidate => optionKey(candidate) === value)
    if (!option) return
    onChange(breadcrumbPatch(applyKnownBreadcrumbNode(nodes, index, option)))
    setQuery('')
  }
  const duplicateOptionLabels = useMemo(() => {
    const counts = new Map<string, number>()
    options.forEach(option => counts.set(option.label, (counts.get(option.label) ?? 0) + 1))
    return counts
  }, [options])
  const displayOptionLabel = (option: BreadcrumbNode) => {
    if ((duplicateOptionLabels.get(option.label) ?? 0) <= 1) return option.label
    return optionLabel(option)
  }
  const kindLabel = (kind: BreadcrumbNodeKind) => ({
    document: 'Document',
    chapter: 'Chapter',
    section: 'Section',
    subsection: 'Subsection',
    control_family: 'Control family',
    control: 'Control',
    enhancement: 'Enhancement',
    local_role: 'Local role',
    unknown: 'Unclassified hierarchy role',
  }[kind])
  const activeNode = editingIndex === null ? null : nodes[editingIndex]
  const activeIndex = editingIndex ?? -1
  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    const candidates = normalizedQuery
      ? options.filter(option =>
          option.label.toLowerCase().includes(normalizedQuery) ||
          option.kind.toLowerCase().includes(normalizedQuery) ||
          (option.node_id ?? '').toLowerCase().includes(normalizedQuery),
        )
      : options
    return candidates.slice(0, 24)
  }, [options, query])
  const addLevel = () => {
    const nextLevel = nodes.length + 1
    onChange(breadcrumbPatch([
      ...nodes,
      { level: nextLevel, kind: 'unknown', label: `level_${nextLevel}`, source: 'human' },
    ]))
    setEditingIndex(nodes.length)
    setQuery('')
  }
  const removeLevel = (index: number) => {
    onChange(breadcrumbPatch(nodes.filter((_, nodeIndex) => nodeIndex !== index)))
    setEditingIndex(null)
    setQuery('')
  }
  const usePreviousPath = () => {
    if (!previousNodes?.length) return
    onChange(breadcrumbPatch(previousNodes))
    setEditingIndex(null)
    setQuery('')
  }
  const clearPath = () => {
    onChange({ breadcrumb: undefined, breadcrumb_nodes: undefined })
    setEditingIndex(null)
    setQuery('')
  }
  const promoteActiveLevel = () => {
    if (editingIndex === null || editingIndex <= 0) return
    const nextNodes = [...nodes]
    const [node] = nextNodes.splice(editingIndex, 1)
    nextNodes.splice(editingIndex - 1, 0, node)
    onChange(breadcrumbPatch(nextNodes))
    setEditingIndex(editingIndex - 1)
  }
  const demoteActiveLevel = () => {
    if (editingIndex === null || editingIndex >= nodes.length - 1) return
    const nextNodes = [...nodes]
    const [node] = nextNodes.splice(editingIndex, 1)
    nextNodes.splice(editingIndex + 1, 0, node)
    onChange(breadcrumbPatch(nextNodes))
    setEditingIndex(editingIndex + 1)
  }

  return (
    <div
      className="pdf-lab-labeling-breadcrumb-editor"
      data-qid={`pdf-lab:labeling:breadcrumb-editor-${region.id}`}
      title="Structured hierarchy path. Reassign a wrong level or add a missing parent level."
    >
      <div className="pdf-lab-labeling-breadcrumb-editor-head">
        <span>document hierarchy path</span>
        <button
          type="button"
          data-qid={`pdf-lab:labeling:breadcrumb-add-level:${region.id}`}
          data-qs-action="PDF_LAB_BREADCRUMB_ADD_LEVEL"
          title="Add a missing TOC/outline/section hierarchy level"
          onClick={addLevel}
        >+ level</button>
      </div>
      <div className="pdf-lab-labeling-breadcrumb-help">
        Path from document root to the current section; role is metadata, not a PDF element type.
      </div>
      {nodes.length === 0 ? (
        <div className="pdf-lab-labeling-breadcrumb-empty-actions">
          <button
            type="button"
            className="pdf-lab-labeling-breadcrumb-empty"
            data-qid={`pdf-lab:labeling:breadcrumb-add-first-level:${region.id}`}
            data-qs-action="PDF_LAB_BREADCRUMB_ADD_FIRST_LEVEL"
            title="Add the first TOC/outline/section hierarchy level"
            onClick={addLevel}
          >
            Add first hierarchy path level
          </button>
          <button
            type="button"
            className="pdf-lab-labeling-breadcrumb-quick"
            disabled={!previousNodes?.length}
            data-qid={`pdf-lab:labeling:breadcrumb-use-previous-empty:${region.id}`}
            data-qs-action="PDF_LAB_BREADCRUMB_USE_PREVIOUS"
            title="Use the previous annotated element's hierarchy path"
            onClick={usePreviousPath}
          >
            Use previous path
          </button>
        </div>
      ) : (
        <>
          <div className="pdf-lab-labeling-breadcrumb-path" data-qid={`pdf-lab:labeling:breadcrumb-path:${region.id}`}>
            {nodes.map((node, index) => (
              <span className="pdf-lab-labeling-breadcrumb-chip-wrap" key={`${region.id}-breadcrumb-chip-${index}`}>
                {index > 0 && <span className="pdf-lab-labeling-breadcrumb-path-sep">›</span>}
                <button
                  type="button"
                  className={`pdf-lab-labeling-breadcrumb-chip ${editingIndex === index ? 'is-editing' : ''}`}
                  data-qid={`pdf-lab:labeling:breadcrumb-chip:${region.id}:${index + 1}`}
                  data-qs-action="PDF_LAB_BREADCRUMB_EDIT_CHIP"
                  title={`Edit hierarchy level ${index + 1}: ${node.label}`}
                  onClick={() => { setEditingIndex(index); setQuery('') }}
                >
                  <span>{node.label}</span>
                  <em>{kindLabel(node.kind)}</em>
                </button>
              </span>
            ))}
            <button
              type="button"
              className="pdf-lab-labeling-breadcrumb-add-inline"
              data-qid={`pdf-lab:labeling:breadcrumb-add-inline:${region.id}`}
              data-qs-action="PDF_LAB_BREADCRUMB_ADD_LEVEL"
              title="Add another hierarchy path level"
              onClick={addLevel}
            >
              + level
            </button>
          </div>
          {activeNode ? (
            <div className="pdf-lab-labeling-breadcrumb-popover" data-qid={`pdf-lab:labeling:breadcrumb-popover:${region.id}`}>
              <div className="pdf-lab-labeling-breadcrumb-popover-title">
                <strong>{activeNode.label}</strong>
                <span>{kindLabel(activeNode.kind)} · auto-detected from selected node</span>
              </div>
              <input
                type="search"
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder="Search or select section…"
                data-qid={`pdf-lab:labeling:breadcrumb-search:${region.id}:${activeIndex + 1}`}
                data-qs-action="PDF_LAB_BREADCRUMB_SEARCH_NODE"
                aria-label={`Search known hierarchy nodes for level ${activeIndex + 1}`}
              />
              <div className="pdf-lab-labeling-breadcrumb-options" role="listbox">
                {filteredOptions.length === 0 ? (
                  <div className="pdf-lab-labeling-breadcrumb-no-options">No matching hierarchy nodes.</div>
                ) : filteredOptions.map(option => (
                  <button
                    type="button"
                    key={`${activeIndex}-${optionKey(option)}`}
                    data-qid={`pdf-lab:labeling:breadcrumb-option:${region.id}:${activeIndex + 1}:${optionKey(option)}`}
                    data-qs-action="PDF_LAB_BREADCRUMB_SELECT_NODE"
                    title={optionLabel(option)}
                    onClick={() => editingIndex !== null && applyOption(editingIndex, optionKey(option))}
                  >
                    <span>{displayOptionLabel(option)}</span>
                    <em>{kindLabel(option.kind)}</em>
                  </button>
                ))}
              </div>
              <div className="pdf-lab-labeling-breadcrumb-actions">
                <button type="button" onClick={usePreviousPath} disabled={!previousNodes?.length}>Use previous path</button>
                <button type="button" onClick={promoteActiveLevel} disabled={editingIndex === null || editingIndex <= 0}>Promote</button>
                <button type="button" onClick={demoteActiveLevel} disabled={editingIndex === null || editingIndex >= nodes.length - 1}>Demote</button>
                <button type="button" onClick={clearPath}>Clear path</button>
              </div>
              <details
                className="pdf-lab-labeling-breadcrumb-advanced"
                open={advancedOpen}
                onToggle={event => setAdvancedOpen(event.currentTarget.open)}
              >
                <summary>Advanced</summary>
                <label>
                  Override display label
                  <input
                    type="text"
                    data-qid={`pdf-lab:labeling:breadcrumb-label:${region.id}:${activeIndex + 1}`}
                    data-qs-action="PDF_LAB_BREADCRUMB_SET_LABEL"
                    value={activeNode.label}
                    onChange={event => editingIndex !== null && replaceNode(editingIndex, { label: event.target.value })}
                  />
                </label>
                <label>
                  Override node role
                  <select
                    data-qid={`pdf-lab:labeling:breadcrumb-kind:${region.id}:${activeIndex + 1}`}
                    data-qs-action="PDF_LAB_BREADCRUMB_SET_KIND"
                    value={activeNode.kind}
                    onChange={event => editingIndex !== null && replaceNode(editingIndex, { kind: event.target.value as BreadcrumbNodeKind })}
                  >
                    {BREADCRUMB_NODE_KINDS.map(kind => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}
                  </select>
                </label>
                <div className="pdf-lab-labeling-breadcrumb-advanced-actions">
                  <button type="button" onClick={() => editingIndex !== null && onChange(breadcrumbPatch(clearBreadcrumbNodeIdentity(nodes, editingIndex)))}>
                    Detach from known hierarchy node
                  </button>
                  <button type="button" onClick={() => editingIndex !== null && removeLevel(editingIndex)}>
                    Remove level
                  </button>
                </div>
              </details>
            </div>
          ) : null}
        </>
      )}
      {nodes.length > 0 ? (
        <div className="pdf-lab-labeling-region-breadcrumb" title="Current structured breadcrumb">
          <span className="pdf-lab-labeling-region-breadcrumb-label">Preview:</span>
          {nodes.map((node, index) => (
            <span key={`${region.id}-structured-bc-${index}`}>
              {index > 0 && <span className="pdf-lab-labeling-region-breadcrumb-sep">›</span>}
              {node.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

const KNOWN_SLICES: KnownSlice[] = [
  {
    slug: 'gs001_intro_page_27',
    label: 'GS001 · Intro · printed pg 1',
    imageUrl: '/pdf-lab-pages/page_0027.png',
    expectedElementsUrl: '/pdf-lab-pages/gs001_intro_page_27.expected_elements.json',
  },
  {
    slug: 'gs002_ac1_page_44',
    label: 'AC-1 · printed pg 18',
    imageUrl: '/pdf-lab-pages/page_0044.png',
    linkSidecarUrl: '/pdf-lab-pages/link_sidecars/links_p44.json',
  },
  {
    slug: 'gs002_ac2_page_45',
    label: 'GS002 · AC-2 · printed pg 19',
    imageUrl: '/pdf-lab-pages/page_0045.png',
    expectedElementsUrl: '/pdf-lab-pages/gs002_ac2_page_45.expected_elements.json',
    linkSidecarUrl: '/pdf-lab-pages/link_sidecars/links_p45.json',
  },
]

export function PdfLabLabelingPage() {
  const [activeFamily, setActiveFamily] = useState<FamilyId>('paragraph_block')
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [imageDataUrl, setImageDataUrl] = useState<string | null>(null)
  const [imageNaturalSize, setImageNaturalSize] = useState<{ w: number; h: number } | null>(null)
  const [regions, setRegions] = useState<Region[]>([])
  const [customFamilyIds, setCustomFamilyIds] = useState<string[]>(() => loadCustomFamilyIds())
  const [customFamilyInput, setCustomFamilyInput] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const breadcrumbOptions = useMemo(() => collectBreadcrumbOptions(asExportableRegions(regions)), [regions])
  const [drag, setDrag] = useState<DragState | null>(null)
  const [slug, setSlug] = useState('manual_labeling')
  const [, setWarnings] = useState<string[]>([])
  const [savedPages, setSavedPages] = useState<Record<string, SavedPage>>(() => loadSavedPages())
  /** Agent-generated projects (multi-page candidate queues). Loaded from
   *  /pdf-lab-projects/index.json on mount. */
  const [projects, setProjects] = useState<Project[]>([])
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const didAutoLoadProjectRef = useRef(false)
  /** Per-page sign-off snapshots, keyed by `${project_id}::${page_slug}`. */
  const [projectSignoffs, setProjectSignoffs] = useState<Record<string, PageSignoff>>(() => loadProjectSignoffs())
  /** Per-page second-pass status sidecars, keyed by `${project_id}::${page_slug}`.
   *  This is intentionally separate from human signoff state: the queue needs
   *  to show what the agent rematerialized even before the human signs off. */
  const [projectSecondPass, setProjectSecondPass] = useState<Record<string, AgentSecondPassSummary>>({})
  /** Snapshot of agent-emitted regions captured at page-load. Used as the
   *  diff baseline when the human signs off — turns each sign-off into
   *  either a `confirmed` regression fixture or an `amended` bug spec. */
  const [regionsInitial, setRegionsInitial] = useState<Region[]>([])
  /** View mode for the canvas. Four modes:
   *    'original'  — pdf_oxide + ledger deterministic output (what the
   *                  primitive extractor + heuristic ledger produced)
   *    'agent'     — scillm second-pass LLM refinement (Agent enrichment)
   *    'human'     — human's edits (editable, default)
   *    'diff'      — overlay showing where agent and human disagree
   *  Only 'human' is editable. */
  const [viewMode, setViewMode] = useState<'original' | 'agent' | 'human' | 'diff'>('human')
  const [dataPaneWidth, setDataPaneWidth] = useState<number>(() => {
    const saved = Number(window.localStorage.getItem('pdf-lab-labeling-data-pane-width'))
    return Number.isFinite(saved) ? Math.max(280, Math.min(640, saved)) : 340
  })
  const [labelPalettePos, setLabelPalettePos] = useState<{ x: number; y: number }>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem('pdf-lab-labeling-label-palette-pos') ?? 'null') as { x?: number; y?: number } | null
      if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
        return {
          x: Math.max(8, Math.min(window.innerWidth - 260, Number(saved.x))),
          y: Math.max(48, Math.min(window.innerHeight - 360, Number(saved.y))),
        }
      }
    } catch {
      // Ignore corrupt localStorage; use safe default.
    }
    return { x: 260, y: 96 }
  })
  /** Regions emitted by the scillm second-pass (Agent view). Loaded from
   *  the second_pass_url sidecar at page-load time. */
  const [regionsAgent, setRegionsAgent] = useState<Region[]>([])
  const [extractionSourceRegions, setExtractionSourceRegions] = useState<Region[]>([])
  const [overlayMode, setOverlayMode] = useState<OverlayMode>('clean')
  /** Context neighbors for the focal page being annotated. The human labels
   *  ONLY the focal canvas; prev/next are rendered as read-only thumbnails
   *  alongside so the human (and the agent) can see whether structural
   *  elements span page boundaries:
   *    - does this Control Enhancements: section's list continue on the
   *      next page?
   *    - does this table at the bottom of the focal page continue?
   *    - was this Discussion block started on the previous page?
   *  Region overlays on the neighbors come from their existing Agent (or
   *  Original) sidecars — read-only — purely for visual continuity scanning. */
  type ContextNeighbor = {
    slug: string
    image_url: string
    page_index: number
    regions: Region[]  // read-only display
  }
  const [contextPrev, setContextPrev] = useState<ContextNeighbor | null>(null)
  const [contextNext, setContextNext] = useState<ContextNeighbor | null>(null)
  const [zoom, setZoom] = useState<number>(1)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; regionId?: string } | null>(null)
  // (Removed freeform label-drag state — labels are anchored to one of 4
  //  fixed corner positions; click the tag to cycle through them.)
  /** Drag-to-reorder state in the Regions panel. Holds the id of the region
   *  being dragged so we can render a drop indicator on hover targets. */
  const [reorderDragId, setReorderDragId] = useState<string | null>(null)
  const [reorderHoverId, setReorderHoverId] = useState<string | null>(null)
  /** Region move / resize drag. `mode` records which edge or corner the user
   *  grabbed; 'move' translates the whole rect. We capture the rect at
   *  mousedown so the math is a simple delta-from-start. */
  const [regionDrag, setRegionDrag] = useState<{
    regionId: string
    mode: 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
    startClientX: number
    startClientY: number
    startBbox: [number, number, number, number]
  } | null>(null)

  const canvasRef = useRef<HTMLDivElement>(null)
  const imgWrapperRef = useRef<HTMLDivElement>(null)
  const saveTimerRef = useRef<number | null>(null)

  const ZOOM_MIN = 0.25
  const ZOOM_MAX = 8
  const recommendedCandidate = useMemo(
    () => recommendedOnePageCandidate(projects, projectSignoffs),
    [projectSignoffs, projects],
  )
  const familyDefs = useMemo<FamilyDef[]>(() => {
    const byId = new Map<string, FamilyDef>()
    CANONICAL_FAMILIES.forEach(family => byId.set(family.id, family))
    customFamilyIds.forEach((id, index) => {
      if (!byId.has(id)) byId.set(id, { id, color: CUSTOM_FAMILY_COLOR, hotkey: String((index + 1) % 10) })
    })
    ;[...regions, ...regionsInitial, ...regionsAgent].forEach(region => {
      if (region.family && !byId.has(region.family)) byId.set(region.family, { id: region.family, color: CUSTOM_FAMILY_COLOR, hotkey: '·' })
    })
    return [...byId.values()]
  }, [customFamilyIds, regions, regionsAgent, regionsInitial])
  const activeFamilyDef = familyDefs.find(f => f.id === activeFamily) ?? familyDefs[0]
  const addCustomFamily = useCallback(() => {
    const id = normalizeFamilyId(customFamilyInput)
    if (!id) return
    setCustomFamilyIds(prev => {
      if (prev.includes(id) || CANONICAL_FAMILIES.some(family => family.id === id)) return prev
      const next = [...prev, id]
      persistCustomFamilyIds(next)
      return next
    })
    setActiveFamily(id)
    if (selectedId && viewMode === 'human') {
      setRegions(prev => prev.map(region => region.id === selectedId ? hydrateRegionMetadata({ ...region, family: id }, prev, extractionSourceRegions) : region))
    }
    setCustomFamilyInput('')
  }, [customFamilyInput, extractionSourceRegions, selectedId, viewMode])
  const renameCustomFamily = useCallback((oldId: string) => {
    const raw = window.prompt(`Rename custom label ${oldId}`, oldId)
    if (raw === null) return
    const nextId = normalizeFamilyId(raw)
    if (!nextId || nextId === oldId) return
    if (CANONICAL_FAMILIES.some(family => family.id === nextId)) {
      window.alert(`${nextId} is a built-in label and cannot replace a custom label.`)
      return
    }
    setCustomFamilyIds(prev => {
      if (!prev.includes(oldId) || prev.includes(nextId)) return prev
      const next = prev.map(id => id === oldId ? nextId : id)
      persistCustomFamilyIds(next)
      return next
    })
    setRegions(prev => prev.map(region => (
      region.family === oldId
        ? hydrateRegionMetadata({ ...region, family: nextId }, prev, extractionSourceRegions)
        : region
    )))
    setActiveFamily(prev => prev === oldId ? nextId : prev)
  }, [extractionSourceRegions])
  const deleteCustomFamily = useCallback((id: string) => {
    const usageCount = regions.filter(region => region.family === id).length
    const message = usageCount > 0
      ? `Delete custom label ${id}? ${usageCount} current region${usageCount === 1 ? '' : 's'} will be remapped to ${FALLBACK_FAMILY_AFTER_CUSTOM_DELETE}.`
      : `Delete unused custom label ${id}?`
    if (!window.confirm(message)) return
    setCustomFamilyIds(prev => {
      if (!prev.includes(id)) return prev
      const next = prev.filter(candidate => candidate !== id)
      persistCustomFamilyIds(next)
      return next
    })
    if (usageCount > 0) {
      setRegions(prev => prev.map(region => (
        region.family === id
          ? hydrateRegionMetadata({ ...region, family: FALLBACK_FAMILY_AFTER_CUSTOM_DELETE }, prev, extractionSourceRegions)
          : region
      )))
    }
    setActiveFamily(prev => prev === id ? FALLBACK_FAMILY_AFTER_CUSTOM_DELETE : prev)
  }, [extractionSourceRegions, regions])

  const zoomIn = useCallback(() => setZoom(z => Math.min(ZOOM_MAX, z * 1.25)), [])
  const zoomOut = useCallback(() => setZoom(z => Math.max(ZOOM_MIN, z / 1.25)), [])
  const zoomReset = useCallback(() => setZoom(1), [])
  const zoomFit = useCallback(() => {
    if (!canvasRef.current || !imageNaturalSize) return
    const r = canvasRef.current.getBoundingClientRect()
    const padding = 32 // breathing room
    const wRatio = (r.width - padding) / imageNaturalSize.w
    const hRatio = (r.height - padding) / imageNaturalSize.h
    setZoom(Math.max(ZOOM_MIN, Math.min(wRatio, hRatio)))
  }, [imageNaturalSize])

  // On mount: prune stale empty entries from localStorage, then if there is
  // at least one actually-labeled saved page, restore the most recent.
  useEffect(() => {
    const entries = Object.values(savedPages).filter(p => p.regions.length > 0)
    const stale = Object.values(savedPages).filter(p => p.regions.length === 0)
    if (stale.length > 0) {
      setSavedPages(prev => {
        const next = { ...prev }
        for (const p of stale) delete next[p.slug]
        persistSavedPages(next)
        return next
      })
    }
    if (entries.length === 0) return
    const mostRecent = entries.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0]
    let cancelled = false
    ;(async () => {
      const source = await fetchFallbackBreadcrumbSourceRegions(mostRecent.slug)
      if (cancelled) return
      setSlug(mostRecent.slug)
      setImageUrl(mostRecent.imageDataUrl)
      setImageDataUrl(mostRecent.imageDataUrl)
      setRegions(backfillMissingBreadcrumbPaths(mostRecent.regions, source))
      if (mostRecent.naturalSize) setImageNaturalSize(mostRecent.naturalSize)
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-save on every regions/image/slug change — but ONLY if the page
  // actually has at least one labeled region. Otherwise "load preset →
  // never label → reload" leaves a parade of empty entries in the explorer.
  useEffect(() => {
    if (!imageDataUrl || !slug) return
    if (regions.length === 0) return
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => {
      setSavedPages(prev => {
        const next: Record<string, SavedPage> = { ...prev }
        next[slug] = {
          slug,
          imageDataUrl,
          regions,
          updatedAt: new Date().toISOString(),
          naturalSize: imageNaturalSize ?? undefined,
        }
        persistSavedPages(next)
        return next
      })
    }, 500)
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    }
  }, [regions, imageDataUrl, slug, imageNaturalSize])

  const loadSavedPage = useCallback(async (p: SavedPage) => {
    const source = await fetchFallbackBreadcrumbSourceRegions(p.slug)
    setSlug(p.slug)
    setImageUrl(p.imageDataUrl)
    setImageDataUrl(p.imageDataUrl)
    setRegions(backfillMissingBreadcrumbPaths(p.regions, source))
    setImageNaturalSize(p.naturalSize ?? null)
    setSelectedId(null)
    setWarnings([`Loaded saved page ${p.slug} (${p.regions.length} regions)`])
  }, [])

  const deleteSavedPage = useCallback((targetSlug: string) => {
    setSavedPages(prev => {
      const next = { ...prev }
      delete next[targetSlug]
      persistSavedPages(next)
      return next
    })
    if (slug === targetSlug) {
      setRegions([])
      setRegionsInitial([])
      setRegionsAgent([])
      setExtractionSourceRegions([])
      setImageUrl(null)
      setImageDataUrl(null)
      setImageNaturalSize(null)
      setSlug('manual_labeling')
    }
  }, [slug])

  const newPage = useCallback(() => {
    setRegions([])
    setRegionsInitial([])
    setRegionsAgent([])
    setExtractionSourceRegions([])
    setImageUrl(null)
    setImageDataUrl(null)
    setImageNaturalSize(null)
    setSlug(`page_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}`)
    setSelectedId(null)
    setWarnings([])
  }, [])

  const loadSlice = useCallback(async (slice: KnownSlice) => {
    try {
      // Pull the canonical image + (optional) contract before considering
      // local edits so schema-enriched fields can backfill stale saved state.
      const dataUrl = await urlToDataUrl(slice.imageUrl)
      let importedRegions: Region[] = []
      const importWarnings: string[] = []
      if (slice.expectedElementsUrl) {
        try {
          const resp = await fetch(slice.expectedElementsUrl)
          if (resp.ok) {
            const json = await resp.json()
            const { regions: rs, warnings: ws } = importJson(json)
            importedRegions = rs.map(r => ({ ...r, origin: r.origin ?? 'human' }))
            importWarnings.push(...ws)
          } else {
            importWarnings.push(`expected_elements.json fetch returned HTTP ${resp.status}`)
          }
        } catch (err) {
          importWarnings.push(`expected_elements.json fetch failed: ${err instanceof Error ? err.message : String(err)}`)
        }
      }

      // 3. Agent sweep: fetch the link sidecar (control_link / publication_link
      //    candidates pre-detected via pypdfium2 /Dest annotations).
      let agentLinkRegions: Region[] = []
      if (slice.linkSidecarUrl) {
        try {
          const resp = await fetch(slice.linkSidecarUrl)
          if (resp.ok) {
            const json = await resp.json()
            const { regions: rs, warnings: ws } = linksToRegions(json, importedRegions)
            agentLinkRegions = rs
            importWarnings.push(...ws.map(w => `link_sidecar: ${w}`))
          } else {
            importWarnings.push(`link_sidecar fetch returned HTTP ${resp.status}`)
          }
        } catch (err) {
          importWarnings.push(`link_sidecar fetch failed: ${err instanceof Error ? err.message : String(err)}`)
        }
      }

      const allRegions = [...importedRegions, ...agentLinkRegions]
      const extractionSourceRegions = await fetchExtractionSourceRegions(slice.expectedElementsUrl)
      const local = savedPages[slice.slug]
      const humanRegions = local && local.regions.length > 0
        ? backfillMissingExtractionPayloads(backfillMissingBreadcrumbPaths(local.regions, allRegions), extractionSourceRegions)
        : allRegions
      setSlug(slice.slug)
      setImageUrl(dataUrl)
      setImageDataUrl(dataUrl)
      setRegions(humanRegions)
      setRegionsInitial(JSON.parse(JSON.stringify(allRegions)))
      setRegionsAgent([])
      setExtractionSourceRegions(extractionSourceRegions)
      setSelectedId(null)
      const linkSummary = agentLinkRegions.length > 0
        ? ` · ${agentLinkRegions.length} agent-link candidate${agentLinkRegions.length === 1 ? '' : 's'}`
        : ''
      const localSummary = local && local.regions.length > 0
        ? ` · restored local edit with current hierarchy metadata`
        : ''
      setWarnings([
        `Loaded ${slice.label} · ${importedRegions.length} region${importedRegions.length === 1 ? '' : 's'} from contract${linkSummary}${localSummary}`,
        ...importWarnings,
      ])
    } catch (err) {
      setWarnings([`Failed to load ${slice.label}: ${err instanceof Error ? err.message : String(err)}`])
    }
  }, [savedPages])

  /** Load a page from a Project (parallels loadSlice, but uses ProjectPage
   *  shape and respects the sign-off snapshot if present). */
  const loadProjectPage = useCallback(async (project: Project, page: ProjectPage) => {
    try {
      const key = signoffKey(project.project_id, page.slug)
      const signoff = projectSignoffs[key]

      const dataUrl = await urlToDataUrl(page.image_url)
      let importedRegions: Region[] = []
      const importWarnings: string[] = []

      if (page.expected_elements_url) {
        try {
          const resp = await fetch(page.expected_elements_url)
          if (resp.ok) {
            const { regions: rs, warnings: ws } = importJson(await resp.json())
            importedRegions = rs.map(r => ({ ...r, origin: r.origin ?? 'human' }))
            importWarnings.push(...ws)
          }
        } catch (err) {
          importWarnings.push(`expected_elements fetch failed: ${err instanceof Error ? err.message : String(err)}`)
        }
      }
      if (page.link_sidecar_url) {
        try {
          const resp = await fetch(page.link_sidecar_url)
          if (resp.ok) {
            const { regions: rs, warnings: ws } = linksToRegions(await resp.json(), importedRegions)
            importedRegions = [...importedRegions, ...rs]
            importWarnings.push(...ws.map(w => `link_sidecar: ${w}`))
          }
        } catch (err) {
          importWarnings.push(`link_sidecar fetch failed: ${err instanceof Error ? err.message : String(err)}`)
        }
      }
      const extractionSourceRegions = await fetchExtractionSourceRegions(page.expected_elements_url)
      importedRegions = backfillMissingExtractionPayloads(importedRegions, extractionSourceRegions)
      if (signoff && signoff.agreed_regions.length > 0) {
        importWarnings.push(`Restored signed-off snapshot from ${signoff.agreed_at} by ${signoff.agreed_by}`)
      }

      // 4. Second-pass Agent view: fetch the scillm-refined sidecar if
      //    present. This is the LLM enrichment of the deterministic
      //    Original output. Surfaced under the "Agent" view-mode.
      let agentRegions: Region[] = []
      if (page.second_pass_url) {
        try {
          const resp = await fetch(page.second_pass_url)
          if (resp.ok) {
            const json = await resp.json()
            const { regions: rs, warnings: ws } = importJson(json)
            agentRegions = backfillMissingExtractionPayloads(
              rs.map(r => ({ ...r, origin: 'agent_dispatcher' as const })),
              extractionSourceRegions,
            )
            importWarnings.push(...ws.map(w => `second_pass: ${w}`))
          }
        } catch (err) {
          importWarnings.push(`second_pass fetch failed: ${err instanceof Error ? err.message : String(err)}`)
        }
      }

      let diskWipRegions: Region[] = []
      try {
        const resp = await fetch('/pdf-lab-api/signoffs/load-in-progress')
        if (resp.ok) {
          const payload = await resp.json() as {
            entries?: Record<string, { regions?: Region[]; updated_at?: string; source_generated_at?: string }>
          }
          const entry = payload.entries?.[key]
          if (entry?.regions?.length) {
            const sourceMatches = isInProgressCompatibleWithSource(entry.regions, importedRegions)
            if (sourceMatches) {
              diskWipRegions = backfillMissingExtractionPayloads(
                backfillMissingBreadcrumbPaths(entry.regions, importedRegions),
                extractionSourceRegions,
              )
              const sourceNote = entry.source_generated_at && entry.source_generated_at !== project.generated_at
                ? '; source artifact was regenerated but region families stayed compatible'
                : ''
              importWarnings.push(`Restored in-progress human feedback from disk (${entry.regions.length} regions, ${entry.updated_at ?? 'unknown time'}${sourceNote})`)
            } else {
              importWarnings.push(
                `Ignored incompatible in-progress human feedback from disk (${entry.updated_at ?? 'unknown time'} does not match current region families)`,
              )
            }
          }
        }
      } catch {
        // Middleware unavailable: fall through to signoff/agent/original seed order.
      }

      // Pick the Human starting state: prefer scillm second-pass when present
      // (it's already a refinement of the deterministic Original — saves the
      // human the merging/cleanup work the agent already did). Fall back to
      // importedRegions (Original heuristic) otherwise.
      const humanSeed = (signoff && signoff.agreed_regions.length > 0)
        ? backfillMissingExtractionPayloads(
            backfillMissingBreadcrumbPaths(signoff.agreed_regions, importedRegions),
            extractionSourceRegions,
          )
        : (diskWipRegions.length > 0
            ? diskWipRegions
            : agentRegions.length > 0
            ? backfillMissingBreadcrumbPaths(
                agentRegions.map(r => ({ ...r, origin: 'human' as const, id: newId() })),
                importedRegions,
              )
            : importedRegions)
      const seedSource = signoff ? 'signed-off snapshot'
        : diskWipRegions.length > 0 ? 'in-progress human feedback'
        : agentRegions.length > 0 ? 'Agent (scillm second-pass)'
        : 'Original (pdf_oxide + ledger)'

      // Fetch context-neighbor renders (prev/next pages) for cross-page
      // continuity scanning. We resolve them by anchor_page ± 1 against the
      // project's page list, falling back to nothing if no matching project
      // entry exists at that anchor. Neighbors are READ-ONLY context — the
      // human only annotates the focal canvas.
      const fetchNeighbor = async (anchorPageDelta: number): Promise<ContextNeighbor | null> => {
        const neighborAnchor = page.anchor_page + anchorPageDelta
        const neighborPage = project.pages.find(p => p.anchor_page === neighborAnchor)
        if (!neighborPage) return null
        try {
          const nDataUrl = await urlToDataUrl(neighborPage.image_url)
          // Prefer second_pass (Agent) regions for neighbor display, fall back
          // to expected_elements (Original). Read-only either way.
          let neighborRegions: Region[] = []
          const tryUrl = neighborPage.second_pass_url || neighborPage.expected_elements_url
          if (tryUrl) {
            try {
              const r = await fetch(tryUrl)
              if (r.ok) {
                const { regions: rs } = importJson(await r.json())
                neighborRegions = rs.map(reg => ({ ...reg, origin: 'agent_dispatcher' as const }))
              }
            } catch {/* swallow — context view degrades gracefully */}
          }
          return { slug: neighborPage.slug, image_url: nDataUrl, page_index: neighborAnchor, regions: neighborRegions }
        } catch {
          return null
        }
      }
      const [prevNbr, nextNbr] = await Promise.all([fetchNeighbor(-1), fetchNeighbor(+1)])

      setCurrentProjectId(project.project_id)
      setSlug(page.slug)
      setImageUrl(dataUrl)
      setImageDataUrl(dataUrl)
      setRegions(humanSeed)
      // Capture the Original (heuristic) regions as the diff baseline.
      // Diff stays meaningful: Original vs Human-final.
      setRegionsInitial(JSON.parse(JSON.stringify(importedRegions)))
      setRegionsAgent(agentRegions)
      setExtractionSourceRegions(extractionSourceRegions)
      setContextPrev(prevNbr)
      setContextNext(nextNbr)
      setSelectedId(null)
      const statusLabel = signoff ? 'signed-off' : page.status
      const ctxMsg = (prevNbr || nextNbr)
        ? ` · context: ${prevNbr ? `prev=${prevNbr.slug}` : '(no prev)'} ${nextNbr ? `next=${nextNbr.slug}` : '(no next)'}`
        : ''
      setWarnings([
        `Project: ${project.name} · page ${page.label} · status=${statusLabel} · seeded Human from ${seedSource} (${humanSeed.length} region${humanSeed.length === 1 ? '' : 's'})${ctxMsg}`,
        ...importWarnings,
      ])
    } catch (err) {
      setWarnings([`Failed to load ${page.label}: ${err instanceof Error ? err.message : String(err)}`])
    }
  }, [projectSignoffs])

  /** Sign off the current page: snapshot regions, mark agreed, advance
   *  to the next pending page in the same project. */
  const signOffAndNext = useCallback(() => {
    if (!currentProjectId) {
      setWarnings(['No active project — cannot sign off'])
      return
    }
    const project = projects.find(p => p.project_id === currentProjectId)
    if (!project) return
    const page = project.pages.find(p => p.slug === slug)
    if (!page) {
      setWarnings([`Active slug ${slug} is not part of ${project.name}; cannot sign off as project page`])
      return
    }
    const key = signoffKey(project.project_id, page.slug)
    // Compute the verdict: did the human edit anything? Each edit is a
    // classified bug spec for pdf_oxide_core or the NIST ledger.
    const { verdict, diff, proposed_owner } = computeVerdict(regionsInitial, regions)
    const next: PageSignoff = {
      project_id: project.project_id,
      page_slug: page.slug,
      agreed_at: new Date().toISOString(),
      agreed_by: 'graham',
      agreed_regions: regions,
      regions_initial: regionsInitial,
      verdict,
      diff,
      proposed_owner,
    }
    const updated = { ...projectSignoffs, [key]: next }
    setProjectSignoffs(updated)
    persistProjectSignoffs(updated)
    // Auto-persist to disk via the Vite middleware so the project agent
    // can read the latest sign-offs without any export-button dance.
    // Failure is non-fatal (localStorage remains the fallback).
    try {
      void fetch('/pdf-lab-api/signoffs/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          schema_version: 'pdf_lab.signoff_export.v1',
          exported_at: new Date().toISOString(),
          exported_by: 'graham',
          projects: projects.map(p => ({
            project_id: p.project_id,
            name: p.name,
            pages_total: p.pages.length,
          })),
          signoffs: updated,
        }),
      })
    } catch {/* swallow — localStorage already updated */}
    // Verdict summary for the status banner.
    const verdictMsg = verdict === 'confirmed'
      ? `CONFIRMED pdf_oxide for ${page.label} (0 edits, ${regions.length} regions locked as positive fixture)`
      : `AMENDED ${page.label}: ${diff.length} diff entr${diff.length === 1 ? 'y' : 'ies'} · proposed owner: ${proposed_owner}`
    const remaining = project.pages.filter(p =>
      p.slug !== page.slug &&
      p.status !== 'agreed' &&
      !updated[signoffKey(project.project_id, p.slug)],
    )
    if (remaining.length === 0) {
      setWarnings([verdictMsg, `Project ${project.name} has no more pending pages.`])
      return
    }
    const nextPage = remaining[0]
    setWarnings([verdictMsg, `Advancing to ${nextPage.label} (${remaining.length} more pending).`])
    loadProjectPage(project, nextPage)
  }, [currentProjectId, projects, projectSignoffs, regions, regionsInitial, slug, loadProjectPage])

  /** Load projects from the index on mount. */
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const indexResp = await fetch('/pdf-lab-projects/index.json')
        if (!indexResp.ok) return
        const idx = await indexResp.json() as { projects: ProjectIndexEntry[] }
        const loaded: Project[] = []
        for (const entry of idx.projects ?? []) {
          try {
            const pResp = await fetch(entry.url)
            if (pResp.ok) loaded.push(await pResp.json() as Project)
          } catch {/* ignore individual project failures */}
        }
        if (!cancelled) setProjects(loaded)
      } catch {/* no projects index → fall back to legacy KNOWN_SLICES */}
    })()
    return () => { cancelled = true }
  }, [])

  /** Load lightweight second-pass summaries for every project page so the
   *  left queue shows agent/machine status without requiring each page to be
   *  opened first. */
  useEffect(() => {
    if (projects.length === 0) return
    let cancelled = false
    ;(async () => {
      const entries: Record<string, AgentSecondPassSummary> = {}
      await Promise.all(projects.flatMap(project =>
        project.pages.map(async page => {
          if (!page.second_pass_url) return
          try {
            const resp = await fetch(page.second_pass_url)
            if (!resp.ok) return
            const summary = agentSecondPassSummary(await resp.json())
            if (summary) entries[signoffKey(project.project_id, page.slug)] = summary
          } catch {
            // Missing sidecars degrade to the manifest's pending/in-review state.
          }
        }),
      ))
      if (!cancelled) setProjectSecondPass(entries)
    })()
    return () => { cancelled = true }
  }, [projects])

  useEffect(() => {
    if (didAutoLoadProjectRef.current || currentProjectId || projects.length === 0) return
    const selected = recommendedCandidate ?? (() => {
      const preferred = projects[0]
      const page = preferred.pages.find(candidate => candidate.status !== 'agreed') ?? preferred.pages[0]
      return page ? { project: preferred, page, guidance: null } : null
    })()
    if (!selected) return
    didAutoLoadProjectRef.current = true
    void loadProjectPage(selected.project, selected.page)
  }, [currentProjectId, loadProjectPage, projects, recommendedCandidate])

  /** Continuous auto-save of the current edit state to disk. Every time
   *  `regions` changes while a project page is loaded, POST a debounced
   *  snapshot to /pdf-lab-api/signoffs/save-in-progress. The agent reads
   *  in_progress.json at any time to see WIP edits — no sign-off needed,
   *  no export-button click. This is the collaboration loop. */
  useEffect(() => {
    if (!currentProjectId || !slug) return
    const project = projects.find(p => p.project_id === currentProjectId)
    if (!project) return
    if (!project.pages.some(pg => pg.slug === slug)) return
    const t = window.setTimeout(() => {
      try {
        void fetch('/pdf-lab-api/signoffs/save-in-progress', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: currentProjectId,
            page_slug: slug,
            regions,
            regions_initial: regionsInitial,
            updated_at: new Date().toISOString(),
            source_generated_at: project.generated_at,
          }),
        })
      } catch {/* offline / no middleware — swallow */}
    }, 400)  // debounce: bundle rapid edits (drag, resize, family-cycle)
    return () => window.clearTimeout(t)
  }, [regions, regionsInitial, currentProjectId, slug, projects])

  /** Auto-load signed-off snapshots from disk on mount so the human↔agent
   *  loop is shared state, not localStorage-trapped. Disk wins over
   *  localStorage when both exist (disk is the agent-readable source). */
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const resp = await fetch('/pdf-lab-api/signoffs/load')
        if (!resp.ok) return
        const payload = await resp.json() as { signoffs?: Record<string, PageSignoff> }
        if (cancelled) return
        const fromDisk = payload.signoffs ?? {}
        if (Object.keys(fromDisk).length > 0) {
          setProjectSignoffs(prev => {
            const merged = { ...prev, ...fromDisk }
            persistProjectSignoffs(merged)
            return merged
          })
        }
      } catch {/* middleware not running — localStorage stays authoritative */}
    })()
    return () => { cancelled = true }
  }, [])

  /** Convert a client-pixel point to normalized image coords. Uses the
   *  scaled image wrapper rect so the mapping stays correct at any zoom. */
  const clientToNormalized = useCallback((clientX: number, clientY: number): [number, number] | null => {
    const el = imgWrapperRef.current
    if (!el) return null
    const r = el.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) return null
    return [clamp01((clientX - r.left) / r.width), clamp01((clientY - r.top) / r.height)]
  }, [])

  /** Shift+drag triggers marquee-delete mode (instead of drawing a new
   *  region). Mouse-up deletes every region whose bbox intersects the
   *  marquee rectangle. */
  const [marqueeMode, setMarqueeMode] = useState<boolean>(false)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!imageUrl) return
    // Original / Agent / Diff views are read-only.
    if (viewMode !== 'human') return
    const p = clientToNormalized(e.clientX, e.clientY)
    if (!p) return
    setSelectedId(null)
    if (e.shiftKey) {
      // Marquee-delete: same drag-rect mechanism, different family marker.
      setMarqueeMode(true)
      setDrag({ startX: p[0], startY: p[1], curX: p[0], curY: p[1], family: activeFamily })
    } else {
      setMarqueeMode(false)
      setDrag({ startX: p[0], startY: p[1], curX: p[0], curY: p[1], family: activeFamily })
    }
  }, [activeFamily, clientToNormalized, imageUrl, viewMode])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (regionDrag && imageNaturalSize) {
      // Convert pixel delta → normalized [0,1] coords. The wrapper at zoom z
      // is naturalW * z pixels wide; one px on screen = 1 / (naturalW * z)
      // in normalized space.
      const dxN = (e.clientX - regionDrag.startClientX) / (imageNaturalSize.w * zoom)
      const dyN = (e.clientY - regionDrag.startClientY) / (imageNaturalSize.h * zoom)
      const [sx0, sy0, sx1, sy1] = regionDrag.startBbox
      let nx0 = sx0, ny0 = sy0, nx1 = sx1, ny1 = sy1
      switch (regionDrag.mode) {
        case 'move': {
          // Translate, but keep the rect entirely inside [0, 1].
          let tx = dxN, ty = dyN
          if (sx0 + tx < 0) tx = -sx0
          if (sy0 + ty < 0) ty = -sy0
          if (sx1 + tx > 1) tx =  1 - sx1
          if (sy1 + ty > 1) ty =  1 - sy1
          nx0 = sx0 + tx; nx1 = sx1 + tx
          ny0 = sy0 + ty; ny1 = sy1 + ty
          break
        }
        case 'n':  ny0 = clamp01(sy0 + dyN); break
        case 's':  ny1 = clamp01(sy1 + dyN); break
        case 'e':  nx1 = clamp01(sx1 + dxN); break
        case 'w':  nx0 = clamp01(sx0 + dxN); break
        case 'nw': nx0 = clamp01(sx0 + dxN); ny0 = clamp01(sy0 + dyN); break
        case 'ne': nx1 = clamp01(sx1 + dxN); ny0 = clamp01(sy0 + dyN); break
        case 'sw': nx0 = clamp01(sx0 + dxN); ny1 = clamp01(sy1 + dyN); break
        case 'se': nx1 = clamp01(sx1 + dxN); ny1 = clamp01(sy1 + dyN); break
      }
      // Normalize against accidental inversion when a resize crosses through
      // the opposite edge.
      const bbox: [number, number, number, number] = [
        Math.min(nx0, nx1), Math.min(ny0, ny1),
        Math.max(nx0, nx1), Math.max(ny0, ny1),
      ]
      setRegions(prev => prev.map(r => r.id === regionDrag.regionId ? { ...r, bbox } : r))
      return
    }
    if (!drag) return
    const p = clientToNormalized(e.clientX, e.clientY)
    if (!p) return
    setDrag({ ...drag, curX: p[0], curY: p[1] })
  }, [clientToNormalized, drag, regionDrag, imageNaturalSize, zoom])

  const handleMouseUp = useCallback(() => {
    if (regionDrag) { setRegionDrag(null); return }
    if (!drag) return
    const bbox = normalizeRect(drag.startX, drag.startY, drag.curX, drag.curY)
    const w = bbox[2] - bbox[0], h = bbox[3] - bbox[1]
    if (w < 0.005 || h < 0.005) {
      setDrag(null)
      setMarqueeMode(false)
      return
    }
    if (marqueeMode) {
      // Marquee-delete: drop every region whose bbox intersects the marquee.
      const intersects = (a: [number, number, number, number], b: [number, number, number, number]): boolean => {
        return !(a[2] <= b[0] || a[0] >= b[2] || a[3] <= b[1] || a[1] >= b[3])
      }
      setRegions(prev => {
        const kept = prev.filter(r => !intersects(r.bbox, bbox))
        const removed = prev.length - kept.length
        if (removed > 0) {
          setWarnings([`Marquee-delete: removed ${removed} region${removed === 1 ? '' : 's'} intersecting the marquee rect`])
        }
        return kept
      })
      setSelectedId(null)
      setMarqueeMode(false)
      setDrag(null)
      return
    }
    const id = newId()
    setRegions(prev => [...prev, hydrateRegionMetadata({ id, family: drag.family, bbox }, prev, extractionSourceRegions)])
    setSelectedId(id)
    setDrag(null)
  }, [drag, extractionSourceRegions, regionDrag, marqueeMode])

  /** Click the family tag → cycle through 4 anchored positions. The label
   *  is always pinned to a corner of the bbox so move/resize keep them
   *  visually attached. */
  const handleLabelClick = useCallback((e: React.MouseEvent, regionId: string) => {
    e.stopPropagation()
    e.preventDefault()
    setRegions(prev => prev.map(r => r.id === regionId
      ? { ...r, labelAnchor: nextAnchor(r.labelAnchor) }
      : r))
  }, [])

  const handleReorderDragStart = useCallback((e: React.DragEvent, regionId: string) => {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', regionId)
    setReorderDragId(regionId)
  }, [])

  const handleReorderDragOver = useCallback((e: React.DragEvent, regionId: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (regionId !== reorderHoverId) setReorderHoverId(regionId)
  }, [reorderHoverId])

  const handleReorderDrop = useCallback((e: React.DragEvent, targetId: string) => {
    e.preventDefault()
    const sourceId = e.dataTransfer.getData('text/plain')
    setReorderDragId(null)
    setReorderHoverId(null)
    if (!sourceId || sourceId === targetId) return
    setRegions(prev => {
      const fromIdx = prev.findIndex(r => r.id === sourceId)
      const toIdx = prev.findIndex(r => r.id === targetId)
      if (fromIdx < 0 || toIdx < 0) return prev
      const next = [...prev]
      const [moved] = next.splice(fromIdx, 1)
      next.splice(toIdx, 0, moved)
      return next
    })
  }, [])

  const handleReorderDragEnd = useCallback(() => {
    setReorderDragId(null)
    setReorderHoverId(null)
  }, [])

  /** Sort regions by reading order: top-to-bottom (bbox y0), then
   *  left-to-right (bbox x0) within the same line. The matcher doesn't
   *  care about order, but downstream artifacts (closure_page.html,
   *  expected_elements.json review) read better in reading order. */
  const sortByReadingOrder = useCallback(() => {
    setRegions(prev => [...prev].sort((a, b) => {
      // Treat rows within ~1.5% of the page height as the same "line".
      const dy = a.bbox[1] - b.bbox[1]
      if (Math.abs(dy) > 0.015) return dy
      return a.bbox[0] - b.bbox[0]
    }))
  }, [])

  const handleRegionMouseDown = useCallback(
    (e: React.MouseEvent, regionId: string,
     mode: 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw' = 'move') => {
      e.stopPropagation()
      e.preventDefault()
      const r = regions.find(rr => rr.id === regionId)
      if (!r) return
      setSelectedId(regionId)
      setRegionDrag({
        regionId, mode,
        startClientX: e.clientX,
        startClientY: e.clientY,
        startBbox: [...r.bbox] as [number, number, number, number],
      })
    }, [regions])

  /** Keybindings:
   *    Esc        → cancel drag/selection/context-menu
   *    Del/BS     → delete selected region
   *    1-9/0/q    → pick family
   *    Ctrl/Cmd + + / = → zoom in
   *    Ctrl/Cmd + -     → zoom out
   *    Ctrl/Cmd + 0     → reset zoom (100%)
   *    Ctrl/Cmd + 9     → fit image to viewport
   */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return
      // Zoom shortcuts.
      if (e.ctrlKey || e.metaKey) {
        if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomIn(); return }
        if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomOut(); return }
        if (e.key === '0')                  { e.preventDefault(); zoomReset(); return }
        if (e.key === '9')                  { e.preventDefault(); zoomFit(); return }
      }
      if (e.key === 'Escape') {
        setDrag(null)
        setSelectedId(null)
        setContextMenu(null)
        return
      }
      if (e.key === '`') {
        setOverlayMode(prev => prev === 'clean' ? 'compact' : prev === 'compact' ? 'debug' : 'clean')
        return
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedId) {
        setRegions(prev => prev.filter(r => r.id !== selectedId))
        setSelectedId(null)
        return
      }
      // Family hotkeys — but skip if Ctrl/Cmd held (those mean zoom).
      if (e.ctrlKey || e.metaKey) return
      const match = familyDefs.find(f => f.hotkey === e.key.toLowerCase())
      if (match) {
        setActiveFamily(match.id)
        if (selectedId && viewMode === 'human') {
          setRegions(prev => prev.map(region => region.id === selectedId
            ? hydrateRegionMetadata({ ...region, family: match.id }, prev, extractionSourceRegions)
            : region))
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [extractionSourceRegions, familyDefs, selectedId, viewMode, zoomIn, zoomOut, zoomReset, zoomFit])

  /** Ctrl/Cmd + scroll zooms; plain scroll uses native canvas scrolling. */
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (!(e.ctrlKey || e.metaKey)) return
    e.preventDefault()
    setZoom(z => {
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1
      return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z * factor))
    })
  }, [])

  /** Right-click context menu — over a region: gives quick zoom + delete +
   *  family pick. Over empty canvas: zoom only. */
  const handleContextMenu = useCallback((e: React.MouseEvent, regionId?: string) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({ x: e.clientX, y: e.clientY, regionId })
    if (regionId) setSelectedId(regionId)
  }, [])

  // Close context menu on outside click.
  useEffect(() => {
    if (!contextMenu) return
    function onDown() { setContextMenu(null) }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [contextMenu])

  const onFile = useCallback(async (file: File) => {
    // Persist as data URL so reload/saved-pages can rehydrate the image.
    // (URL.createObjectURL would not survive a page reload.)
    const dataUrl = await fileToDataUrl(file)
    setImageUrl(dataUrl)
    setImageDataUrl(dataUrl)
    setRegions([])
    setSelectedId(null)
    const stem = file.name.replace(/\.[^.]+$/, '')
    setSlug(s => (s === 'manual_labeling' || s.startsWith('page_2')) ? stem : s)
  }, [])

  const onJsonImport = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const data = JSON.parse(String(reader.result || ''))
        const { regions: imported, warnings: w, format } = importJson(data)
        setRegions(prev => [...prev, ...imported])
        setWarnings([`Imported ${imported.length} regions from ${format}`, ...w])
      } catch (err) {
        setWarnings([`Import failed: ${err instanceof Error ? err.message : String(err)}`])
      }
    }
    reader.readAsText(file)
  }, [])

  const onExport = useCallback(() => {
    const payload = regionsToExpected(asExportableRegions(regions), slug)
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${slug}_expected_elements.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [regions, slug])

  // Show a preview rect while dragging.
  const previewRect = useMemo(() => {
    if (!drag) return null
    const bbox = normalizeRect(drag.startX, drag.startY, drag.curX, drag.curY)
    return bbox
  }, [drag])

  const agentViewRegions = regionsAgent.length > 0 ? regionsAgent : regionsInitial
  const paneRegions = viewMode === 'original'
    ? regionsInitial
    : viewMode === 'agent'
      ? agentViewRegions
      : regions
  const paneSelectedRegion = paneRegions.find(r => r.id === selectedId) ?? null
  const inspectorRegions = paneSelectedRegion ? [paneSelectedRegion] : []
  const currentProject = currentProjectId ? projects.find(p => p.project_id === currentProjectId) : null
  const activeProjectPage = currentProject?.pages.find(p => p.slug === slug) ?? null
  const selectedFamilyDef = paneSelectedRegion
    ? familyDefs.find(f => f.id === paneSelectedRegion.family)
    : activeFamilyDef
  const activePageNotes = activeProjectPage?.notes
    ? activeProjectPage.notes.split(';').map(note => note.trim()).filter(Boolean)
    : []
  const activePagePrimaryNote = activePageNotes[0] ?? activeProjectPage?.stratum ?? null
  const liveIssueVerdict = useMemo(
    () => activeProjectPage ? computeVerdict(regionsInitial, regions) : null,
    [activeProjectPage, regions, regionsInitial],
  )
  const livePageIssueDraft = useMemo(
    () => activeProjectPage && liveIssueVerdict
      ? buildPageIssueDraft(activeProjectPage, currentProject, liveIssueVerdict, regions)
      : null,
    [activeProjectPage, currentProject, liveIssueVerdict, regions],
  )
  const activeTocRegion = paneSelectedRegion?.semantic_role === 'toc' || paneSelectedRegion?.family === 'toc'
    ? paneSelectedRegion
    : paneRegions.find(region => region.semantic_role === 'toc' || region.family === 'toc') ?? null
  const activeTocEntries = activeTocRegion?.toc_entries ?? []
  const activeTocFlatEntries = flattenTocEntries(activeTocEntries)
  const selectedHumanRegion = viewMode === 'human'
    ? regions.find(region => region.id === selectedId) ?? null
    : null
  const applyFamilyToSelectedRegion = useCallback((family: FamilyId) => {
    setActiveFamily(family)
    if (!selectedId || viewMode !== 'human') return
    setRegions(prev => prev.map(region => region.id === selectedId ? hydrateRegionMetadata({ ...region, family }, prev, extractionSourceRegions) : region))
  }, [extractionSourceRegions, selectedId, viewMode])
  const onLabelPaletteDragStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startY = event.clientY
    const startPos = labelPalettePos
    document.body.style.cursor = 'move'
    document.body.style.userSelect = 'none'

    const onMove = (moveEvent: MouseEvent) => {
      const next = {
        x: Math.max(8, Math.min(window.innerWidth - 260, startPos.x + moveEvent.clientX - startX)),
        y: Math.max(48, Math.min(window.innerHeight - 360, startPos.y + moveEvent.clientY - startY)),
      }
      setLabelPalettePos(next)
      window.localStorage.setItem('pdf-lab-labeling-label-palette-pos', JSON.stringify(next))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [labelPalettePos])
  const onDataPaneResizeStart = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    const startX = event.clientX
    const startWidth = dataPaneWidth
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const onMove = (moveEvent: MouseEvent) => {
      const nextWidth = Math.max(280, Math.min(640, startWidth - (moveEvent.clientX - startX)))
      setDataPaneWidth(nextWidth)
      window.localStorage.setItem('pdf-lab-labeling-data-pane-width', String(nextWidth))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [dataPaneWidth])

  return (
    <div
      className={`pdf-lab-labeling-root overlay-${overlayMode} ${selectedId ? 'has-selection' : 'no-selection'}`}
      data-qid="pdf-lab:labeling:root"
    >
      <div className="pdf-lab-labeling-main" data-qid="pdf-lab:labeling:main">
      <LeftPane title="PDF Candidates" width={240} defaultCollapsed={false}>
      <div className="pdf-lab-labeling-chips" data-qid="pdf-lab:labeling:chip-column">
        {recommendedCandidate && (
          <section
            className="pdf-lab-labeling-one-page-workflow"
            data-qid="pdf-lab:labeling:one-page-workflow"
            aria-label="One page workflow recommendation"
          >
            <div className="pdf-lab-labeling-one-page-kicker">One-page workflow</div>
            <div className="pdf-lab-labeling-one-page-title">{recommendedCandidate.page.label}</div>
            <div className="pdf-lab-labeling-one-page-meta">
              {recommendedCandidate.guidance.expectedRegionCount} expected regions · p.{recommendedCandidate.page.anchor_page}
            </div>
            <div className="pdf-lab-labeling-one-page-scope">{recommendedCandidate.guidance.scope}</div>
            <div className="pdf-lab-labeling-one-page-reason">{recommendedCandidate.guidance.reason}</div>
            <button
              className="pdf-lab-labeling-one-page-open"
              data-qid="pdf-lab:labeling:open-recommended-candidate"
              data-qs-action="PDF_LAB_LABELING_OPEN_RECOMMENDED_ONE_PAGE"
              onClick={() => loadProjectPage(recommendedCandidate.project, recommendedCandidate.page)}
              title="Open the currently recommended one-page candidate"
            >
              Open selected candidate
            </button>
          </section>
        )}
        {(() => {
          // One unified explorer: known slices first, then any custom local
          // slugs the user added that aren't in the manifest. Each row shows
          // the live region count from the saved-page record (so users can
          // see at-a-glance what's actually labeled vs. blank).
          const knownSlugs = new Set(KNOWN_SLICES.map(s => s.slug))
          const customSavedPages = Object.values(savedPages)
            .filter(p => !knownSlugs.has(p.slug) && p.regions.length > 0)
            .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))

          // Always-expanded project queue: show every project's pages inline
          // (no "click to open" step). The currently-loaded page is highlighted.
          // Project sign-off uses the toolbar button; the queue is a navigator.
          return (
            <div className="pdf-lab-labeling-pages">
              {projects.length > 0 && projects.map(proj => {
                let agreed = 0
                let secondPassResolved = 0
                let humanNeeded = 0
                for (const pg of proj.pages) {
                  const key = signoffKey(proj.project_id, pg.slug)
                  const state = queueStateForPage(pg, projectSignoffs[key], projectSecondPass[key])
                  if (state === 'human_signed_off') agreed++
                  if (state === 'second_pass_resolved') secondPassResolved++
                  if (state === 'human_needed') humanNeeded++
                }
                return (
                  <div key={proj.project_id} className="pdf-lab-labeling-pages-project">
                    <div className="pdf-lab-labeling-chips-title">
                      🤖 {proj.name}
                      <span className="pdf-lab-labeling-project-progress">
                        · {secondPassResolved}/{proj.pages.length} second pass · {humanNeeded} human · {agreed} agreed
                      </span>
                    </div>
                    {proj.pages.map(pg => {
                      const isActive = pg.slug === slug && currentProjectId === proj.project_id
                      const isRecommended = recommendedCandidate?.project.project_id === proj.project_id &&
                        recommendedCandidate.page.slug === pg.slug
                      const key = signoffKey(proj.project_id, pg.slug)
                      const signoff = projectSignoffs[key]
                      const secondPass = projectSecondPass[key]
                      const queueState = queueStateForPage(pg, signoff, secondPass)
                      const statusClass = `is-status-${queueState.replace(/_/g, '-')}`
                      const hint = queueStateLabel(queueState)
                      const tooltipParts = [
                        pg.label,
                        queueStateLongLabel(queueState),
                        secondPass?.fix_error_request_count !== undefined ? `${secondPass.fix_error_request_count} fix request${secondPass.fix_error_request_count === 1 ? '' : 's'}` : null,
                        secondPass?.captured_at ? `second pass ${secondPass.captured_at.slice(0, 10)}` : null,
                        pg.agent_origin ?? 'agent',
                      ].filter(Boolean)
                      const tooltip = tooltipParts.join(' · ')
                      const StatusIcon = queueState === 'human_signed_off'
                        ? UserCheck
                        : queueState === 'second_pass_resolved'
                        ? CheckCircle2
                        : queueState === 'human_needed'
                        ? AlertTriangle
                        : queueState === 'in_review'
                        ? CircleDashed
                        : Circle
                      return (
                        <div
                          key={pg.slug}
                          className={`pdf-lab-labeling-pages-row pdf-lab-labeling-pages-row-compact is-queue-${queueState.replace(/_/g, '-')} ${isActive ? 'is-active' : ''} ${isRecommended ? 'is-recommended' : ''}`}
                          data-qid={`pdf-lab:labeling:page-${pg.slug}`}
                        >
                          <button
                            className="pdf-lab-labeling-pages-row-main"
                            data-qid={`pdf-lab:labeling:page-open-${pg.slug}`}
                            data-qs-action="PDF_LAB_LABELING_OPEN_PROJECT_PAGE"
                            onClick={() => loadProjectPage(proj, pg)}
                            title={tooltip}
                            aria-label={tooltip}
                          >
                            <span className={`pdf-lab-labeling-pages-row-status ${statusClass}`} aria-label={queueStateLongLabel(queueState)}>
                              <StatusIcon size={14} strokeWidth={2.4} aria-hidden="true" />
                            </span>
                            <span className="pdf-lab-labeling-pages-row-slug">{pg.label}</span>
                            <span className={`pdf-lab-labeling-pages-row-hint pdf-lab-labeling-pages-row-hint-inline ${statusClass}`}>
                              {isRecommended ? `next · ${hint}` : hint}
                            </span>
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )
              })}
              {projects.length > 0 && (
                <div className="pdf-lab-labeling-pages-section">LEGACY SLICES</div>
              )}
              {projects.length === 0 && <div className="pdf-lab-labeling-chips-title">Projects</div>}
              {KNOWN_SLICES.map(s => {
                const saved = savedPages[s.slug]
                const isActive = s.slug === slug
                const regionCount = saved?.regions.length ?? 0
                const dirty = saved && saved.regions.length > 0 && imageDataUrl === saved.imageDataUrl ? '·' : ''
                return (
                  <div
                    key={s.slug}
                    className={`pdf-lab-labeling-pages-row ${isActive ? 'is-active' : ''}`}
                    data-qid={`pdf-lab:labeling:project-${s.slug}`}
                  >
                    <button
                      className="pdf-lab-labeling-pages-row-main"
                      data-qid={`pdf-lab:labeling:project-open-${s.slug}`}
                      data-qs-action="PDF_LAB_LABELING_OPEN_LEGACY_SLICE"
                      onClick={() => loadSlice(s)}
                      title={s.imageUrl}
                    >
                      <span className="pdf-lab-labeling-pages-row-slug">{s.label}</span>
                      <span className="pdf-lab-labeling-pages-row-hint">
                        {regionCount > 0
                          ? `${regionCount} region${regionCount === 1 ? '' : 's'} ${dirty}`
                          : (s.expectedElementsUrl ? 'has contract · click to load' : 'blank · click to label')}
                      </span>
                    </button>
                    {saved && (
                      <button
                        className="pdf-lab-labeling-pages-row-del"
                        onClick={() => deleteSavedPage(s.slug)}
                        title={`Clear local edits for ${s.slug}`}
                      >×</button>
                    )}
                  </div>
                )
              })}
              {customSavedPages.length > 0 && (
                <>
                  <div className="pdf-lab-labeling-pages-section">CUSTOM</div>
                  {customSavedPages.map(p => {
                    const isActive = p.slug === slug
                    return (
                      <div
                        key={p.slug}
                        className={`pdf-lab-labeling-pages-row ${isActive ? 'is-active' : ''}`}
                        data-qid={`pdf-lab:labeling:saved-${p.slug}`}
                      >
                        <button
                          className="pdf-lab-labeling-pages-row-main"
                          data-qid={`pdf-lab:labeling:saved-open-${p.slug}`}
                          data-qs-action="PDF_LAB_LABELING_OPEN_SAVED_PAGE"
                          onClick={() => loadSavedPage(p)}
                          title={`Updated ${p.updatedAt}`}
                        >
                          <span className="pdf-lab-labeling-pages-row-slug">{p.slug}</span>
                          <span className="pdf-lab-labeling-pages-row-hint">
                            {p.regions.length} region{p.regions.length === 1 ? '' : 's'}
                          </span>
                        </button>
                        <button
                          className="pdf-lab-labeling-pages-row-del"
                          onClick={() => deleteSavedPage(p.slug)}
                          title={`Delete custom slug ${p.slug}`}
                        >×</button>
                      </div>
                    )
                  })}
                </>
              )}
              <button
                className="pdf-lab-labeling-pages-new"
                data-qid="pdf-lab:labeling:new-page"
                data-qs-action="PDF_LAB_LABELING_NEW_PAGE"
                title="Create a custom labeling page from uploaded files"
                onClick={newPage}
              >
                + Custom page from file
              </button>
            </div>
          )
        })()}

      </div>
      </LeftPane>

      <section className="pdf-lab-labeling-canvas-pane" data-qid="pdf-lab:labeling:canvas-pane">
        <header className="pdf-lab-labeling-canvas-toolbar">
          <details className="pdf-lab-labeling-overflow-menu">
            <summary title="Secondary import/export/debug actions">Tools</summary>
            <div className="pdf-lab-labeling-overflow-panel">
              <label className="pdf-lab-labeling-file">
                <input type="file" accept="image/*" onChange={e => e.target.files?.[0] && onFile(e.target.files[0])} />
                <span>Open page image…</span>
              </label>
              <label className="pdf-lab-labeling-file">
                <input type="file" accept="application/json,.json" onChange={e => e.target.files?.[0] && onJsonImport(e.target.files[0])} />
                <span>Import expected_elements JSON…</span>
              </label>
              <button className="pdf-lab-labeling-export" onClick={onExport} disabled={regions.length === 0}>
                Export expected_elements.json
              </button>
            </div>
          </details>
          <label className="pdf-lab-labeling-file">
            <input type="file" accept="image/*" onChange={e => e.target.files?.[0] && onFile(e.target.files[0])} />
            <span>Open image…</span>
          </label>
          <label className="pdf-lab-labeling-file">
            <input type="file" accept="application/json,.json" onChange={e => e.target.files?.[0] && onJsonImport(e.target.files[0])} />
            <span>Import JSON…</span>
          </label>
          <span className="pdf-lab-labeling-spacer" />
          <label className="pdf-lab-labeling-family-picker" title={`Active family: ${activeFamily}`}>
            <span>Family</span>
            <select
              value={activeFamily}
              onChange={event => setActiveFamily(event.target.value as FamilyId)}
              data-qid="pdf-lab:labeling:family-select"
              aria-label="Active annotation family"
            >
              {familyDefs.map(f => <option key={f.id} value={f.id}>{f.id}</option>)}
            </select>
          </label>
          <input
            className="pdf-lab-labeling-slug"
            type="text"
            value={slug}
            onChange={e => setSlug(e.target.value)}
            placeholder="slice_id (slug)"
          />
          <button className="pdf-lab-labeling-export" onClick={onExport} disabled={regions.length === 0}>
            Export JSON
          </button>
          <button
            className="pdf-lab-labeling-export"
            onClick={() => {
              // Dump the full sign-off snapshot bundle (every project page
              // the human has signed off, with regions_initial + regions_final
              // + verdict + diff + proposed_owner). This is the artifact the
              // project agent reads to compute pdf_oxide_core + ledger PRs.
              const payload = {
                schema_version: 'pdf_lab.signoff_export.v1',
                exported_at: new Date().toISOString(),
                exported_by: 'graham',
                projects: projects.map(p => ({
                  project_id: p.project_id,
                  name: p.name,
                  pages_total: p.pages.length,
                })),
                signoffs: projectSignoffs,
              }
              const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `signoffs_${new Date().toISOString().replace(/[:.]/g, '-')}.json`
              document.body.appendChild(a)
              a.click()
              document.body.removeChild(a)
              URL.revokeObjectURL(url)
              const n = Object.keys(projectSignoffs).length
              setWarnings([`Exported ${n} signoff${n === 1 ? '' : 's'}. Commit to /tmp/nist-corpus-graph-design-review/.plan-iterate/phase-04-7-hyperlink-chip-canary/evidence-artifacts/signoffs/`])
            }}
            disabled={Object.keys(projectSignoffs).length === 0}
            title={Object.keys(projectSignoffs).length === 0
              ? 'No signed-off pages yet'
              : `Download all ${Object.keys(projectSignoffs).length} sign-off snapshots as a single JSON (verdict + diff + proposed_owner per page). Commit the file so the project agent can compute downstream PRs.`}
            data-qid="pdf-lab:labeling:export-verdicts"
          >
            ⤓ Verdicts ({Object.keys(projectSignoffs).length})
          </button>
          {(() => {
            const project = currentProjectId ? projects.find(p => p.project_id === currentProjectId) : null
            const isProjectPage = !!(project && project.pages.some(pg => pg.slug === slug))
            const alreadyAgreed = isProjectPage && project ? !!projectSignoffs[signoffKey(project.project_id, slug)] : false
            const noRegions = regions.length === 0
            const disabled = noRegions || !isProjectPage
            // Live verdict preview: would clicking sign-off CONFIRM pdf_oxide
            // (zero edits, locks a positive fixture) or AMEND it (edits exist,
            // files a bug spec routed to pdf_oxide_core / nist_preset)?
            const liveVerdict = isProjectPage ? computeVerdict(regionsInitial, regions) : null
            const verdictClass = liveVerdict?.verdict === 'amended' ? 'is-signoff-amend' : 'is-signoff'
            const label = !isProjectPage
              ? '✓ Next'
              : liveVerdict?.verdict === 'amended'
                ? `⚠ Amend (${liveVerdict.diff.length})`
                : `✓ Confirm`
            const title = !isProjectPage
              ? 'Current page is not part of an agent project queue. Open a project page from the side panel to enable sign-off.'
                : noRegions
                  ? 'Draw or load at least one region before signing off.'
                  : liveVerdict?.verdict === 'amended'
                  ? `AMEND verdict: ${liveVerdict.diff.length} raw diff entr${liveVerdict.diff.length === 1 ? 'y' : 'ies'} → owner: ${liveVerdict.proposed_owner}. Raw diffs are evidence for one page-level issue draft, not standalone bugs.`
                  : alreadyAgreed
                    ? `Re-CONFIRM pdf_oxide — no edits since the previous sign-off; locks ${regions.length} regions as positive regression fixture for ${project!.name}.`
                    : `CONFIRM pdf_oxide — no edits made; locks ${regions.length} regions as positive regression fixture for ${project!.name}.`
            return (
              <button
                className={`pdf-lab-labeling-export ${verdictClass}`}
                onClick={signOffAndNext}
                disabled={disabled}
                title={title}
                data-qid="pdf-lab:labeling:signoff-next"
              >
                {alreadyAgreed && liveVerdict?.verdict === 'confirmed' ? `✓ Re-confirm` : label}
              </button>
            )
          })()}
          <span className="pdf-lab-labeling-toolbar-divider" />
          <button
            className="pdf-lab-labeling-zoom-btn"
            onClick={() => {
              if (regions.length === 0) return
              if (window.confirm(`Clear all ${regions.length} region${regions.length === 1 ? '' : 's'} on this page? (Auto-save will persist the empty state.)`)) {
                setRegions([])
                setSelectedId(null)
              }
            }}
            disabled={regions.length === 0 || viewMode !== 'human'}
            title={
              viewMode !== 'human'
                ? 'Clear is only available in Human view'
                : regions.length === 0
                  ? 'No regions to clear'
                  : `Clear all ${regions.length} regions on this page (you can redraw from scratch)`
            }
            data-qid="pdf-lab:labeling:clear-all"
          >Clear</button>
          <span className="pdf-lab-labeling-toolbar-divider" />
          <select
            className="pdf-lab-labeling-mode-select"
            value={viewMode}
            onChange={event => setViewMode(event.target.value as typeof viewMode)}
            title="Canvas view mode"
            data-qid="pdf-lab:labeling:viewmode-select"
            aria-label="Canvas view mode"
          >
            <option value="original">Original</option>
            <option value="agent">Agent</option>
            <option value="human">Human</option>
            <option value="diff">Diff</option>
          </select>
          <select
            className="pdf-lab-labeling-mode-select"
            value={overlayMode}
            onChange={event => setOverlayMode(event.target.value as OverlayMode)}
            title="Overlay density"
            data-qid="pdf-lab:labeling:overlay-select"
            aria-label="Overlay density"
          >
            <option value="clean">Clean</option>
            <option value="compact">Compact</option>
            <option value="debug">Debug</option>
          </select>
          <span className="pdf-lab-labeling-toolbar-divider" />
          <button className="pdf-lab-labeling-zoom-btn" onClick={zoomOut}     title="Zoom out (Ctrl/Cmd −)">−</button>
          <button className="pdf-lab-labeling-zoom-btn" onClick={zoomFit}     title="Fit to viewport (Ctrl/Cmd 9)">fit</button>
          <button className="pdf-lab-labeling-zoom-btn" onClick={zoomReset}   title="Reset zoom 100% (Ctrl/Cmd 0)">{Math.round(zoom * 100)}%</button>
          <button className="pdf-lab-labeling-zoom-btn" onClick={zoomIn}      title="Zoom in (Ctrl/Cmd +)">+</button>
        </header>

        <div
          ref={canvasRef}
          className="pdf-lab-labeling-canvas"
          data-qid="pdf-lab:labeling:canvas"
          onWheel={handleWheel}
          onContextMenu={e => handleContextMenu(e)}
        >
          {imageUrl ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, width: '100%' }}>
              {contextPrev && (
                <div
                  className="pdf-lab-labeling-context-pane pdf-lab-labeling-context-prev"
                  data-qid="pdf-lab:labeling:context-prev"
                  title={`Previous page (read-only context): ${contextPrev.slug}`}
                  style={{
                    opacity: 0.55,
                    position: 'relative',
                    width: imageNaturalSize ? `${imageNaturalSize.w * zoom * 0.5}px` : '50%',
                    border: '2px dashed rgba(120,140,180,0.45)',
                    borderRadius: 6,
                    padding: 4,
                    flexShrink: 0,
                  }}
                >
                  <div style={{ fontSize: 11, color: '#9aa6c4', padding: '2px 8px', fontFamily: 'ui-monospace, monospace', textAlign: 'center' }}>
                    ◀ prev (read-only context — scan for page-spanning elements): {contextPrev.slug} · {contextPrev.regions.length} regions
                  </div>
                  <img
                    src={contextPrev.image_url}
                    alt={`Previous page ${contextPrev.slug}`}
                    draggable={false}
                    style={{ width: '100%', height: 'auto', display: 'block' }}
                  />
                </div>
              )}
            <div
              ref={imgWrapperRef}
              className="pdf-lab-labeling-canvas-inner"
              style={imageNaturalSize ? {
                width: `${imageNaturalSize.w * zoom}px`,
                height: `${imageNaturalSize.h * zoom}px`,
              } : undefined}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={() => drag && handleMouseUp()}
            >
              <img
                src={imageUrl}
                alt="Page being annotated"
                className="pdf-lab-labeling-canvas-img"
                onLoad={e => {
                  const img = e.currentTarget
                  setImageNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
                }}
                draggable={false}
              />
              {(() => {
                // Compute the displayed region set based on viewMode.
                //   'agent' → regionsInitial (read-only, pdf_oxide's claim)
                //   'human' → regions (editable, default)
                //   'diff'  → union with per-region _diffStatus annotation
                interface RenderRegion extends Region {
                  _diffStatus?: 'identical' | 'added' | 'removed' | 'bbox_edited' | 'family_relabeled' | 'metadata_edited'
                }
                let displayed: RenderRegion[] = []
                if (viewMode === 'original') {
                  // Original = pdf_oxide + ledger deterministic (the regions captured
                  // at page-load before any human or scillm edits).
                  displayed = regionsInitial.map(r => ({ ...r, _diffStatus: 'identical' as const }))
                } else if (viewMode === 'agent') {
                  // Agent = scillm second-pass when present; otherwise the
                  // deterministic pdf_oxide + ledger annotation contract.
                  displayed = agentViewRegions.map(r => ({ ...r, _diffStatus: 'identical' as const }))
                } else if (viewMode === 'human') {
                  displayed = regions
                } else {
                  const initialById = new Map(regionsInitial.map(r => [r.id, r]))
                  const currentById = new Map(regions.map(r => [r.id, r]))
                  const allIds = new Set<string>([...initialById.keys(), ...currentById.keys()])
                  for (const id of allIds) {
                    const a = initialById.get(id)
                    const h = currentById.get(id)
                    if (a && !h) {
                      displayed.push({ ...a, _diffStatus: 'removed' })
                    } else if (!a && h) {
                      displayed.push({ ...h, _diffStatus: 'added' })
                    } else if (a && h) {
                      const d = classifyRegionDiff(a, h)
                      if (!d) {
                        displayed.push({ ...h, _diffStatus: 'identical' })
                      } else if (d.kind === 'family_relabeled') {
                        displayed.push({ ...h, _diffStatus: 'family_relabeled' })
                      } else if (d.kind === 'bbox_edited') {
                        displayed.push({ ...h, _diffStatus: 'bbox_edited' })
                      } else {
                        displayed.push({ ...h, _diffStatus: 'metadata_edited' })
                      }
                    }
                  }
                }
                return displayed.map(r => {
                  const def = familyDefs.find(f => f.id === r.family)
                  const isSelected = selectedId === r.id && viewMode === 'human'
                  const isEditable = viewMode === 'human'
                  const diffClass = r._diffStatus && r._diffStatus !== 'identical'
                    ? `is-diff-${r._diffStatus}`
                    : ''
                  return (
                  <div
                    key={`${viewMode}-${r.id}`}
                    className={`pdf-lab-labeling-region ${isSelected ? 'is-selected' : ''} ${r.origin && r.origin !== 'human' ? 'is-agent' : ''} ${diffClass}`}
                    data-origin={r.origin ?? 'human'}
                    onMouseDown={isEditable ? e => handleRegionMouseDown(e, r.id, 'move') : undefined}
                    onContextMenu={isEditable ? e => handleContextMenu(e, r.id) : undefined}
                    style={{
                      left: `${r.bbox[0] * 100}%`,
                      top: `${r.bbox[1] * 100}%`,
                      width: `${(r.bbox[2] - r.bbox[0]) * 100}%`,
                      height: `${(r.bbox[3] - r.bbox[1]) * 100}%`,
                      borderColor: def?.color ?? '#fff',
                      background: overlayMode === 'debug' ? `${def?.color ?? '#fff'}26` : 'transparent',
                    }}
                  >
                    <span
                      className={`pdf-lab-labeling-region-tag tag-anchor-${r.labelAnchor ?? 'top-outside'} ${r.semantic_role === 'toc_entry' ? 'is-toc-entry' : ''} ${r.semantic_role === 'toc_heading' ? 'is-toc-heading' : ''}`}
                      style={{ ['--region-color' as string]: def?.color ?? '#fff' }}
                      onMouseDown={e => { e.stopPropagation(); e.preventDefault() }}
                      onClick={e => handleLabelClick(e, r.id)}
                      title={overlayMode === 'debug'
                        ? 'Debug overlay label. Click to cycle label position.'
                        : `${r.semantic_role ?? r.family}${typeof r.target_page === 'number' ? ` target page ${r.target_page}` : ''}. Click to cycle label position.`}
                    >
                      {overlayLabelForRegion(r, overlayMode)}
                    </span>
                    {isSelected && (['nw','n','ne','e','se','s','sw','w'] as const).map(dir => (
                      <div
                        key={dir}
                        className={`pdf-lab-labeling-region-handle h-${dir}`}
                        onMouseDown={e => handleRegionMouseDown(e, r.id, dir)}
                        title={`Drag to resize (${dir})`}
                      />
                    ))}
                  </div>
                  )
                })
              })()}
              {selectedHumanRegion && (
                <div
                  className="pdf-lab-labeling-family-popover"
                  data-qid="pdf-lab:labeling:family-popover"
                  style={{
                    left: labelPalettePos.x,
                    top: labelPalettePos.y,
                  }}
                  onMouseDown={event => { event.stopPropagation() }}
                >
                  <div
                    className="pdf-lab-labeling-family-popover-title"
                    data-qid="pdf-lab:labeling:family-popover-drag-handle"
                    title="Drag to move label hotkey reference"
                    onMouseDown={onLabelPaletteDragStart}
                  >
                    Set label
                  </div>
                  <div className="pdf-lab-labeling-family-popover-grid">
                    {familyDefs.map(family => (
                      <button
                        key={family.id}
                        className={`pdf-lab-labeling-family-popover-chip ${selectedHumanRegion.family === family.id ? 'is-active' : ''}`}
                        data-qid={`pdf-lab:labeling:popover-family-${family.id}`}
                        style={{ ['--chip-color' as string]: family.color }}
                        onClick={() => applyFamilyToSelectedRegion(family.id)}
                        title={`${family.id} (${family.hotkey})`}
                      >
                        <span>{family.hotkey}</span>
                        <strong>{family.id}</strong>
                      </button>
                    ))}
                  </div>
                  <div className="pdf-lab-labeling-family-popover-custom">
                    <input
                      value={customFamilyInput}
                      onChange={event => setCustomFamilyInput(event.target.value)}
                      onKeyDown={event => {
                        if (event.key === 'Enter') {
                          event.preventDefault()
                          addCustomFamily()
                        }
                      }}
                      placeholder="custom_label"
                      data-qid="pdf-lab:labeling:custom-family-input"
                    />
                    <button
                      type="button"
                      onClick={addCustomFamily}
                      data-qid="pdf-lab:labeling:add-custom-family"
                    >
                      Add
                    </button>
                  </div>
                  {customFamilyIds.length > 0 && (
                    <div className="pdf-lab-labeling-family-popover-custom-list" data-qid="pdf-lab:labeling:custom-family-list">
                      {customFamilyIds.map(id => {
                        const usageCount = regions.filter(region => region.family === id).length
                        return (
                          <div key={id} className="pdf-lab-labeling-family-popover-custom-row">
                            <span title={`${usageCount} current region${usageCount === 1 ? '' : 's'} use this label`}>
                              {id}
                              <em>{usageCount}</em>
                            </span>
                            <button
                              type="button"
                              onClick={() => renameCustomFamily(id)}
                              data-qid={`pdf-lab:labeling:rename-custom-family-${id}`}
                              title={`Rename custom label ${id}`}
                            >
                              Rename
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteCustomFamily(id)}
                              data-qid={`pdf-lab:labeling:delete-custom-family-${id}`}
                              title={`Delete custom label ${id}`}
                            >
                              Delete
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
              {previewRect && (
                <div
                  className={`pdf-lab-labeling-region is-preview ${marqueeMode ? 'is-marquee-delete' : ''}`}
                  style={{
                    left: `${previewRect[0] * 100}%`,
                    top: `${previewRect[1] * 100}%`,
                    width: `${(previewRect[2] - previewRect[0]) * 100}%`,
                    height: `${(previewRect[3] - previewRect[1]) * 100}%`,
                    borderColor: marqueeMode ? '#ef4444' : activeFamilyDef.color,
                    background: marqueeMode ? '#ef444422' : `${activeFamilyDef.color}22`,
                  }}
                />
              )}
            </div>
            {contextNext && (
              <div
                className="pdf-lab-labeling-context-pane pdf-lab-labeling-context-next"
                data-qid="pdf-lab:labeling:context-next"
                title={`Next page (read-only context): ${contextNext.slug}`}
                style={{
                  opacity: 0.55,
                  position: 'relative',
                  width: imageNaturalSize ? `${imageNaturalSize.w * zoom * 0.5}px` : '50%',
                  border: '2px dashed rgba(120,140,180,0.45)',
                  borderRadius: 6,
                  padding: 4,
                  flexShrink: 0,
                }}
              >
                <div style={{ fontSize: 11, color: '#9aa6c4', padding: '2px 8px', fontFamily: 'ui-monospace, monospace', textAlign: 'center' }}>
                  ▶ next (read-only context — scan for page-spanning elements): {contextNext.slug} · {contextNext.regions.length} regions
                </div>
                <img
                  src={contextNext.image_url}
                  alt={`Next page ${contextNext.slug}`}
                  draggable={false}
                  style={{ width: '100%', height: 'auto', display: 'block' }}
                />
              </div>
            )}
            </div>
          ) : (
            <div className="pdf-lab-labeling-empty">
              Open a page image to start labeling.
              <br /><small>Hotkeys 1-9/0/q pick a family · Esc cancels · Del removes selection · Ctrl-+/-/0/9 zoom · Right-click for menu</small>
            </div>
          )}
        </div>

        {contextMenu && (
          <div
            className="pdf-lab-labeling-ctx-menu"
            style={{ left: contextMenu.x, top: contextMenu.y }}
            onMouseDown={e => e.stopPropagation()}
          >
            <button onClick={() => { zoomIn(); setContextMenu(null) }}>Zoom in</button>
            <button onClick={() => { zoomOut(); setContextMenu(null) }}>Zoom out</button>
            <button onClick={() => { zoomFit(); setContextMenu(null) }}>Fit to viewport</button>
            <button onClick={() => { zoomReset(); setContextMenu(null) }}>Reset 100%</button>
            {contextMenu.regionId && (
              <>
                <div className="pdf-lab-labeling-ctx-divider" />
                <div className="pdf-lab-labeling-ctx-header">Change family</div>
                {familyDefs.map(f => (
                  <button
                    key={f.id}
                    onClick={() => {
                      setRegions(prev => prev.map(r => r.id === contextMenu.regionId ? hydrateRegionMetadata({ ...r, family: f.id }, prev, extractionSourceRegions) : r))
                      setContextMenu(null)
                    }}
                  >
                    <span style={{ background: f.color, width: 10, height: 10, display: 'inline-block', borderRadius: 2, marginRight: 6 }} />
                    {f.id}
                  </button>
                ))}
                <div className="pdf-lab-labeling-ctx-divider" />
                <button
                  onClick={() => {
                    setRegions(prev => prev.map(r => r.id === contextMenu.regionId ? { ...r, labelAnchor: undefined } : r))
                    setContextMenu(null)
                  }}
                >Reset label position</button>
                <button
                  className="pdf-lab-labeling-ctx-del"
                  onClick={() => {
                    setRegions(prev => prev.filter(r => r.id !== contextMenu.regionId))
                    setSelectedId(null)
                    setContextMenu(null)
                  }}
                >Delete region</button>
              </>
            )}
          </div>
        )}

      </section>

      <div
        className="pdf-lab-labeling-data-pane-resizer"
        data-qid="pdf-lab:labeling:data-pane-resizer"
        data-qs-action="PDF_LAB_RESIZE_DATA_PANE"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize annotation data pane"
        title="Drag to resize data pane"
        onMouseDown={onDataPaneResizeStart}
      />

      <aside
        className="pdf-lab-labeling-regions-pane"
        data-qid="pdf-lab:labeling:regions-pane"
        style={{ ['--data-pane-width' as string]: `${dataPaneWidth}px` }}
      >
        <div className="pdf-lab-labeling-inspector-hero" data-qid="pdf-lab:labeling:inspector-hero">
          <div className="pdf-lab-labeling-inspector-kicker">Annotation Decision</div>
          <h2>{paneSelectedRegion ? 'Amend selected region' : 'Select or draw a region'}</h2>
          <p>
            {activeProjectPage
              ? `${currentProject?.name ?? 'Project'} · ${activeProjectPage.label}`
              : 'Open an artifact-backed project page from the queue.'}
          </p>
          <div className="pdf-lab-labeling-inspector-facts">
            <span>{paneRegions.length} visible region{paneRegions.length === 1 ? '' : 's'}</span>
            <span>{viewMode} view</span>
            <span>{selectedFamilyDef?.id ?? activeFamily}</span>
          </div>
        </div>
        {activeProjectPage && activePageNotes.length > 0 && (
          <div className="pdf-lab-labeling-human-task" data-qid="pdf-lab:labeling:human-task">
            <div className="pdf-lab-labeling-human-task-kicker">What the agent is unsure about</div>
            <strong>{activePagePrimaryNote}</strong>
            <ul>
              {activePageNotes.slice(1).map(note => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        )}
        {activeProjectPage && liveIssueVerdict && (
          <div className="pdf-lab-labeling-issue-card" data-qid="pdf-lab:labeling:identified-issues">
            <div className="pdf-lab-labeling-issue-card-head">
              <div>
                <span>Identified Issues</span>
                <strong>
                  {livePageIssueDraft
                    ? `1 page issue · ${livePageIssueDraft.issue_items.length} bug${livePageIssueDraft.issue_items.length === 1 ? '' : 's'}`
                    : 'No page issue'}
                </strong>
              </div>
              <button
                type="button"
                disabled={!livePageIssueDraft}
                onClick={() => {
                  if (!livePageIssueDraft) return
                  const payload = {
                    schema: 'pdf_lab.github_issue_draft_export.v1',
                    exported_at: new Date().toISOString(),
                    repository: 'grahama1970/pdf_oxide',
                    page_slug: activeProjectPage.slug,
                    drafts: [livePageIssueDraft],
                  }
                  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `${activeProjectPage.slug}_github_issue_drafts.json`
                  document.body.appendChild(a)
                  a.click()
                  document.body.removeChild(a)
                  URL.revokeObjectURL(url)
                }}
                data-qid="pdf-lab:labeling:export-github-issue-drafts"
              >
                Export
              </button>
            </div>
            {!livePageIssueDraft ? (
              <p>No human-vs-agent diffs on this page. A sign-off would create a positive regression fixture.</p>
            ) : (
              <ol>
                {livePageIssueDraft.issue_items.map(issue => (
                  <li key={issue.id}>
                    <span>{issue.owner}</span>
                    <strong>{issue.title}</strong>
                    <em>{issue.evidence_region_ids.length} regions</em>
                    <p>{issue.rationale}</p>
                  </li>
                ))}
              </ol>
            )}
            {livePageIssueDraft && livePageIssueDraft.raw_diff_count > 0 && (
              <div className="pdf-lab-labeling-issue-card-more">
                Raw amendment diffs: {livePageIssueDraft.raw_diff_count}. These are evidence for the page issue, not separate bugs.
              </div>
            )}
          </div>
        )}
        {activeTocRegion && (
          <div className="pdf-lab-labeling-toc-inspector" data-qid="pdf-lab:labeling:toc-inspector">
            <div className="pdf-lab-labeling-toc-inspector-head">
              <span>Extracted TOC Structure</span>
              <strong>{activeTocFlatEntries.length} entries</strong>
            </div>
          <div className="pdf-lab-labeling-toc-tree">
              {activeTocFlatEntries.slice(0, 18).map(entry => (
                <div
                  key={entry.id}
                  className="pdf-lab-labeling-toc-tree-row"
                  style={{ ['--toc-depth' as string]: Math.max(0, entry.level - 1) }}
                >
                  <span>{entry.title}</span>
                  <em>p.{entry.target_page}{entry.verification?.status === 'matched' ? ' ✓' : ''}</em>
                </div>
              ))}
              {activeTocFlatEntries.length > 18 && (
                <div className="pdf-lab-labeling-toc-tree-more">+ {activeTocFlatEntries.length - 18} more entries in JSON</div>
              )}
            </div>
            <details className="pdf-lab-labeling-toc-json">
              <summary>Show nested JSON</summary>
              <pre>{formatTocJson(activeTocEntries)}</pre>
            </details>
          </div>
        )}
        <div className="pdf-lab-labeling-family-grid" data-qid="pdf-lab:labeling:family-grid">
          {familyDefs.map(f => (
            <button
              key={f.id}
              className={`pdf-lab-labeling-family-tile ${activeFamily === f.id || paneSelectedRegion?.family === f.id ? 'is-active' : ''}`}
              style={{ ['--chip-color' as string]: f.color }}
              onClick={() => {
                setActiveFamily(f.id)
                if (paneSelectedRegion && viewMode === 'human') {
                  setRegions(prev => prev.map(r => r.id === paneSelectedRegion.id ? hydrateRegionMetadata({ ...r, family: f.id }, prev, extractionSourceRegions) : r))
                }
              }}
              title={`${f.id} (${f.hotkey})`}
              data-qid={`pdf-lab:labeling:family-tile-${f.id}`}
            >
              <span className="pdf-lab-labeling-family-tile-key">{f.hotkey}</span>
              <span className="pdf-lab-labeling-family-tile-label">{f.id}</span>
            </button>
          ))}
        </div>
        <div className="pdf-lab-labeling-regions-title">
          <span>{paneSelectedRegion ? 'Selected region' : `Regions (${paneRegions.length})`}</span>
          {imageNaturalSize && <span className="pdf-lab-labeling-regions-meta">{imageNaturalSize.w}×{imageNaturalSize.h}px</span>}
          <button
            className="pdf-lab-labeling-pane-close"
            type="button"
            data-qid="pdf-lab:labeling:regions-close"
            data-qs-action="PDF_LAB_REGIONS_PANE_CLOSE"
            title="Close selected-region inspector"
            onClick={() => setSelectedId(null)}
          >
            ×
          </button>
        </div>
        <div
          className="pdf-lab-labeling-selected-breadcrumb"
          data-qid="pdf-lab:labeling:selected-breadcrumb"
          title="Selected region document hierarchy path"
        >
          <span className="pdf-lab-labeling-region-breadcrumb-label">Path:</span>
          <span className="pdf-lab-labeling-selected-breadcrumb-text">
            {hierarchyPathText(paneSelectedRegion)}
          </span>
        </div>
        {paneSelectedRegion && (
          <div className="pdf-lab-labeling-selected-breadcrumb-note">
            Document hierarchy metadata; not a PDF element type.
          </div>
        )}
        {paneSelectedRegion?.notes?.includes(HIERARCHY_UNRESOLVED_NOTE) && (
          <div className="pdf-lab-labeling-selected-breadcrumb-error" data-qid="pdf-lab:labeling:hierarchy-error">
            Hierarchy could not be auto-derived for this region. Add a path or inspect the TOC-backed source regions.
          </div>
        )}
        {viewMode === 'human' && regions.length > 1 && (
          <button
            className="pdf-lab-labeling-regions-sort"
            data-qid="pdf-lab:labeling:sort-by-reading-order"
            onClick={sortByReadingOrder}
            title="Sort regions top-to-bottom by their bbox position on the page"
          >
            ↓ Sort by reading order
          </button>
        )}
        {!paneSelectedRegion && (
          <div className="pdf-lab-labeling-regions-empty">
            Select a region to edit type, text, and traceability. The full region list is intentionally hidden to keep the PDF canvas usable.
          </div>
        )}
        {inspectorRegions.map((r) => {
          const def = familyDefs.find(f => f.id === r.family)
          const update = (patch: Partial<Region>) => setRegions(prev => prev.map(x => x.id === r.id ? hydrateRegionMetadata({ ...x, ...patch }, prev, extractionSourceRegions) : x))
          const remove = () => { setRegions(prev => prev.filter(x => x.id !== r.id)); if (selectedId === r.id) setSelectedId(null) }
          const isDragging = reorderDragId === r.id
          const isDropTarget = reorderHoverId === r.id && reorderDragId && reorderDragId !== r.id
          const selectedIndex = paneRegions.findIndex(candidate => candidate.id === r.id)
          const previousBreadcrumbNodes = [...paneRegions.slice(0, Math.max(0, selectedIndex))]
            .reverse()
            .map(candidate => breadcrumbNodesFromRegion(candidate))
            .find(candidateNodes => candidateNodes.length > 0)
          return (
            <div
              key={r.id}
              data-qid={`pdf-lab:labeling:region-${r.id}`}
              className={
                `pdf-lab-labeling-region-row ` +
                `${selectedId === r.id ? 'is-selected ' : ''}` +
                `${isDragging ? 'is-dragging ' : ''}` +
                `${isDropTarget ? 'is-drop-target ' : ''}`
              }
              onClick={() => setSelectedId(r.id)}
              onDragOver={e => handleReorderDragOver(e, r.id)}
              onDrop={e => handleReorderDrop(e, r.id)}
              onDragLeave={() => setReorderHoverId(prev => prev === r.id ? null : prev)}
            >
              <div className="pdf-lab-labeling-region-row-head">
                <span
                  className="pdf-lab-labeling-region-row-grip"
                  draggable
                  onDragStart={e => handleReorderDragStart(e, r.id)}
                  onDragEnd={handleReorderDragEnd}
                  title="Drag to reorder"
                >≡</span>
                <span className="pdf-lab-labeling-region-row-swatch" style={{ background: def?.color }} />
                <select value={r.family} onChange={e => update({ family: e.target.value as FamilyId })}>
                  {familyDefs.map(f => <option key={f.id} value={f.id}>{f.id}</option>)}
                </select>
                <button className="pdf-lab-labeling-region-row-del" onClick={e => { e.stopPropagation(); remove() }}>×</button>
              </div>
              <input
                type="text"
                value={r.label || ''}
                onChange={e => update({ label: e.target.value || undefined })}
                placeholder="label (e.g. 'AC-2 ACCOUNT MANAGEMENT')"
              />
              <textarea
                rows={2}
                value={r.text_hint || ''}
                onChange={e => update({ text_hint: e.target.value || undefined })}
                placeholder="text_hint — exact text the matcher should find"
              />
              {r.extraction && (
                <div className="pdf-lab-labeling-extraction-card" data-qid="pdf-lab:labeling:selected-extraction">
                  <div className="pdf-lab-labeling-extraction-card-head">
                    <span>Extracted {r.family} JSON</span>
                    <em>{r.extraction.source_id || r.extraction.source || 'release extraction'}</em>
                  </div>
                  {r.family === 'table' && r.extraction.table_json && (
                    <div className="pdf-lab-labeling-extraction-summary">
                      <span>{r.extraction.table_json.row_count ?? 'unknown'} rows</span>
                      <span>{r.extraction.table_json.col_count ?? 'unknown'} cols</span>
                      {r.extraction.table_json.semantic_type && <span>{r.extraction.table_json.semantic_type}</span>}
                    </div>
                  )}
                  <details open>
                    <summary>Structured payload</summary>
                    <pre>{JSON.stringify(r.extraction.table_json ?? r.extraction, null, 2)}</pre>
                  </details>
                </div>
              )}
              {!r.extraction && EXTRACTION_CAPABLE_FAMILIES.has(r.family) && (
                <div className="pdf-lab-labeling-extraction-missing" data-qid="pdf-lab:labeling:extraction-missing">
                  No structured extraction payload matched this {r.family} bbox. Treat this as an extractor/materialization bug if the visual element is real.
                </div>
              )}
              <BreadcrumbEditor
                region={r}
                options={breadcrumbOptions}
                previousNodes={previousBreadcrumbNodes}
                onChange={update}
              />
              {r.family === 'labeled_paragraph' && (
                <input
                  type="text"
                  value={r.lead_label || ''}
                  onChange={e => update({ lead_label: e.target.value || undefined })}
                  placeholder="lead_label (e.g. 'Discussion:')"
                />
              )}
            </div>
          )
        })}
      </aside>
      </div>
    </div>
  )
}
