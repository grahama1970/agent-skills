import React, { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  Cpu,
  Film,
  GitBranch,
  Globe,
  Plane,
  Maximize2,
  Pencil,
  RefreshCw,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  MessageSquareText,
  NotebookPen,
  Trash2,
  Upload,
  X,
} from 'lucide-react'

const EMOTION_TAGS = ['LAUGH', 'CHUCKLE', 'SIGH', 'COUGH', 'SNIFFLE', 'GROAN', 'YAWN', 'GASP'] as const

import SharedChatShell from '../SharedChatShell'
import type { WatchChatAdapterOptions, WatchSceneRow } from '../memory-turn'
import {
  annotationSessionActions,
  annotationSessionReducer,
  createInitialAnnotationSession,
  selectActiveCharacter,
  selectDeleteTarget,
  selectVisibleOverlays,
} from '../src/watchAnnotationSession'
import type {
  AnnotationSessionState,
  SessionRow,
  VisibleAnnotationOverlay,
  WatchMemoryRecord,
} from '../src/watchAnnotationSession'

interface DiffInfo {
  category: 'sanitized' | 'acoustic_context' | 'hidden_dialogue' | 'minor_diff' | 'unknown_diff'
  confidence: number
  detail: string
}

interface CharacterIntel {
  name: string
  scene_count: number
  divergence_count: number
  top_divergences: Array<{ timecode: string; category: string; detail: string }>
  insight: string
}

interface DiffIntelligence {
  overall_diff_percentage: number
  category_counts: Record<string, number>
  anomaly_count: number
  anomalies: Array<{
    index: number
    timecode: string
    category: string
    confidence: number
    detail: string
  }>
  character_intel: CharacterIntel[]
  takeaways: string[]
}

type DomainStatus = 'verified' | 'divergent'
type LeftRailMode = 'audit' | 'library'
type AssetKind = 'all' | 'cinema' | 'drone' | 'itar' | 'web'
type IngestStageStatus = 'complete' | 'running' | 'pending' | 'blocked'

interface IngestStage {
  id: string
  label: string
  detail: string
  status: IngestStageStatus
}

interface AssetLibraryItem {
  id: string
  kind: Exclude<AssetKind, 'all'>
  title: string
  subtitle: string
  statusLabel: string
  diffPercent: number
  auditProgress: number
  selected: boolean
}

interface WatchIngestJob {
  job_id: string
  source: string
  status: 'queued' | 'running' | 'complete' | 'failed'
  stages: IngestStage[]
  log_tail: string[]
  report_path?: string
  error?: string
}

interface ResolutionHubState {
  rowIndex: number
  timecode: string
  entity: string
  sourceText: string
  verifiedText: string
  diffLabel: string
}

interface SceneElement {
  index: number
  timecode: string
  text?: string
  srt_text?: string
  scene_marker_image_path?: string
  video_clip_path?: string
  audio_clip_path?: string
  visual_description?: string
  visual_description_source?: string
  visual_description_status?: string
  movie_segment?: string
  sound?: string
  audio_path?: string
  diff_info?: DiffInfo
}

interface WatchOverlayIdentityCandidate {
  name: string
  actor_name?: string
  status: 'PROVISIONAL' | 'VERIFIED' | string
  confidence?: number
  entity_id?: string
  basis?: string[]
}

interface WatchOverlayPayloadOverlay {
  overlay_id: string
  segment_id: string
  track_id: string
  time_range: {
    start_seconds: number
    end_seconds: number
  }
  anchor_media_time_seconds: number
  valid_at_media_time_seconds: number
  bbox_policy: string
  track_lifecycle_status: string
  stale_after_ms: number
  detected_class: string
  classification: string
  identity_candidate?: WatchOverlayIdentityCandidate
  identity_status: string
  visibility_proof: boolean
  bbox_percent: {
    left: number
    top: number
    width: number
    height: number
  }
  render_policy: {
    stroke?: string
    stroke_color?: string
    fill_opacity?: number
    pointer_events?: string
  }
}

interface WatchOverlayPayload {
  schema_version: 'watch.ui_overlay_payload.v1'
  status: 'DRY_RUN_ONLY' | string
  proof_scope: string[]
  excluded_proofs: string[]
  overlays: WatchOverlayPayloadOverlay[]
}

type NormalizedBbox = [number, number, number, number]
type BboxResizeHandle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w'

const EMPTY_ANNOTATION_SESSION_ROW: SessionRow = {
  rowIndex: -1,
  movieTitle: '',
  segmentStartSeconds: 0,
  segmentEndSeconds: 1,
}

interface KeyframeAnnotationReceipt {
  ok: boolean
  receipt_path?: string
  error?: string
}

interface OrpheusReviewReceipt {
  ok: boolean
  receipt_path?: string
  error?: string
}

interface KeyframeAnnotationDraftState {
  characterName: string
  actorName: string
  capturedFrameDataUrl: string | null
  capturedFrameSeconds: number | null
  draftBbox: NormalizedBbox | null
  savedBoxes: KeyframeAnnotationBox[]
  adjustmentEvents: KeyframeAnnotationAdjustmentEvent[]
  saveStatus: string
}

interface KeyframeAnnotationBox {
  id: string
  bbox: NormalizedBbox
  characterName: string
  actorName: string
  timestampSeconds?: number
  status: 'draft' | 'receipt_written'
  receiptPath?: string
}

interface KeyframeAnnotationAdjustmentEvent {
  id: string
  type: 'draw' | 'move' | 'resize' | 'delete' | 'promote'
  boxId: string
  characterName: string
  actorName: string
  timestampSeconds: number
  timecode: string
  bbox: NormalizedBbox | null
  bboxDimensions: {
    left: number
    top: number
    width: number
    height: number
  } | null
  createdAt: string
}

interface WatchYoloTrackLabel {
  trackId: string
  characterName: string
  actorName?: string
  status: 'accepted' | 'suggested'
  source: 'human' | 'memory'
  confidence?: number
  updatedAt: string
}

interface WatchYoloBoxRejection {
  boxKey: string
  trackId: string
  timeSeconds: number
  status: 'rejected'
  source: 'human'
  updatedAt: string
}

interface WatchYoloLabelEvent {
  id?: string
  action: string
  status?: string
  track_id: string
  box_key?: string
  time_seconds?: number | null
  character_name?: string
  actor_name?: string
  confidence?: number
  created_at?: string
}

interface WatchYoloSequenceRow {
  key: string
  timeLabel: string
  sortValue: number
  source: 'yolo' | 'watch'
  trackId: string
  stateLabel: string
  detailLabel: string
  tone: 'accept' | 'stop' | 'reset'
}

interface WatchIdentitySuggestionResponse {
  schema?: string
  status?: string
  track_id?: string
  memory?: {
    confidence?: number
    items?: Array<Record<string, unknown>>
    suggestions?: Array<{
      character_name?: string
      actor_name?: string
      confidence?: number
      display_label?: string
    }>
  }
  suggestion?: {
    character_name?: string
    actor_name?: string
    confidence?: number
    basis?: string[]
  } | null
}

interface WatchReport {
  watch_report: {
    title: string
    duration_formatted: string
    frame_count: number
    sampling_mode: string
    gaps?: string[]
  }
  scene_elements: SceneElement[]
  captions?: { segment_count: number }
  transcript?: { segment_count: number }
  diff_intelligence?: DiffIntelligence
}

const SIDEBAR_CSS = '.watch-body::-webkit-scrollbar{width:6px}.watch-body::-webkit-scrollbar-track{background:transparent}.watch-body::-webkit-scrollbar-thumb{background:#2d3748;border-radius:3px}'
const WATCH_LEFT_COLLAPSED_KEY = 'ux-lab:watch:audit-rail-collapsed'
const WATCH_RIGHT_COLLAPSED_KEY = 'ux-lab:watch:right-sidebar-collapsed'
const WATCH_ACTIVE_TAB_KEY = 'ux-lab:watch:active-agent-tab'
const WATCH_ANNOTATION_DRAFT_PREFIX = 'ux-lab:watch:annotation-draft'
const WATCH_YOLO_LABEL_PREFIX = 'ux-lab:watch:yolo-track-labels'
const AUDIT_STEPS = ['Parsing SRT', 'Profiling Willie', 'Extracting Entities', 'Comparing SRT/Whisper', 'Accessing Memory', 'Compiling audit'] as const
const ASSET_KIND_OPTIONS: Array<{ id: AssetKind; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'cinema', label: 'Cinema' },
  { id: 'drone', label: 'Drone' },
  { id: 'itar', label: 'ITAR' },
  { id: 'web', label: 'Web' },
]
const ASSET_KIND_META: Record<Exclude<AssetKind, 'all'>, { label: string; Icon: typeof Film; color: string }> = {
  cinema: { label: 'Cinema/SRT', Icon: Film, color: '#4ea1ff' },
  drone: { label: 'Drone/UAV', Icon: Plane, color: '#03dac6' },
  itar: { label: 'ITAR stream', Icon: ShieldAlert, color: '#f59e0b' },
  web: { label: 'Web stream', Icon: Globe, color: '#ef4444' },
}
const WATCH_INGEST_CONTRACT = 'POST /api/projects/watch/ingest'

function stripWhisperSource(text?: string): string {
  return (text ?? '').replace(/\s*\+Whisper\s*$/i, '').trim()
}

function isEmptyTranscript(text?: string): boolean {
  const value = stripWhisperSource(text).trim()
  return !value || /^no transcript(?: in this segment)?\.?$/i.test(value)
}

const COLON_SPEAKER_RE = /^([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?):\s/

function extractCharacter(text: string): string | null {
  const m = text.match(COLON_SPEAKER_RE)
  return m ? m[1] : null
}

const ENTITY_COLOR_MAP: Record<string, { border: string; background: string; color: string }> = {
  Willie: { border: 'rgba(187,134,252,0.42)', background: 'rgba(187,134,252,0.09)', color: '#c9a7ff' },
  Marcus: { border: 'rgba(3,218,198,0.38)', background: 'rgba(3,218,198,0.08)', color: '#48f1df' },
  'The Kid': { border: 'rgba(78,161,255,0.38)', background: 'rgba(78,161,255,0.08)', color: '#9dc6ff' },
  Santa: { border: 'rgba(245,158,11,0.42)', background: 'rgba(245,158,11,0.09)', color: '#ffd37c' },
  Girl: { border: 'rgba(78,161,255,0.38)', background: 'rgba(78,161,255,0.08)', color: '#9dc6ff' },
  Manager: { border: 'rgba(148,163,184,0.34)', background: 'rgba(148,163,184,0.07)', color: '#cbd5e1' },
}

const ENTITY_PATTERNS: Array<{ name: string; pattern: RegExp }> = [
  { name: 'Willie', pattern: /\bwillie\b/i },
  { name: 'Marcus', pattern: /\bmarcus\b|\btony cox\b|\bmall[-\s]store elf\b|\bdepartment store elf\b|\belf character\b/i },
  { name: 'The Kid', pattern: /\bthe kid\b|\bbrett kelly\b/i },
  { name: 'Santa', pattern: /\bsanta(?:\s+claus)?\b/i },
  { name: 'Girl', pattern: /\bgirl\b|\bkid\b|\bchild\b/i },
  { name: 'Manager', pattern: /\bmanager\b|\bstore manager\b|\bsecurity\b/i },
]

const VISUAL_ENTITY_OVERRIDES: Record<string, string[]> = {
  '02:48': ['Marcus'],
  frame_0008: ['Marcus'],
}

function visualOverrideEntities(row: SceneElement): string[] {
  const frameMatch = row.scene_marker_image_path?.match(/frame_\d+/)?.[0]
  return [
    ...(row.timecode ? VISUAL_ENTITY_OVERRIDES[row.timecode] ?? [] : []),
    ...(frameMatch ? VISUAL_ENTITY_OVERRIDES[frameMatch] ?? [] : []),
  ]
}

function sceneEntities(row: SceneElement): string[] {
  const textHaystack = [row.srt_text, row.text, row.movie_segment]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .join(' ')
  const entities = new Set<string>()
  const speaker = extractCharacter(row.srt_text ?? row.text ?? '')
  if (speaker) entities.add(speaker)
  for (const entity of visualOverrideEntities(row)) entities.add(entity)
  for (const entity of ENTITY_PATTERNS) {
    if (entity.name === 'Santa' && /\bsanta\s+(?:hat|suit|costume|style|beard|wig|coat)\b/i.test(row.visual_description ?? '')) continue
    if (entity.pattern.test(textHaystack)) entities.add(entity.name)
  }
  return [...entities]
}

function calibratedVisualDescription(row: SceneElement): string {
  if (visualOverrideEntities(row).includes('Marcus')) {
    return 'Marcus (Tony Cox), the mall-store elf character, appears in this frame. The original visual pass described costume/holiday cues generically; the movie-domain cast layer resolves the visible elf as Marcus.'
  }
  return row.visual_description ?? ''
}

function entityChipColors(name: string): { border: string; background: string; color: string } {
  return ENTITY_COLOR_MAP[name] ?? { border: 'rgba(187,134,252,0.28)', background: 'rgba(187,134,252,0.06)', color: '#d6c7ff' }
}

function entityType(name: string): 'character' | 'actor' | 'place' | 'work' {
  if (['Mall', 'Store'].includes(name)) return 'place'
  if (Object.values(CAST_MAP).includes(name)) return 'actor'
  if (name === 'Bad Santa') return 'work'
  return 'character'
}

function renderDomainEntityText(
  text: string,
  entities: string[],
  onEntityClick: (entity: string) => void,
  domainStatus: DomainStatus = 'verified',
): React.ReactNode {
  if (!text || entities.length === 0) return text
  const terms = new Map<string, { name: string; type: 'character' | 'actor' | 'place' | 'work' }>()
  for (const entity of entities) {
    const clean = entity.trim()
    if (!clean) continue
    terms.set(clean.toLowerCase(), { name: clean, type: entityType(clean) })
    const actor = actorForCharacter(clean)
    if (actor) terms.set(actor.toLowerCase(), { name: actor, type: 'actor' })
  }
  const sortedTerms = [...terms.entries()].sort((a, b) => b[0].length - a[0].length)
  const matches: Array<{ start: number; end: number; text: string; name: string; type: 'character' | 'actor' | 'place' | 'work' }> = []
  const lower = text.toLowerCase()
  for (const [term, meta] of sortedTerms) {
    const pattern = new RegExp(`(?<![a-z0-9])${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![a-z0-9])`, 'gi')
    for (const match of lower.matchAll(pattern)) {
      if (typeof match.index !== 'number') continue
      const start = match.index
      const end = start + match[0].length
      matches.push({ start, end, text: text.slice(start, end), name: meta.name, type: meta.type })
    }
  }
  matches.sort((a, b) => a.start - b.start || b.end - a.end)
  const accepted: typeof matches = []
  let cursor = -1
  for (const match of matches) {
    if (match.start < cursor) continue
    accepted.push(match)
    cursor = match.end
  }
  if (accepted.length === 0) return text

  const nodes: React.ReactNode[] = []
  let offset = 0
  accepted.forEach((match, index) => {
    if (match.start > offset) nodes.push(text.slice(offset, match.start))
    nodes.push(
      <button
        key={`${match.name}-${match.start}-${index}`}
        type="button"
        className="watch-chat-entity-pivot"
        data-qid="watch:table:entity-pivot"
        data-entity-type={match.type}
        data-domain-status={domainStatus}
        title={`Verified movie-domain term: ${match.name}`}
        onClick={(event) => {
          event.stopPropagation()
          onEntityClick(match.name)
        }}
      >
        {match.text}
      </button>,
    )
    offset = match.end
  })
  if (offset < text.length) nodes.push(text.slice(offset))
  return nodes
}

const CAST_MAP: Record<string, string> = {
  Willie: 'Billy Bob Thornton',
  Marcus: 'Tony Cox',
  Sue: 'Lauren Graham',
  Gin: 'Bernie Mac',
  Lois: 'Lauren Tom',
  Grandma: 'Cloris Leachman',
  Roger: 'Ethan Phillips',
  Santa: 'Billy Bob Thornton',
  Opal: 'Octavia Spencer',
  Herb: 'Matt Walsh',
}

const CHARACTER_OPTIONS = Object.keys(CAST_MAP)

function actorForCharacter(name: string): string | null {
  if (CAST_MAP[name]) return CAST_MAP[name]
  return null
}

function candidateCharacterForRow(row: SceneElement): { name: string; actor: string | null } | null {
  const speaker = extractCharacter(row.srt_text || '') || extractCharacter(row.text || '')
  const name = speaker || sceneEntities(row)[0]
  if (!name) return null
  return { name, actor: actorForCharacter(name) }
}

function rowMatchesSearch(row: SceneElement, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return (
    row.text?.toLowerCase().includes(q) ||
    row.srt_text?.toLowerCase().includes(q) ||
    row.timecode?.includes(q) ||
    row.visual_description?.toLowerCase().includes(q) ||
    row.movie_segment?.toLowerCase().includes(q) ||
    sceneEntities(row).some((entity) => entity.toLowerCase().includes(q))
  ) ?? false
}

function clockToSeconds(value?: string): number {
  if (!value) return 0
  const parts = value.trim().split(':').map(Number)
  if (parts.some((part) => Number.isNaN(part))) return 0
  return parts.reduce((total, part) => (total * 60) + part, 0)
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function normalizeDragBbox(
  start: { x: number; y: number },
  current: { x: number; y: number },
  rect: DOMRect,
): NormalizedBbox {
  const x1 = clamp01(Math.min(start.x, current.x) / rect.width)
  const y1 = clamp01(Math.min(start.y, current.y) / rect.height)
  const x2 = clamp01(Math.max(start.x, current.x) / rect.width)
  const y2 = clamp01(Math.max(start.y, current.y) / rect.height)
  return [x1, y1, x2, y2]
}

function bboxStyle(bbox: NormalizedBbox): React.CSSProperties {
  const [x1, y1, x2, y2] = bbox
  return {
    left: `${x1 * 100}%`,
    top: `${y1 * 100}%`,
    width: `${(x2 - x1) * 100}%`,
    height: `${(y2 - y1) * 100}%`,
  }
}

function bboxObjectPosition(bbox?: NormalizedBbox | null): string {
  if (!bbox) return '50% 38%'
  const [x1, y1, x2, y2] = bbox
  return `${clamp01((x1 + x2) / 2) * 100}% ${clamp01((y1 + y2) / 2) * 100}%`
}

function resizeBboxFromHandle(
  bbox: NormalizedBbox,
  handle: BboxResizeHandle,
  dx: number,
  dy: number,
): NormalizedBbox {
  let [x1, y1, x2, y2] = bbox
  const minSize = 0.02
  if (handle.includes('w')) x1 = clamp01(x1 + dx)
  if (handle.includes('e')) x2 = clamp01(x2 + dx)
  if (handle.includes('n')) y1 = clamp01(y1 + dy)
  if (handle.includes('s')) y2 = clamp01(y2 + dy)

  if (x2 - x1 < minSize) {
    if (handle.includes('w')) x1 = Math.max(0, x2 - minSize)
    else x2 = Math.min(1, x1 + minSize)
  }
  if (y2 - y1 < minSize) {
    if (handle.includes('n')) y1 = Math.max(0, y2 - minSize)
    else y2 = Math.min(1, y1 + minSize)
  }
  return [x1, y1, x2, y2]
}

function moveBboxByDelta(bbox: NormalizedBbox, dx: number, dy: number): NormalizedBbox {
  const [x1, y1, x2, y2] = bbox
  const width = x2 - x1
  const height = y2 - y1
  const nextX1 = Math.max(0, Math.min(1 - width, x1 + dx))
  const nextY1 = Math.max(0, Math.min(1 - height, y1 + dy))
  return [nextX1, nextY1, nextX1 + width, nextY1 + height]
}

function getSnapCoordinates(value: number, anchors: number[] = [0, 0.25, 0.5, 0.75, 1], threshold = 0.005): number {
  const match = anchors.find((anchor) => Math.abs(value - anchor) <= threshold)
  return match ?? value
}

function snapBboxEdges(bbox: NormalizedBbox): NormalizedBbox {
  return [
    getSnapCoordinates(bbox[0]),
    getSnapCoordinates(bbox[1]),
    getSnapCoordinates(bbox[2]),
    getSnapCoordinates(bbox[3]),
  ]
}

function initialsForIdentity(characterName: string, actorName: string): string {
  const source = actorName.trim() || characterName.trim() || 'NA'
  const initials = source.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
  return initials || 'NA'
}

function secondsToClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

function bboxDimensions(bbox: NormalizedBbox | null): KeyframeAnnotationAdjustmentEvent['bboxDimensions'] {
  if (!bbox) return null
  const [x1, y1, x2, y2] = bbox
  return {
    left: x1,
    top: y1,
    width: x2 - x1,
    height: y2 - y1,
  }
}

function interpolateNormalizedBbox(a: NormalizedBbox, b: NormalizedBbox, ratio: number): NormalizedBbox {
  const t = clamp01(ratio)
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
    a[3] + (b[3] - a[3]) * t,
  ]
}

function interpolatedKeyframeBox(boxes: KeyframeAnnotationBox[], timeSeconds: number, characterName: string): KeyframeAnnotationBox | null {
  const candidates = boxes
    .filter((box) => box.characterName === characterName && typeof box.timestampSeconds === 'number')
    .sort((a, b) => (a.timestampSeconds ?? 0) - (b.timestampSeconds ?? 0))
  if (candidates.length < 2) return null
  const exact = candidates.find((box) => Math.abs((box.timestampSeconds ?? 0) - timeSeconds) < 0.05)
  if (exact) return exact
  const previous = [...candidates].reverse().find((box) => (box.timestampSeconds ?? 0) <= timeSeconds)
  const next = candidates.find((box) => (box.timestampSeconds ?? 0) >= timeSeconds)
  if (!previous || !next || previous.id === next.id) return null
  const start = previous.timestampSeconds ?? 0
  const end = next.timestampSeconds ?? start
  const ratio = end === start ? 0 : (timeSeconds - start) / (end - start)
  return {
    id: `interpolated-${previous.id}-${next.id}`,
    bbox: interpolateNormalizedBbox(previous.bbox, next.bbox, ratio),
    characterName,
    actorName: previous.actorName || next.actorName,
    timestampSeconds: timeSeconds,
    status: 'draft',
  }
}

function segmentEndSeconds(row: SceneElement): number {
  const range = row.movie_segment?.split('-')
  if (range?.[1]) return clockToSeconds(range[1])
  return clockToSeconds(row.timecode)
}

function segmentStartSeconds(value?: string): number {
  if (!value) return 0
  return clockToSeconds(value.split('-')[0])
}

function segmentEndFromLabel(value?: string): number {
  if (!value) return 0
  const range = value.split('-')
  return range[1] ? clockToSeconds(range[1]) : clockToSeconds(range[0])
}

function rangesOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart <= bEnd && bStart <= aEnd
}

function overlaysForClip(
  clip: { segment: string; timecode: string; entities: string[] },
  payload: WatchOverlayPayload,
): WatchOverlayPayloadOverlay[] {
  const label = clip.segment || clip.timecode
  const clipStart = segmentStartSeconds(label)
  const clipEnd = segmentEndFromLabel(label) || clipStart
  const entitySet = new Set(clip.entities.map((entity) => entity.toLowerCase()))

  return payload.overlays.filter((overlay) => {
    const candidateName = overlay.identity_candidate?.name?.toLowerCase()
    const matchesEntity = !candidateName || entitySet.size === 0 || entitySet.has(candidateName)
    return (
      matchesEntity &&
      rangesOverlap(
        clipStart,
        clipEnd,
        overlay.time_range.start_seconds,
        overlay.time_range.end_seconds,
      )
    )
  })
}

function mediaUrl(path: string | undefined, prefix: string): string | null {
  if (!path) return null
  const idx = path.indexOf(prefix)
  if (idx === -1) return null
  const suffix = path.slice(idx + prefix.length)
  const clean = suffix.startsWith('/') ? suffix.slice(1) : suffix
  const segments = clean.split('/').map((s) => encodeURIComponent(s)).join('/')
  return `/api/projects/watch/static/${prefix}/${segments}`
}

function sceneThumbUrl(row: SceneElement): string | null {
  if (row.scene_marker_image_path) return mediaUrl(row.scene_marker_image_path, 'watch-frames')
  if (row.video_clip_path) return mediaUrl(row.video_clip_path.replace(/\.mp4$/, '.jpg'), 'watch-frames')
  return null
}

function segmentVideoUrl(row: SceneElement): string | null {
  return row.video_clip_path ? mediaUrl(row.video_clip_path, 'watch-frames') : null
}

function diffCategoryColor(cat?: string): string {
  switch (cat) {
    case 'sanitized': return '#ffb300'
    case 'hidden_dialogue': return '#bb86fc'
    case 'acoustic_context': return '#03dac6'
    case 'minor_diff': return '#a0a0a0'
    case 'unknown_diff': return '#a0a0a0'
    default: return '#ffb300'
  }
}

function diffCategorySymbol(cat?: string): string {
  switch (cat) {
    case 'sanitized': return '[!]'
    case 'hidden_dialogue': return '[+]'
    case 'acoustic_context': return '[?]'
    case 'minor_diff': return '[~]'
    case 'unknown_diff': return '[?]'
    default: return '[!]'
  }
}

function diffCategoryLabel(cat?: string): string {
  switch (cat) {
    case 'sanitized': return 'Sanitized'
    case 'hidden_dialogue': return 'Hidden'
    case 'acoustic_context': return 'Occluded'
    case 'minor_diff': return 'Minor Diff'
    case 'unknown_diff': return 'Unknown Diff'
    default: return 'Diff'
  }
}

function annotationDraftStorageKey(reportTitle: string, row: SceneElement): string {
  const asset = reportTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'watch_asset'
  const segment = `${row.index}:${row.timecode}:${row.movie_segment || ''}`.replace(/[^a-zA-Z0-9:._-]+/g, '_')
  return `${WATCH_ANNOTATION_DRAFT_PREFIX}:${asset}:${segment}`
}

function yoloTrackLabelStorageKey(reportTitle: string, row: SceneElement): string {
  const asset = reportTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'watch_asset'
  const segment = `${row.index}:${row.timecode}:${row.movie_segment || ''}`.replace(/[^a-zA-Z0-9:._-]+/g, '_')
  return `${WATCH_YOLO_LABEL_PREFIX}:${asset}:${segment}`
}

function watchAssetUid(reportTitle: string): string {
  return reportTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'watch_asset'
}

function readAnnotationDraft(key: string): Partial<KeyframeAnnotationDraftState> | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<KeyframeAnnotationDraftState>
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function readYoloTrackLabels(key: string): Record<string, WatchYoloTrackLabel> {
  if (typeof window === 'undefined' || !key) return {}
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, WatchYoloTrackLabel>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeYoloTrackLabels(key: string, labels: Record<string, WatchYoloTrackLabel>): void {
  if (typeof window === 'undefined' || !key) return
  try {
    window.localStorage.setItem(key, JSON.stringify(labels))
  } catch {
    // local YOLO labels are operator convenience state; failing closed here
    // leaves the original YOLO track labels visible instead of inventing truth.
  }
}

function yoloTrackDisplayName(trackId: string): string {
  return `YOLO ${trackId.replace(/\s+/g, '_').toUpperCase()}`
}

function yoloBoxInstanceKey(trackId: string, timeSeconds: number): string {
  return `${trackId}@${Math.round(Math.max(0, timeSeconds) * 100)}`
}

function readYoloLabelEvents(value: unknown): WatchYoloLabelEvent[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is WatchYoloLabelEvent => {
    if (!item || typeof item !== 'object') return false
    const record = item as Record<string, unknown>
    return typeof record.track_id === 'string' && typeof record.action === 'string'
  })
}

function yoloLabelEventTime(event: WatchYoloLabelEvent): number | null {
  const time = Number(event.time_seconds)
  return Number.isFinite(time) ? time : null
}

function yoloLabelEventSortValue(event: WatchYoloLabelEvent, index: number): number {
  const time = yoloLabelEventTime(event)
  return (time ?? Number.MAX_SAFE_INTEGER) * 100000 + index
}

function isYoloIdentityStopEvent(event: WatchYoloLabelEvent): boolean {
  return event.action === 'reject_box'
    || event.action === 'reset_box'
    || event.action === 'reset'
    || event.action === 'reject'
    || event.status === 'rejected_box'
    || event.status === 'reset'
    || event.status === 'reject'
}

function upsertYoloLabelEvent(events: WatchYoloLabelEvent[], event: WatchYoloLabelEvent): WatchYoloLabelEvent[] {
  return [
    ...events.filter((existing) => !(
      existing.action === event.action &&
      existing.track_id === event.track_id &&
      (existing.box_key || '') === (event.box_key || '')
    )),
    event,
  ]
}

function latestYoloLabelEventForTrack(
  events: WatchYoloLabelEvent[],
  trackId: string,
  timeSeconds: number,
): WatchYoloLabelEvent | null {
  const boundedTime = Math.max(0, timeSeconds)
  const candidates = events
    .map((event, index) => ({ event, index, time: yoloLabelEventTime(event) }))
    .filter(({ event, time }) => event.track_id === trackId && time != null && time <= boundedTime + 0.011)
    .sort((a, b) => yoloLabelEventSortValue(a.event, a.index) - yoloLabelEventSortValue(b.event, b.index))
  return candidates.length > 0 ? candidates[candidates.length - 1].event : null
}

function yoloLabelFromEvent(event: WatchYoloLabelEvent): WatchYoloTrackLabel | null {
  if (isYoloIdentityStopEvent(event)) return null
  if (!event.character_name || event.character_name === 'Unassigned') return null
  return {
    trackId: event.track_id,
    characterName: event.character_name,
    actorName: event.actor_name || actorForCharacter(event.character_name) || undefined,
    status: 'accepted',
    source: 'human',
    confidence: typeof event.confidence === 'number' ? event.confidence : 1,
    updatedAt: event.created_at || new Date().toISOString(),
  }
}

function yoloSequenceRowFromEvent(event: WatchYoloLabelEvent, index: number): WatchYoloSequenceRow {
  const time = yoloLabelEventTime(event)
  const label = yoloLabelFromEvent(event)
  const isStop = isYoloIdentityStopEvent(event)
  const isReset = event.action === 'reset' || event.action === 'reset_box' || event.status === 'reset'
  return {
    key: `${event.track_id}:${event.box_key || 'track'}:${event.action}:${event.created_at || index}`,
    timeLabel: time == null ? '--' : `${time.toFixed(2)}s`,
    sortValue: (time ?? Number.MAX_SAFE_INTEGER) * 100000 + index,
    source: 'yolo',
    trackId: event.track_id,
    stateLabel: label?.characterName || 'Unassigned',
    detailLabel: isStop
      ? 'holds until next assignment'
      : label?.actorName || actorForCharacter(label?.characterName || '') || 'accepted',
    tone: isStop ? (isReset ? 'reset' : 'stop') : 'accept',
  }
}

function watchSequenceRowsFromAnnotationSession(state: AnnotationSessionState): WatchYoloSequenceRow[] {
  const rows: WatchYoloSequenceRow[] = []
  let index = 0
  for (const characterId of state.trackOrder) {
    const track = state.tracksByCharacterId[characterId]
    if (!track) continue
    for (const keyframe of Object.values(track.keyframesById)) {
      rows.push({
        key: `watch:${keyframe.localId}:keyframe`,
        timeLabel: `${Math.max(0, keyframe.timeSeconds - state.row.segmentStartSeconds).toFixed(2)}s`,
        sortValue: keyframe.timeSeconds * 100000 + index++,
        source: 'watch',
        trackId: track.characterName,
        stateLabel: keyframe.characterName,
        detailLabel: keyframe.actorName || 'keyframe starts/updates held sequence',
        tone: 'accept',
      })
    }
    for (const marker of Object.values(track.offscreenById)) {
      rows.push({
        key: `watch:${marker.localId}:offscreen`,
        timeLabel: `${Math.max(0, marker.timeSeconds - state.row.segmentStartSeconds).toFixed(2)}s`,
        sortValue: marker.timeSeconds * 100000 + index++,
        source: 'watch',
        trackId: track.characterName,
        stateLabel: 'Unassigned',
        detailLabel: `${track.characterName} stops until reassigned`,
        tone: 'stop',
      })
    }
  }
  return rows.sort((a, b) => a.sortValue - b.sortValue)
}

function yoloLabelForOverlay(
  overlay: WatchOverlayPayloadOverlay,
  events: WatchYoloLabelEvent[],
  labels: Record<string, WatchYoloTrackLabel>,
  suggestions: Record<string, WatchYoloTrackLabel>,
  rejections: Record<string, WatchYoloBoxRejection> = {},
  timeSeconds = 0,
): WatchYoloTrackLabel | null {
  const latestEvent = latestYoloLabelEventForTrack(events, overlay.track_id, timeSeconds)
  if (latestEvent) return yoloLabelFromEvent(latestEvent)
  if (rejections[yoloBoxInstanceKey(overlay.track_id, timeSeconds)]) return null
  return labels[overlay.track_id] ?? suggestions[overlay.track_id] ?? null
}

function yoloOverlayWithLabel(
  overlay: WatchOverlayPayloadOverlay,
  label: WatchYoloTrackLabel | null,
): WatchOverlayPayloadOverlay {
  if (!label) {
    return {
      ...overlay,
      identity_candidate: undefined,
      identity_status: 'YOLO_TRACK',
      render_policy: {
        ...overlay.render_policy,
        stroke: 'dashed',
        stroke_color: '#22d3ee',
        fill_opacity: 0.055,
      },
    }
  }

  return {
    ...overlay,
    identity_candidate: {
      name: label.characterName,
      actor_name: label.actorName || undefined,
      status: label.status === 'accepted' ? 'VERIFIED' : 'PROVISIONAL',
      confidence: label.confidence,
      basis: [label.source === 'human' ? 'human_yolo_track_label' : 'memory_qdrant_crop_recall'],
    },
    identity_status: label.status === 'accepted'
      ? 'ACCEPTED'
      : `SUGGESTED${typeof label.confidence === 'number' ? ` ${label.confidence.toFixed(2)}` : ''}`,
    render_policy: {
      ...overlay.render_policy,
      stroke: label.status === 'accepted' ? 'solid' : 'dashed',
      stroke_color: label.characterName === 'Marcus'
        ? '#a78bfa'
        : label.characterName === 'Willie'
          ? '#facc15'
          : '#22d3ee',
      fill_opacity: label.status === 'accepted' ? 0.12 : 0.075,
    },
  }
}

function parseMemorySuggestion(data: WatchIdentitySuggestionResponse): WatchYoloTrackLabel | null {
  const direct = data.suggestion
  if (direct?.character_name) {
    const characterName = direct.character_name
    return {
      trackId: data.track_id || '',
      characterName,
      actorName: direct.actor_name || actorForCharacter(characterName) || undefined,
      status: 'suggested',
      source: 'memory',
      confidence: direct.confidence,
      updatedAt: new Date().toISOString(),
    }
  }

  const suggested = data.memory?.suggestions?.[0]
  if (suggested?.character_name) {
    const characterName = suggested.character_name
    return {
      trackId: data.track_id || '',
      characterName,
      actorName: suggested.actor_name || actorForCharacter(characterName) || undefined,
      status: 'suggested',
      source: 'memory',
      confidence: suggested.confidence,
      updatedAt: new Date().toISOString(),
    }
  }

  const candidates = data.memory?.items ?? []
  for (const item of candidates) {
    const haystack = JSON.stringify(item)
    const match = ENTITY_PATTERNS.find((entry) => entry.pattern.test(haystack))
    if (!match) continue
    const scores = item.scores && typeof item.scores === 'object' ? item.scores as Record<string, unknown> : {}
    const score = typeof scores.total === 'number'
      ? scores.total
      : typeof scores.dense === 'number'
        ? scores.dense
        : typeof data.memory?.confidence === 'number'
          ? data.memory.confidence
          : undefined
    return {
      trackId: data.track_id || '',
      characterName: match.name,
      actorName: actorForCharacter(match.name) || undefined,
      status: 'suggested',
      source: 'memory',
      confidence: typeof score === 'number' && score > 1 ? score / 100 : score,
      updatedAt: new Date().toISOString(),
    }
  }
  return null
}

function annotationOverlaysForRow(reportTitle: string, row: SceneElement): WatchOverlayPayloadOverlay[] {
  const stored = readAnnotationDraft(annotationDraftStorageKey(reportTitle, row))
  if (!stored) return []
  const boxes = [
    ...(Array.isArray(stored.savedBoxes) ? stored.savedBoxes : []),
    ...(stored.draftBbox ? [{
      id: 'draft-bbox',
      bbox: stored.draftBbox,
      characterName: stored.characterName || 'Unassigned',
      actorName: stored.actorName || '',
      status: 'draft' as const,
    }] : []),
  ].filter((box) => Array.isArray(box.bbox) && box.bbox.length === 4)

  if (boxes.length === 0) return []
  const segmentLabel = row.movie_segment || row.timecode
  const start = segmentStartSeconds(segmentLabel)
  const end = segmentEndFromLabel(segmentLabel) || (start + 24)

  return boxes.map((box, index) => {
    const [x1, y1, x2, y2] = box.bbox
    const characterName = box.characterName || stored.characterName || 'Unassigned'
    const actorName = box.actorName || stored.actorName || actorForCharacter(characterName) || ''
    return {
      overlay_id: `annotation-${row.index}-${box.id || index}`,
      segment_id: `annotation-row-${row.index}`,
      track_id: `human-keyframe-${row.index}-${index}`,
      time_range: {
        start_seconds: start,
        end_seconds: end,
      },
      anchor_media_time_seconds: typeof box.timestampSeconds === 'number' ? box.timestampSeconds : typeof stored.capturedFrameSeconds === 'number' ? stored.capturedFrameSeconds : start,
      valid_at_media_time_seconds: typeof box.timestampSeconds === 'number' ? box.timestampSeconds : typeof stored.capturedFrameSeconds === 'number' ? stored.capturedFrameSeconds : start,
      bbox_policy: 'human_keyframe_annotation',
      track_lifecycle_status: box.status === 'receipt_written' ? 'approved_reference' : 'draft_reference',
      stale_after_ms: 0,
      detected_class: 'person',
      classification: box.status === 'receipt_written' ? 'human_approved_keyframe' : 'human_draft_keyframe',
      identity_candidate: {
        name: characterName,
        actor_name: actorName || undefined,
        status: box.status === 'receipt_written' ? 'VERIFIED' : 'PROVISIONAL',
        confidence: box.status === 'receipt_written' ? 1 : 0.7,
        basis: ['human_keyframe_annotation'],
      },
      identity_status: box.status === 'receipt_written' ? 'HUMAN_APPROVED' : 'HUMAN_DRAFT',
      visibility_proof: true,
      bbox_percent: {
        left: x1 * 100,
        top: y1 * 100,
        width: (x2 - x1) * 100,
        height: (y2 - y1) * 100,
      },
      render_policy: {
        stroke: box.status === 'receipt_written' ? 'solid' : 'dashed',
        stroke_color: box.status === 'receipt_written' ? '#03dac6' : '#ffb300',
        fill_opacity: box.status === 'receipt_written' ? 0.1 : 0.12,
        pointer_events: 'none',
      },
    }
  })
}

function writeAnnotationDraft(key: string, value: KeyframeAnnotationDraftState): void {
  if (typeof window === 'undefined') return
  const cappedFrame = value.capturedFrameDataUrl && value.capturedFrameDataUrl.length < 450_000 ? value.capturedFrameDataUrl : null
  try {
    window.localStorage.setItem(key, JSON.stringify({ ...value, capturedFrameDataUrl: cappedFrame }))
  } catch {
    window.localStorage.setItem(key, JSON.stringify({ ...value, capturedFrameDataUrl: null }))
  }
}

function annotationSessionRecordsFromDraft(row: SceneElement, stored: Partial<KeyframeAnnotationDraftState> | null): WatchMemoryRecord[] {
  const boxes = Array.isArray(stored?.savedBoxes) ? stored.savedBoxes : []
  return boxes
    .filter((box) => Array.isArray(box.bbox) && box.bbox.length === 4)
    .map((box, index) => ({
      _id: `watch_keyframe_annotations/${box.id || `local-${row.index}-${index}`}`,
      _key: box.id || `local-${row.index}-${index}`,
      collection: 'watch_keyframe_annotations',
      rowIndex: row.index,
      characterName: box.characterName || stored?.characterName || 'Unassigned',
      actorName: box.actorName || stored?.actorName || '',
      timeSeconds: typeof box.timestampSeconds === 'number'
        ? box.timestampSeconds
        : typeof stored?.capturedFrameSeconds === 'number'
          ? stored.capturedFrameSeconds
          : 0,
      bbox: box.bbox,
    }))
}

function savedBoxesFromAnnotationSession(state: AnnotationSessionState): KeyframeAnnotationBox[] {
  return state.trackOrder.flatMap((characterId) => {
    const track = state.tracksByCharacterId[characterId]
    if (!track) return []
    return Object.values(track.keyframesById)
      .sort((a, b) => a.timeSeconds - b.timeSeconds)
      .map((keyframe) => ({
        id: keyframe.localId,
        bbox: keyframe.bbox,
        characterName: keyframe.characterName,
        actorName: keyframe.actorName || '',
        timestampSeconds: keyframe.timeSeconds,
        status: keyframe.status === 'clean' && keyframe.source === 'memory' ? 'receipt_written' as const : 'draft' as const,
      }))
  })
}

function countAnnotationSessionKeyframes(state: AnnotationSessionState): number {
  return state.trackOrder.reduce((sum, characterId) => {
    const track = state.tracksByCharacterId[characterId]
    return sum + (track ? Object.keys(track.keyframesById).length : 0)
  }, 0)
}

function sessionOverlayToWatchOverlay(row: SceneElement, overlay: VisibleAnnotationOverlay): WatchOverlayPayloadOverlay {
  const [x1, y1, x2, y2] = overlay.bbox
  const exact = overlay.policy === 'exact_keyframe'
  return {
    overlay_id: overlay.overlayId,
    segment_id: `annotation-row-${row.index}`,
    track_id: `human-keyframe-${row.index}-${overlay.characterId}`,
    time_range: {
      start_seconds: overlay.timeSeconds,
      end_seconds: overlay.timeSeconds,
    },
    anchor_media_time_seconds: overlay.timeSeconds,
    valid_at_media_time_seconds: overlay.timeSeconds,
    bbox_policy: exact ? 'human_keyframe_annotation' : overlay.policy,
    track_lifecycle_status: exact ? 'human_keyframe' : 'runtime_derived_from_human_keyframes',
    stale_after_ms: 0,
    detected_class: 'person',
    classification: exact ? 'human_draft_keyframe' : 'runtime_annotation_overlay',
    identity_candidate: {
      name: overlay.characterName,
      actor_name: overlay.actorName || undefined,
      status: exact ? 'PROVISIONAL' : 'INTERPOLATED',
      confidence: exact ? 0.7 : 0.55,
      basis: exact ? ['human_keyframe_annotation'] : ['runtime_interpolation_between_human_keyframes'],
    },
    identity_status: exact ? 'HUMAN_DRAFT' : 'RUNTIME',
    visibility_proof: exact,
    bbox_percent: {
      left: x1 * 100,
      top: y1 * 100,
      width: (x2 - x1) * 100,
      height: (y2 - y1) * 100,
    },
    render_policy: {
      stroke: exact ? 'solid' : 'dashed',
      stroke_color: overlay.isActiveCharacter ? '#FFD700' : '#9ca3af',
      fill_opacity: exact ? 0.06 : 0.035,
      pointer_events: exact ? 'auto' : 'none',
    },
  }
}

function CharacterKeyframeAnnotation({
  row,
  reportTitle,
}: {
  row: SceneElement
  reportTitle: string
}) {
  const candidate = candidateCharacterForRow(row)
  const thumbSrc = sceneThumbUrl(row)
  const videoSrc = segmentVideoUrl(row)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const draftStorageKey = annotationDraftStorageKey(reportTitle, row)
  const [characterName, setCharacterName] = useState(candidate?.name || 'Willie')
  const [actorName, setActorName] = useState(candidate?.actor || '')
  const [capturedFrameDataUrl, setCapturedFrameDataUrl] = useState<string | null>(null)
  const [capturedFrameSeconds, setCapturedFrameSeconds] = useState<number | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [videoDrawMode, setVideoDrawMode] = useState(false)
  const [videoDragStart, setVideoDragStart] = useState<{ x: number; y: number } | null>(null)
  const [videoDraftBbox, setVideoDraftBbox] = useState<NormalizedBbox | null>(null)
  const [draftBbox, setDraftBbox] = useState<NormalizedBbox | null>(null)
  const [savedBoxes, setSavedBoxes] = useState<KeyframeAnnotationBox[]>([])
  const [saveStatus, setSaveStatus] = useState('')
  const [saving, setSaving] = useState(false)
  const annotationFrameSrc = capturedFrameDataUrl || thumbSrc

  useEffect(() => {
    const nextCandidate = candidateCharacterForRow(row)
    const stored = readAnnotationDraft(annotationDraftStorageKey(reportTitle, row))
    const nextCharacterName = stored?.characterName || nextCandidate?.name || 'Willie'
    const nextActorName = stored?.actorName || nextCandidate?.actor || actorForCharacter(nextCharacterName) || ''
    setCharacterName(nextCharacterName)
    setActorName(nextActorName)
    setCapturedFrameDataUrl(stored?.capturedFrameDataUrl || null)
    setCapturedFrameSeconds(typeof stored?.capturedFrameSeconds === 'number' ? stored.capturedFrameSeconds : null)
    setDraftBbox(stored?.draftBbox || null)
    const legacyBboxes = Array.isArray((stored as { savedBboxes?: NormalizedBbox[] } | null)?.savedBboxes)
      ? ((stored as { savedBboxes?: NormalizedBbox[] }).savedBboxes ?? [])
      : []
    const storedBoxes = Array.isArray(stored?.savedBoxes) ? stored.savedBoxes : []
    setSavedBoxes(storedBoxes.length > 0 ? storedBoxes : legacyBboxes.map((bbox, index) => ({
      id: `legacy-${row.index}-${index}`,
      bbox,
      characterName: nextCharacterName,
      actorName: nextActorName,
      status: 'draft',
    })))
    setSaveStatus(stored?.saveStatus || '')
    setDragStart(null)
    setVideoDrawMode(false)
    setVideoDragStart(null)
    setVideoDraftBbox(null)
  }, [row, reportTitle])

  useEffect(() => {
    writeAnnotationDraft(draftStorageKey, {
      characterName,
      actorName,
      capturedFrameDataUrl,
      capturedFrameSeconds,
      draftBbox,
      savedBoxes,
      adjustmentEvents: [],
      saveStatus,
    })
  }, [draftStorageKey, characterName, actorName, capturedFrameDataUrl, capturedFrameSeconds, draftBbox, savedBoxes, saveStatus])

  function onCharacterChange(name: string) {
    setCharacterName(name)
    const actor = actorForCharacter(name)
    if (actor) setActorName(actor)
  }

  function captureVideoFrameDataUrl(): string | null {
    const video = videoRef.current
    if (!video || video.readyState < 2) {
      setSaveStatus('Play or load the segment before capturing a key frame.')
      return null
    }
    const width = video.videoWidth
    const height = video.videoHeight
    if (!width || !height) {
      setSaveStatus('Video frame dimensions are unavailable.')
      return null
    }
    try {
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        setSaveStatus('Could not create capture canvas.')
        return null
      }
      ctx.drawImage(video, 0, 0, width, height)
      return canvas.toDataURL('image/jpeg', 0.86)
    } catch (err) {
      setSaveStatus(`Frame capture failed: ${String(err)}`)
      return null
    }
  }

  function pointerPosition(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      rect,
      point: {
        x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
        y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
      },
    }
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!annotationFrameSrc) return
    const { point } = pointerPosition(event)
    setDragStart(point)
    setDraftBbox(null)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart) return
    const { rect, point } = pointerPosition(event)
    setDraftBbox(normalizeDragBbox(dragStart, point, rect))
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!dragStart) return
    const { rect, point } = pointerPosition(event)
    const bbox = normalizeDragBbox(dragStart, point, rect)
    setDragStart(null)
    if ((bbox[2] - bbox[0]) < 0.02 || (bbox[3] - bbox[1]) < 0.02) {
      setDraftBbox(null)
      setSaveStatus('Draw a larger face or body box.')
      return
    }
    setDraftBbox(bbox)
    setSaveStatus('Draft box ready.')
  }

  function startVideoDrawMode() {
    const video = videoRef.current
    if (!video || video.readyState < 2) {
      setSaveStatus('Load the movie segment before drawing over the video.')
      return
    }
    video.pause()
    setVideoDrawMode(true)
    setVideoDragStart(null)
    setVideoDraftBbox(null)
    setSaveStatus('Draw directly over the paused movie frame.')
  }

  function onVideoPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!videoDrawMode) return
    const video = videoRef.current
    if (!video) return
    video.pause()
    const { point } = pointerPosition(event)
    setVideoDragStart(point)
    setVideoDraftBbox(null)
    setDraftBbox(null)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onVideoPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!videoDrawMode || !videoDragStart) return
    const { rect, point } = pointerPosition(event)
    setVideoDraftBbox(normalizeDragBbox(videoDragStart, point, rect))
  }

  function onVideoPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!videoDrawMode || !videoDragStart) return
    const video = videoRef.current
    const { rect, point } = pointerPosition(event)
    const bbox = normalizeDragBbox(videoDragStart, point, rect)
    setVideoDragStart(null)
    if ((bbox[2] - bbox[0]) < 0.02 || (bbox[3] - bbox[1]) < 0.02) {
      setVideoDraftBbox(null)
      setSaveStatus('Draw a larger face or body box over the movie frame.')
      return
    }
    const dataUrl = captureVideoFrameDataUrl()
    if (!dataUrl || !video) {
      setVideoDraftBbox(null)
      return
    }
    setCapturedFrameDataUrl(dataUrl)
    setCapturedFrameSeconds(video.currentTime)
    setDraftBbox(bbox)
    setVideoDraftBbox(null)
    setVideoDrawMode(false)
    setSaveStatus(`Draft box captured from movie frame at ${video.currentTime.toFixed(2)}s.`)
  }

  function addDraftBox() {
    if (!draftBbox) {
      setSaveStatus('Draw a key-frame box first.')
      return
    }
    const box: KeyframeAnnotationBox = {
      id: `${row.index}-${Date.now()}-${Math.round(draftBbox[0] * 1000)}-${Math.round(draftBbox[1] * 1000)}`,
      bbox: draftBbox,
      characterName,
      actorName,
      status: 'draft',
    }
    setSavedBoxes((current) => [...current, box])
    setDraftBbox(null)
    setSaveStatus(`Added ${box.characterName} box. Approve when the box list is correct.`)
  }

  function deleteBox(id: string) {
    setSavedBoxes((current) => current.filter((box) => box.id !== id))
    setSaveStatus('Removed annotation box from this segment draft.')
  }

  function editBox(box: KeyframeAnnotationBox) {
    setCharacterName(box.characterName)
    setActorName(box.actorName)
    setDraftBbox(box.bbox)
    setSavedBoxes((current) => current.filter((item) => item.id !== box.id))
    setSaveStatus('Loaded box back into the draft controls.')
  }

  async function postAnnotationBox(box: KeyframeAnnotationBox): Promise<KeyframeAnnotationReceipt> {
    const response = await fetch('/api/projects/watch/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        asset_uid: reportTitle.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'watch_asset',
        row_index: row.index,
        timecode: row.timecode,
        movie_segment: row.movie_segment || row.timecode,
        character_name: box.characterName,
        actor_name: box.actorName,
        bbox: box.bbox,
        keyframe_image_data_url: capturedFrameDataUrl || undefined,
        keyframe_time_seconds: capturedFrameSeconds,
        frame_path: row.scene_marker_image_path || '',
        video_clip_path: row.video_clip_path || '',
      }),
    })
    const payload = await response.json() as KeyframeAnnotationReceipt
    if (!response.ok || !payload.ok) {
      return { ok: false, error: payload.error || `Save failed (${response.status})` }
    }
    return payload
  }

  async function saveAnnotation() {
    const boxesToSave = [
      ...savedBoxes.filter((box) => box.status !== 'receipt_written'),
      ...(draftBbox ? [{
        id: `${row.index}-${Date.now()}-inline`,
        bbox: draftBbox,
        characterName,
        actorName,
        status: 'draft' as const,
      }] : []),
    ]
    if (boxesToSave.length === 0) {
      setSaveStatus('Draw or add at least one key-frame box first.')
      return
    }
    setSaving(true)
    setSaveStatus(`Saving ${boxesToSave.length} annotation receipt${boxesToSave.length === 1 ? '' : 's'}...`)
    try {
      const receiptById = new Map<string, string>()
      for (const box of boxesToSave) {
        const payload = await postAnnotationBox(box)
        if (!payload.ok) {
          setSaveStatus(payload.error || 'Save failed')
          return
        }
        receiptById.set(box.id, payload.receipt_path || 'written')
      }
      setSavedBoxes((current) => {
        const next = current.map((box) => receiptById.has(box.id)
          ? { ...box, status: 'receipt_written' as const, receiptPath: receiptById.get(box.id) }
          : box)
        if (draftBbox) {
          next.push({
            id: boxesToSave[boxesToSave.length - 1].id,
            bbox: draftBbox,
            characterName,
            actorName,
            status: 'receipt_written',
            receiptPath: receiptById.get(boxesToSave[boxesToSave.length - 1].id),
          })
        }
        return next
      })
      setDraftBbox(null)
      setSaveStatus(`Receipt: ${boxesToSave.length} annotation${boxesToSave.length === 1 ? '' : 's'} written`)
    } catch (err) {
      setSaveStatus(`Save failed: ${String(err)}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section data-qid="watch:annotation:keyframe" style={{ background: '#10161b', border: '1px solid rgba(3,218,198,0.22)', borderRadius: 8, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 850, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#2dd4bf' }}>Character Keyframe</div>
          <div style={{ fontSize: 11, color: '#7f8ea3', marginTop: 3 }}>{row.movie_segment || row.timecode} · normalized bbox reference</div>
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          style={{
            border: '1px solid rgba(45,212,191,0.28)',
            background: 'rgba(45,212,191,0.10)',
            color: '#2dd4bf',
            borderRadius: 6,
            padding: '7px 10px',
            fontSize: 10,
            fontWeight: 850,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Maximize2 size={13} /> Open
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '86px minmax(0, 1fr)', gap: 10, alignItems: 'center' }}>
        <div style={{ width: 86, aspectRatio: '16 / 9', borderRadius: 6, overflow: 'hidden', background: '#05070a', border: '1px solid rgba(255,255,255,0.08)' }}>
          {annotationFrameSrc ? <img src={annotationFrameSrc} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} /> : null}
        </div>
        <div style={{ minWidth: 0 }}>
          <div title={`${characterName}${actorName ? ` · ${actorName}` : ''}`} style={{ color: '#dce6f1', fontSize: 13, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {characterName}{actorName ? ` · ${actorName}` : ''}
          </div>
          <div style={{ color: '#7f8ea3', fontSize: 11, lineHeight: 1.35, marginTop: 3 }}>
            {savedBoxes.length + (draftBbox ? 1 : 0)} box{savedBoxes.length + (draftBbox ? 1 : 0) === 1 ? '' : 'es'} · {capturedFrameSeconds != null ? `${capturedFrameSeconds.toFixed(2)}s key frame` : 'segment frame'}
          </div>
          <div style={{ color: saveStatus.startsWith('Receipt:') ? '#2dd4bf' : '#8ea0b8', fontSize: 10, lineHeight: 1.35, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {saveStatus || 'Open the annotation workspace to scrub, select a character, and draw a box.'}
          </div>
        </div>
      </div>

      {modalOpen && typeof document !== 'undefined' ? createPortal((
        <div
          data-qid="watch:annotation:modal"
          role="dialog"
          aria-modal="true"
          aria-label="Character annotation workspace"
          style={{ position: 'fixed', inset: 0, zIndex: 2147483647, isolation: 'isolate', background: 'rgba(1,4,8,0.92)', backdropFilter: 'blur(4px)', display: 'grid', placeItems: 'center', padding: 28 }}
        >
          <div style={{ width: 'min(1180px, 96vw)', maxHeight: '92vh', overflow: 'auto', background: '#080d13', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 10, boxShadow: '0 24px 80px rgba(0,0,0,0.58)', padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: '#2dd4bf', fontSize: 11, fontWeight: 900, letterSpacing: '0.14em', textTransform: 'uppercase' }}>Character Annotation Workspace</div>
                <div title={row.movie_segment || row.timecode} style={{ color: '#dce6f1', fontSize: 18, fontWeight: 820, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.movie_segment || row.timecode}</div>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                aria-label="Close annotation workspace"
                style={{ width: 36, height: 36, borderRadius: 7, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)', color: '#dce6f1', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <X size={17} />
              </button>
            </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 8, marginBottom: 10 }}>
        <label style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 10, color: '#7f8ea3', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Character
          <select
            value={characterName}
            onChange={(event) => onCharacterChange(event.target.value)}
            title={characterName}
            style={{
              minWidth: 0,
              width: '100%',
              boxSizing: 'border-box',
              background: '#0b1118',
              border: '1px solid #263241',
              borderRadius: 6,
              color: '#e6edf3',
              padding: '7px 8px',
              fontSize: 12,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {CHARACTER_OPTIONS.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4, fontSize: 10, color: '#7f8ea3', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Actor
          <input
            value={actorName}
            onChange={(event) => setActorName(event.target.value)}
            title={actorName}
            style={{
              minWidth: 0,
              width: '100%',
              boxSizing: 'border-box',
              background: '#0b1118',
              border: '1px solid #263241',
              borderRadius: 6,
              color: '#e6edf3',
              padding: '7px 8px',
              fontSize: 12,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          />
        </label>
      </div>

      {videoSrc ? (
        <div style={{ marginBottom: 10 }}>
          <div
            data-qid="watch:annotation:movie-draw-surface"
            onPointerDown={onVideoPointerDown}
            onPointerMove={onVideoPointerMove}
            onPointerUp={onVideoPointerUp}
            style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', borderRadius: 6, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)', background: '#030507' }}
          >
            <video
              ref={videoRef}
              src={videoSrc}
              controls={!videoDrawMode}
              preload="metadata"
              playsInline
              style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#030507', display: 'block' }}
            />
            {[...savedBoxes, ...(draftBbox ? [{ id: 'active-draft', bbox: draftBbox, characterName, actorName, status: 'draft' as const }] : []), ...(videoDraftBbox ? [{ id: 'active-video-draft', bbox: videoDraftBbox, characterName, actorName, status: 'draft' as const }] : [])].map((box, index) => {
              const isDraft = box.id === 'active-draft' || box.id === 'active-video-draft'
              return (
                <div
                  key={`video-box-${box.id}-${index}`}
                  style={{
                    position: 'absolute',
                    ...bboxStyle(box.bbox),
                    border: isDraft ? '2px dashed #ffb300' : '2px solid #03dac6',
                    background: isDraft ? 'rgba(255,179,0,0.08)' : 'rgba(3,218,198,0.10)',
                    boxShadow: isDraft ? '0 0 0 1px rgba(255,179,0,0.25)' : '0 0 0 1px rgba(3,218,198,0.18)',
                    pointerEvents: 'none',
                    zIndex: 6,
                  }}
                />
              )
            })}
            {[...savedBoxes, ...(draftBbox ? [{ id: 'active-draft', bbox: draftBbox, characterName, actorName, status: 'draft' as const }] : []), ...(videoDraftBbox ? [{ id: 'active-video-draft', bbox: videoDraftBbox, characterName, actorName, status: 'draft' as const }] : [])].map((box, index) => {
              const isDraft = box.id === 'active-draft' || box.id === 'active-video-draft'
              const [x1, y1] = box.bbox
              return (
                <div
                  key={`video-label-${box.id}-${index}`}
                  title={`${box.characterName}${box.actorName ? ` · ${box.actorName}` : ''}`}
                  style={{
                    position: 'absolute',
                    left: `${x1 * 100}%`,
                    top: `${y1 * 100}%`,
                    transform: y1 < 0.12 ? 'translate(0, 2px)' : 'translate(0, -100%)',
                    maxWidth: 'calc(100% - 10px)',
                    background: isDraft ? '#ffb300' : '#03dac6',
                    color: '#00110f',
                    fontSize: 11,
                    lineHeight: '20px',
                    height: 22,
                    padding: '0 8px',
                    fontWeight: 900,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    boxShadow: '0 3px 14px rgba(0,0,0,0.58)',
                    pointerEvents: 'none',
                    zIndex: 30,
                  }}
                >
                  {box.characterName}{box.actorName ? ` · ${box.actorName}` : ''}
                </div>
              )
            })}
            <div
              aria-hidden={!videoDrawMode}
              style={{
                position: 'absolute',
                inset: 0,
                cursor: videoDrawMode ? 'crosshair' : 'default',
                pointerEvents: videoDrawMode ? 'auto' : 'none',
                background: videoDrawMode ? 'rgba(3,7,18,0.08)' : 'transparent',
              }}
            />
              <div style={{ position: 'absolute', top: 10, left: 10, right: 10, zIndex: 40, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, pointerEvents: 'none' }}>
                <span style={{ background: 'rgba(0,0,0,0.76)', border: `1px solid ${videoDrawMode ? 'rgba(255,179,0,0.42)' : 'rgba(45,212,191,0.30)'}`, color: videoDrawMode ? '#ffcf66' : '#2dd4bf', borderRadius: 5, padding: '6px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  {videoDrawMode ? 'Draw over paused movie frame' : `${savedBoxes.length + (draftBbox ? 1 : 0)} keyframe box${savedBoxes.length + (draftBbox ? 1 : 0) === 1 ? '' : 'es'}`}
                </span>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    if (videoDrawMode) {
                      setVideoDrawMode(false)
                      setVideoDragStart(null)
                      setVideoDraftBbox(null)
                      setSaveStatus('Movie-frame draw mode cancelled.')
                    } else {
                      startVideoDrawMode()
                    }
                  }}
                  style={{ pointerEvents: 'auto', border: '1px solid rgba(255,255,255,0.16)', background: 'rgba(0,0,0,0.62)', color: '#dce6f1', borderRadius: 5, padding: '6px 8px', fontSize: 10, fontWeight: 850, cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.06em' }}
                >
                  {videoDrawMode ? 'Cancel' : 'Draw box'}
                </button>
              </div>
          </div>
        </div>
      ) : null}

      {!videoSrc ? (
      <div
        data-qid="watch:annotation:keyframe-canvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16 / 9',
          borderRadius: 6,
          overflow: 'hidden',
          background: '#030507',
          border: '1px solid rgba(255,255,255,0.08)',
          cursor: annotationFrameSrc ? 'crosshair' : 'not-allowed',
          userSelect: 'none',
          touchAction: 'none',
        }}
      >
        {annotationFrameSrc ? <img src={annotationFrameSrc} alt="" draggable={false} style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.88, display: 'block' }} /> : null}
        {[...savedBoxes, ...(draftBbox ? [{ id: 'active-draft', bbox: draftBbox, characterName, actorName, status: 'draft' as const }] : [])].map((box, index) => {
          const isDraft = box.id === 'active-draft'
          return (
            <div
              key={`${box.id}-${index}`}
              style={{
                position: 'absolute',
                ...bboxStyle(box.bbox),
                border: isDraft ? '2px dashed #ffb300' : '2px solid #03dac6',
                background: isDraft ? 'rgba(255,179,0,0.08)' : 'rgba(3,218,198,0.10)',
                boxShadow: isDraft ? '0 0 0 1px rgba(255,179,0,0.25)' : '0 0 0 1px rgba(3,218,198,0.18)',
                pointerEvents: 'none',
                zIndex: 5,
              }}
            />
          )
        })}
        {[...savedBoxes, ...(draftBbox ? [{ id: 'active-draft', bbox: draftBbox, characterName, actorName, status: 'draft' as const }] : [])].map((box, index) => {
          const isDraft = box.id === 'active-draft'
          const [x1, y1] = box.bbox
          return (
            <div
              key={`label-${box.id}-${index}`}
              title={`${box.characterName}${box.actorName ? ` · ${box.actorName}` : ''}`}
              style={{
                position: 'absolute',
                left: `${x1 * 100}%`,
                top: `${y1 * 100}%`,
                transform: y1 < 0.12 ? 'translate(0, 2px)' : 'translate(0, -100%)',
                maxWidth: 'calc(100% - 10px)',
                background: isDraft ? '#ffb300' : '#03dac6',
                color: '#00110f',
                fontSize: 11,
                lineHeight: '20px',
                height: 22,
                padding: '0 8px',
                fontWeight: 900,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                boxShadow: '0 3px 14px rgba(0,0,0,0.58)',
                pointerEvents: 'none',
                zIndex: 30,
              }}
            >
              {box.characterName}{box.actorName ? ` · ${box.actorName}` : ''}
            </div>
          )
        })}
        {!annotationFrameSrc && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: '#7f8ea3', fontSize: 12 }}>No frame available for this row.</div>}
      </div>
      ) : null}

            <div data-qid="watch:annotation:box-list" style={{ marginTop: 12, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, background: 'rgba(255,255,255,0.025)', padding: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
                <div style={{ color: '#9dc6ff', fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Annotation Boxes</div>
                <button
                  type="button"
                  data-qid="watch:annotation:add-box"
                  onClick={addDraftBox}
                  disabled={!draftBbox}
                  style={{
                    border: '1px solid rgba(255,179,0,0.32)',
                    background: draftBbox ? 'rgba(255,179,0,0.12)' : 'rgba(255,255,255,0.035)',
                    color: draftBbox ? '#ffcf66' : '#6b7280',
                    borderRadius: 6,
                    padding: '6px 9px',
                    fontSize: 10,
                    fontWeight: 850,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    cursor: draftBbox ? 'pointer' : 'default',
                  }}
                >
                  Add Box
                </button>
              </div>
              {savedBoxes.length === 0 ? (
                <div style={{ color: '#7f8ea3', fontSize: 11, lineHeight: 1.45 }}>No saved boxes yet. Draw a box on the frame, then add it to the segment draft.</div>
              ) : (
                <div style={{ display: 'grid', gap: 7 }}>
                  {savedBoxes.map((box, index) => (
                    <div key={box.id} data-qid="watch:annotation:box-row" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 8, alignItems: 'center', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, background: 'rgba(0,0,0,0.18)', padding: 8 }}>
                      <div style={{ minWidth: 0 }}>
                        <div title={`${box.characterName}${box.actorName ? ` · ${box.actorName}` : ''}`} style={{ color: '#dce6f1', fontSize: 12, fontWeight: 820, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {index + 1}. {box.characterName}{box.actorName ? ` · ${box.actorName}` : ''}
                        </div>
                        <div title={box.receiptPath || box.status} style={{ color: box.status === 'receipt_written' ? '#2dd4bf' : '#ffcf66', fontSize: 10, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {box.status === 'receipt_written' ? `receipt ${box.receiptPath || 'written'}` : 'draft'}
                        </div>
                      </div>
                      <button
                        type="button"
                        data-qid="watch:annotation:edit-box"
                        onClick={() => editBox(box)}
                        disabled={box.status === 'receipt_written'}
                        style={{ border: '1px solid rgba(157,198,255,0.24)', background: 'rgba(157,198,255,0.07)', color: box.status === 'receipt_written' ? '#536073' : '#9dc6ff', borderRadius: 5, padding: '5px 7px', fontSize: 10, fontWeight: 820, cursor: box.status === 'receipt_written' ? 'default' : 'pointer' }}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        data-qid="watch:annotation:delete-box"
                        onClick={() => deleteBox(box.id)}
                        disabled={box.status === 'receipt_written'}
                        style={{ border: '1px solid rgba(248,113,113,0.24)', background: 'rgba(248,113,113,0.07)', color: box.status === 'receipt_written' ? '#536073' : '#fca5a5', borderRadius: 5, padding: '5px 7px', fontSize: 10, fontWeight: 820, cursor: box.status === 'receipt_written' ? 'default' : 'pointer' }}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 12 }}>
              <div style={{ minWidth: 0, fontSize: 12, lineHeight: 1.45, color: saveStatus.startsWith('Receipt:') ? '#2dd4bf' : '#8fa1b8', wordBreak: 'break-word' }}>
                {saveStatus || (videoSrc ? 'Play or scrub the segment, capture a key frame, draw one or more boxes, then approve the segment annotations.' : 'Draw one or more boxes on this key frame, then approve the segment annotations.')}
              </div>
              <button
                type="button"
                onClick={saveAnnotation}
                disabled={saving || (!draftBbox && savedBoxes.every((box) => box.status === 'receipt_written'))}
                style={{
                  flexShrink: 0,
                  border: '1px solid rgba(45,212,191,0.28)',
                  background: (draftBbox || savedBoxes.some((box) => box.status !== 'receipt_written')) ? 'rgba(45,212,191,0.14)' : 'rgba(255,255,255,0.04)',
                  color: (draftBbox || savedBoxes.some((box) => box.status !== 'receipt_written')) ? '#2dd4bf' : '#6b7280',
                  borderRadius: 7,
                  padding: '9px 12px',
                  fontSize: 11,
                  fontWeight: 900,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  cursor: (draftBbox || savedBoxes.some((box) => box.status !== 'receipt_written')) && !saving ? 'pointer' : 'default',
                }}
              >
                {saving ? 'Saving' : 'Approve Segment'}
              </button>
            </div>
          </div>
        </div>
      ), document.body) : null}
    </section>
  )
}

function OrpheusClipReview({
  row,
  selectedTags,
  setSelectedTags,
}: {
  row: SceneElement
  selectedTags: Set<string>
  setSelectedTags: React.Dispatch<React.SetStateAction<Set<string>>>
}) {
  const videoSrc = segmentVideoUrl(row)
  const thumbSrc = sceneThumbUrl(row)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const segmentLabel = row.movie_segment ?? row.timecode
  const segmentStart = segmentStartSeconds(segmentLabel)
  const segmentEnd = segmentEndFromLabel(segmentLabel)
  const segmentDuration = Math.max(1, Math.round((segmentEnd || segmentStart + 24) - segmentStart))
  const defaultStart = Math.min(segmentDuration - 0.25, Math.max(0, segmentDuration * 0.16))
  const defaultEnd = Math.min(segmentDuration, Math.max(defaultStart + 0.25, segmentDuration * 0.36))
  const [selectionStart, setSelectionStart] = useState(defaultStart)
  const [selectionEnd, setSelectionEnd] = useState(defaultEnd)
  const [currentTime, setCurrentTime] = useState(0)
  const [reviewStatus, setReviewStatus] = useState('')
  const [staging, setStaging] = useState(false)

  useEffect(() => {
    setSelectionStart(defaultStart)
    setSelectionEnd(defaultEnd)
    setCurrentTime(0)
    setReviewStatus('')
  }, [row.index, defaultStart, defaultEnd])

  function clampSelectionStart(value: number) {
    const next = Math.max(0, Math.min(value, selectionEnd - 0.25))
    setSelectionStart(next)
    setReviewStatus(`Start set to ${next.toFixed(2)}s.`)
  }

  function clampSelectionEnd(value: number) {
    const next = Math.min(segmentDuration, Math.max(value, selectionStart + 0.25))
    setSelectionEnd(next)
    setReviewStatus(`End set to ${next.toFixed(2)}s.`)
  }

  function setBoundaryFromPlayhead(boundary: 'start' | 'end') {
    const video = videoRef.current
    const value = video ? video.currentTime : currentTime
    if (boundary === 'start') clampSelectionStart(value)
    else clampSelectionEnd(value)
  }

  async function stageReview() {
    if (selectionEnd <= selectionStart) {
      setReviewStatus('Selection end must be after start.')
      return
    }
    setStaging(true)
    setReviewStatus('Writing Orpheus review receipt...')
    try {
      const response = await fetch('/api/projects/watch/orpheus-reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          row_index: row.index,
          timecode: row.timecode,
          movie_segment: row.movie_segment || row.timecode,
          video_clip_path: row.video_clip_path || '',
          audio_clip_path: row.audio_clip_path || row.audio_path || '',
          scene_marker_image_path: row.scene_marker_image_path || '',
          selection_start_seconds: selectionStart,
          selection_end_seconds: selectionEnd,
          selected_tags: [...selectedTags],
          transcript: row.srt_text || row.text || '',
          source: 'watch_orpheus_review',
        }),
      })
      const payload = await response.json() as OrpheusReviewReceipt
      if (!response.ok || !payload.ok) {
        setReviewStatus(payload.error || `Stage failed (${response.status})`)
        return
      }
      setReviewStatus(`Receipt: ${payload.receipt_path || 'written'}`)
    } catch (err) {
      setReviewStatus(`Stage failed: ${String(err)}`)
    } finally {
      setStaging(false)
    }
  }

  const startPct = (selectionStart / segmentDuration) * 100
  const endPct = (selectionEnd / segmentDuration) * 100
  const currentPct = (currentTime / segmentDuration) * 100
  return (
    <section data-qid="watch:orpheus-review" style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280' }}>Orpheus Clip Review</div>
          <div style={{ fontSize: 18, fontWeight: 820, color: '#e2e8f0', marginTop: 5, fontVariantNumeric: 'tabular-nums' }}>{row.timecode}</div>
        </div>
        <span style={{ color: '#8ea0b8', fontSize: 11, fontWeight: 750, fontVariantNumeric: 'tabular-nums' }}>{selectionStart.toFixed(2)}s - {selectionEnd.toFixed(2)}s</span>
      </div>

      <div style={{ position: 'relative', width: '100%', borderRadius: 6, overflow: 'hidden', background: '#000', border: '1px solid rgba(255,255,255,0.08)' }}>
        {videoSrc ? (
          <video
            ref={videoRef}
            src={videoSrc}
            controls
            preload="metadata"
            playsInline
            onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
            style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', display: 'block' }}
          />
        ) : thumbSrc ? (
          <img src={thumbSrc} alt="" style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', display: 'block', opacity: 0.85 }} />
        ) : (
          <div style={{ aspectRatio: '16 / 9', display: 'grid', placeItems: 'center', color: '#7f8ea3', fontSize: 12 }}>No playable clip for this row.</div>
        )}
      </div>

      <div style={{ position: 'relative', height: 26, marginTop: 10, borderRadius: 999, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: `${startPct}%`, width: `${Math.max(1, endPct - startPct)}%`, top: 0, bottom: 0, background: 'linear-gradient(90deg, rgba(45,212,191,0.28), rgba(78,161,255,0.24))', borderLeft: '2px solid #2dd4bf', borderRight: '2px solid #4ea1ff' }} />
        <div title="Emotion event/playhead" style={{ position: 'absolute', left: `${currentPct}%`, top: 0, bottom: 0, width: 2, background: '#f59e0b', boxShadow: '0 0 12px rgba(245,158,11,0.7)' }} />
      </div>

      <div style={{ display: 'grid', gap: 9, marginTop: 10 }}>
        <label style={{ color: '#8ea0b8', fontSize: 10, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Start {selectionStart.toFixed(2)}s
          <input type="range" min={0} max={segmentDuration} step={0.05} value={selectionStart} onChange={(event) => clampSelectionStart(Number(event.target.value))} style={{ width: '100%' }} />
        </label>
        <label style={{ color: '#8ea0b8', fontSize: 10, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          End {selectionEnd.toFixed(2)}s
          <input type="range" min={0} max={segmentDuration} step={0.05} value={selectionEnd} onChange={(event) => clampSelectionEnd(Number(event.target.value))} style={{ width: '100%' }} />
        </label>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        <button type="button" onClick={() => setBoundaryFromPlayhead('start')} style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, background: 'rgba(255,255,255,0.05)', color: '#dce6f1', padding: '6px 8px', fontSize: 10, fontWeight: 800, cursor: 'pointer' }}>Set start from playhead</button>
        <button type="button" onClick={() => setBoundaryFromPlayhead('end')} style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, background: 'rgba(255,255,255,0.05)', color: '#dce6f1', padding: '6px 8px', fontSize: 10, fontWeight: 800, cursor: 'pointer' }}>Set end from playhead</button>
      </div>

      <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginTop: 14, marginBottom: 9 }}>Emotion Tags</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {EMOTION_TAGS.map((tag) => {
          const active = selectedTags.has(tag)
          return (
            <button key={tag} type="button" onClick={() => {
              const next = new Set(selectedTags)
              if (next.has(tag)) next.delete(tag); else next.add(tag)
              setSelectedTags(next)
            }} style={{
              padding: '5px 10px', borderRadius: 999, border: active ? '1px solid rgba(45,212,191,0.3)' : '1px solid rgba(255,255,255,0.08)',
              background: active ? 'rgba(45,212,191,0.15)' : 'rgba(255,255,255,0.04)',
              color: active ? '#2dd4bf' : '#6b7280', fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer',
            }}>{tag}</button>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="button" onClick={stageReview} disabled={staging} style={{ flex: 1, padding: '9px 0', borderRadius: 6, border: '1px solid rgba(45,212,191,0.25)', background: '#0f3d36', color: '#2dd4bf', fontSize: 11, fontWeight: 700, cursor: staging ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}><NotebookPen size={12} /> {staging ? 'Staging' : 'Stage Review'}</button>
        <button type="button" style={{ flex: 1, padding: '9px 0', borderRadius: 6, border: '1px solid rgba(248,113,113,0.25)', background: '#3f1818', color: '#f87171', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>Reject</button>
      </div>
      <div style={{ marginTop: 8, color: reviewStatus.startsWith('Receipt:') ? '#2dd4bf' : '#7f8ea3', fontSize: 10, lineHeight: 1.4, wordBreak: 'break-word' }}>
        {reviewStatus || 'Scrub around the emotion, set exact boundaries, choose tags, then stage a reviewed Orpheus candidate.'}
      </div>
    </section>
  )
}

function readStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  const value = window.localStorage.getItem(key)
  if (value === 'true') return true
  if (value === 'false') return false
  return fallback
}

function readStoredWatchTab(): 'agent' | 'annotation' {
  if (typeof window === 'undefined') return 'agent'
  return window.localStorage.getItem(WATCH_ACTIVE_TAB_KEY) === 'annotation' ? 'annotation' : 'agent'
}

function readClipRowFromHash(): number | null {
  if (typeof window === 'undefined') return null
  const [, query = ''] = window.location.hash.split('?')
  if (!query) return null
  const value = new URLSearchParams(query).get('clipRow')
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function writeClipRowToHash(rowIndex: number | null): void {
  if (typeof window === 'undefined') return
  const [path = '#watch', query = ''] = window.location.hash.split('?')
  const params = new URLSearchParams(query)
  if (rowIndex == null) {
    params.delete('clipRow')
  } else {
    params.set('clipRow', String(rowIndex))
  }
  const nextQuery = params.toString()
  const nextHash = `${path || '#watch'}${nextQuery ? `?${nextQuery}` : ''}`
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`)
  }
}

export function WatchReportView({
  reportPath = '/tmp/watch-wex5uxs_/report.json',
  answerModel = 'Qwen/Qwen3.6-27B-TEE',
}: {
  reportPath?: string
  answerModel?: string
}): JSX.Element {
  const [report, setReport] = useState<WatchReport | null>(null)
  const [loadError, setLoadError] = useState('')
  const [overlayPayload, setOverlayPayload] = useState<WatchOverlayPayload | null>(null)
  const [overlayPayloadError, setOverlayPayloadError] = useState('')
  const [searchText, setSearchText] = useState('')
  const [selectedRow, setSelectedRow] = useState<number | null>(null)
  const [density, setDensity] = useState<'compact' | 'standard' | 'expanded'>('standard')
  const [showDivergencesOnly, setShowDivergencesOnly] = useState(false)
  const [activeDiffCategory, setActiveDiffCategory] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'agent' | 'annotation'>(() => readStoredWatchTab())
  const [sidebarWidth, setSidebarWidth] = useState(340)
  const [leftRailMode, setLeftRailMode] = useState<LeftRailMode>('library')
  const [leftRailCollapsed, setLeftRailCollapsed] = useState(() => readStoredBoolean(WATCH_LEFT_COLLAPSED_KEY, false))
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(() => readStoredBoolean(WATCH_RIGHT_COLLAPSED_KEY, false))
  const [assetFilterKind, setAssetFilterKind] = useState<AssetKind>('all')
  const [assetLibraryQuery, setAssetLibraryQuery] = useState('')
  const [pendingSource, setPendingSource] = useState('')
  const [assetIngestOpen, setAssetIngestOpen] = useState(false)
  const [ingestPipelineOpen, setIngestPipelineOpen] = useState(false)
  const [ingestJob, setIngestJob] = useState<WatchIngestJob | null>(null)
  const [ingestError, setIngestError] = useState('')
  const [auditRunning, setAuditRunning] = useState(false)
  const [auditStepIndex, setAuditStepIndex] = useState(0)
  const [expandedClip, setExpandedClip] = useState<{ src: string; segment: string; timecode: string; rowIndex: number; entities: string[] } | null>(null)
  const clipModalVideoRef = useRef<HTMLVideoElement | null>(null)
  const [clipModalManualDrawEnabled, setClipModalManualDrawEnabled] = useState(false)
  const [clipModalDrawMode, setClipModalDrawMode] = useState(false)
  const [clipModalDragStart, setClipModalDragStart] = useState<{ x: number; y: number } | null>(null)
  const [clipModalDraftBbox, setClipModalDraftBbox] = useState<NormalizedBbox | null>(null)
  const [clipModalAnnotationRevision, setClipModalAnnotationRevision] = useState(0)
  const [clipModalYoloLabelRevision, setClipModalYoloLabelRevision] = useState(0)
  const [clipModalSelectedYoloTrackId, setClipModalSelectedYoloTrackId] = useState<string | null>(null)
  const [clipModalYoloLabels, setClipModalYoloLabels] = useState<Record<string, WatchYoloTrackLabel>>({})
  const [clipModalYoloBoxRejections, setClipModalYoloBoxRejections] = useState<Record<string, WatchYoloBoxRejection>>({})
  const [clipModalYoloLabelEvents, setClipModalYoloLabelEvents] = useState<WatchYoloLabelEvent[]>([])
  const [clipModalMemorySuggestions, setClipModalMemorySuggestions] = useState<Record<string, WatchYoloTrackLabel>>({})
  const [clipModalYoloStatus, setClipModalYoloStatus] = useState('')
  const [clipModalCharacterName, setClipModalCharacterName] = useState('')
  const [clipModalActorName, setClipModalActorName] = useState('')
  const [clipModalPlaybackSeconds, setClipModalPlaybackSeconds] = useState(0)
  const [clipModalDurationSeconds, setClipModalDurationSeconds] = useState(0)
  const [clipModalPaused, setClipModalPaused] = useState(false)
  const [clipModalSelectedOverlayId, setClipModalSelectedOverlayId] = useState<string | null>(null)
  const [clipModalResizeState, setClipModalResizeState] = useState<{ overlayId: string; handle: BboxResizeHandle; startPoint: { x: number; y: number }; startBbox: NormalizedBbox } | null>(null)
  const [clipModalMoveState, setClipModalMoveState] = useState<{ overlayId: string; startPoint: { x: number; y: number }; startBbox: NormalizedBbox } | null>(null)
  const [annotationSession, annotationDispatch] = useReducer(
    annotationSessionReducer,
    EMPTY_ANNOTATION_SESSION_ROW,
    createInitialAnnotationSession,
  )
  const clipModalDrawRafRef = useRef<number | null>(null)
  const clipModalMoveRafRef = useRef<number | null>(null)
  const clipModalResizeRafRef = useRef<number | null>(null)
  const [activePlaybackRow, setActivePlaybackRow] = useState<number | null>(null)
  const [pauseOnDivergence, setPauseOnDivergence] = useState(true)
  const [pausedDivergenceRows, setPausedDivergenceRows] = useState<Set<number>>(() => new Set())
  const [forensicPause, setForensicPause] = useState<{ rowIndex: number; timecode: string; label: string; detail: string } | null>(null)
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set(['LAUGH', 'CHUCKLE']))
  const [resolutionHub, setResolutionHub] = useState<ResolutionHubState | null>(null)
  const [resolutionNotes, setResolutionNotes] = useState<string[]>([])

  useEffect(() => {
    fetch(`/api/projects/watch/report?path=${encodeURIComponent(reportPath)}`)
      .then((r) => r.json())
      .then((data) => setReport(data))
      .catch((err) => setLoadError(String(err)))
  }, [reportPath])

  useEffect(() => {
    fetch('/api/projects/watch/overlay-payload')
      .then((r) => {
        if (!r.ok) throw new Error(`overlay payload HTTP ${r.status}`)
        return r.json()
      })
      .then((data) => {
        if (data?.schema_version !== 'watch.ui_overlay_payload.v1') {
          throw new Error('unexpected Watch overlay payload schema')
        }
        setOverlayPayload(data)
        setOverlayPayloadError('')
      })
      .catch((err) => {
        setOverlayPayload(null)
        setOverlayPayloadError(err instanceof Error ? err.message : String(err))
      })
  }, [])

  useEffect(() => {
    window.localStorage.setItem(WATCH_LEFT_COLLAPSED_KEY, String(leftRailCollapsed))
  }, [leftRailCollapsed])

  useEffect(() => {
    window.localStorage.setItem(WATCH_RIGHT_COLLAPSED_KEY, String(rightSidebarCollapsed))
  }, [rightSidebarCollapsed])

  useEffect(() => {
    window.localStorage.setItem(WATCH_ACTIVE_TAB_KEY, activeTab)
  }, [activeTab])

  useEffect(() => () => {
    if (clipModalDrawRafRef.current !== null) window.cancelAnimationFrame(clipModalDrawRafRef.current)
    if (clipModalMoveRafRef.current !== null) window.cancelAnimationFrame(clipModalMoveRafRef.current)
    if (clipModalResizeRafRef.current !== null) window.cancelAnimationFrame(clipModalResizeRafRef.current)
  }, [])

  useEffect(() => {
    const handleEntityFilter = (event: Event) => {
      const detail = (event as CustomEvent<{ entity?: string }>).detail
      const entity = typeof detail?.entity === 'string' ? detail.entity.trim() : ''
      if (!entity) return
      setActiveDiffCategory(null)
      setShowDivergencesOnly(false)
      setSearchText(entity)
      setActiveTab('agent')
    }
    window.addEventListener('watch:entity-filter', handleEntityFilter)
    return () => window.removeEventListener('watch:entity-filter', handleEntityFilter)
  }, [])

  const reportWithDiff = useMemo((): WatchReport | null => {
    if (!report) return null
    if (report.diff_intelligence) return report

    const enriched: WatchReport = JSON.parse(JSON.stringify(report))
    const rows = enriched.scene_elements
    const anomalies: DiffIntelligence['anomalies'] = []
    const cc: Record<string, number> = { sanitized: 0, hidden_dialogue: 0, acoustic_context: 0, minor_diff: 0, unknown_diff: 0 }
    const charMap = new Map<string, CharacterIntel>()

    for (const row of rows) {
      const srt = (row.srt_text ?? '').trim()
      const txt = (row.text ?? '').trim()
      const bothNoTranscript = srt === 'No transcript in this segment' && txt === 'No transcript in this segment'
      if (!srt && !txt) continue
      if (bothNoTranscript) continue
      if (srt === txt) continue

      const srtNoTranscript = srt === 'No transcript in this segment'
      const txtNoTranscript = txt === 'No transcript in this segment'
      const srtParenthetical = /^\([A-Z ]+\)$/.test(srt)
      const srtWords = new Set(srt.toLowerCase().split(/\s+/))
      const txtWords = new Set(txt.toLowerCase().split(/\s+/))
      const intersection = new Set([...srtWords].filter(w => txtWords.has(w)))
      const jaccard = intersection.size / Math.max(srtWords.size + txtWords.size - intersection.size, 1)
      const wordRatio = Math.max(txt.split(/\s+/).length, srt.split(/\s+/).length) / Math.min(txt.split(/\s+/).length, srt.split(/\s+/).length)

      let category: DiffInfo['category'] = 'unknown_diff'
      let confidence = 0.5
      let detail = ''

      if (srtNoTranscript && !txtNoTranscript) {
        category = 'hidden_dialogue'
        confidence = 0.8
        detail = `Whisper caught dialogue SRT omitted entirely: "${txt.slice(0, 60)}"`
      } else if (srtParenthetical && txtNoTranscript) {
        category = 'acoustic_context'
        confidence = 0.85
        detail = `SRT captured audio cue "${srt}" but Whisper detected no speech`
      } else if (txtNoTranscript && !srtParenthetical) {
        category = 'acoustic_context'
        confidence = 0.7
        detail = `SRT has dialogue but Whisper returned no transcript`
      } else if (jaccard < 0.15 && wordRatio > 1.8) {
        category = 'sanitized'
        confidence = 0.8
        const longer = txt.length > srt.length ? 'Whisper' : 'SRT'
        const shorter = txt.length > srt.length ? 'SRT' : 'Whisper'
        detail = `${longer} text is ${wordRatio.toFixed(1)}× longer — ${shorter} may have been sanitized or condensed`
      } else if (jaccard < 0.4) {
        category = 'sanitized'
        confidence = 0.65
        detail = `Significant wording difference (${(jaccard * 100).toFixed(0)}% similarity) — content may have been edited`
      } else {
        category = 'minor_diff'
        confidence = 0.5
        detail = `Minor wording variation (${(jaccard * 100).toFixed(0)}% similarity)`
      }

      row.diff_info = { category, confidence, detail }
      cc[category]++
      anomalies.push({ index: row.index, timecode: row.timecode, category, confidence, detail })

      const speaker = extractCharacter(srt) || extractCharacter(txt)
      if (speaker) {
        let ci = charMap.get(speaker)
        if (!ci) {
          ci = { name: speaker, scene_count: 0, divergence_count: 0, top_divergences: [], insight: '' }
          charMap.set(speaker, ci)
        }
        ci.scene_count++
        ci.divergence_count++
        ci.top_divergences.push({ timecode: row.timecode, category, detail: detail.slice(0, 80) })
      }
    }

    const diffCount = anomalies.length
    const character_intel: CharacterIntel[] = [...charMap.values()].map(ci => {
      ci.top_divergences = ci.top_divergences.slice(0, 3)
      const actor = actorForCharacter(ci.name)
      ci.insight = actor
        ? `${ci.name} (${actor}) — ${ci.divergence_count > 1 ? `${ci.divergence_count} divergences` : '1 divergence'}`
        : `${ci.name} — ${ci.divergence_count > 1 ? `${ci.divergence_count} divergences` : '1 divergence'}`
      return ci
    }).sort((a, b) => b.divergence_count - a.divergence_count)

    enriched.diff_intelligence = {
      overall_diff_percentage: rows.length > 0 ? Math.round((diffCount / rows.length) * 100) : 0,
      category_counts: cc,
      anomaly_count: diffCount,
      anomalies,
      character_intel,
      takeaways: [
        cc.sanitized > 0 ? `${cc.sanitized} sanitized — SRT toned down raw language vs Whisper` : '',
        cc.hidden_dialogue > 0 ? `${cc.hidden_dialogue} hidden — Whisper caught dialogue SRT omitted entirely` : '',
        cc.acoustic_context > 0 ? `${cc.acoustic_context} occluded — SRT captured audio cues Whisper missed` : '',
        cc.minor_diff > 0 ? `${cc.minor_diff} minor wording variations` : '',
      ].filter(Boolean),
    }
    return enriched
  }, [report])

  const ingestStages = useMemo((): IngestStage[] => {
    const rows = reportWithDiff?.scene_elements ?? []
    const frameCount = rows.filter((row) => sceneThumbUrl(row)).length
    const clipCount = rows.filter((row) => segmentVideoUrl(row)).length
    const srtCount = rows.filter((row) => !isEmptyTranscript(row.srt_text)).length
    const whisperCount = rows.filter((row) => !isEmptyTranscript(row.text)).length
    const visualCount = rows.filter((row) => row.visual_description_status === 'described' || Boolean(row.visual_description?.trim())).length
    const anomalyCount = reportWithDiff?.diff_intelligence?.anomaly_count ?? 0
    const rowCount = rows.length
    return [
      {
        id: 'source',
        label: 'Source loaded',
        detail: reportWithDiff ? `${reportWithDiff.watch_report.title || 'Current Watch report'}` : 'No report loaded',
        status: reportWithDiff ? 'complete' : 'pending',
      },
      {
        id: 'frames',
        label: 'Frame extraction',
        detail: `${frameCount}/${rowCount} rows have frames`,
        status: rowCount > 0 && frameCount > 0 ? 'complete' : 'blocked',
      },
      {
        id: 'clips',
        label: 'Movie segments',
        detail: `${clipCount}/${rowCount} rows have playable clips`,
        status: rowCount > 0 && clipCount > 0 ? 'complete' : 'blocked',
      },
      {
        id: 'captions',
        label: 'SRT stream',
        detail: `${srtCount}/${rowCount} rows include SRT text`,
        status: rowCount > 0 && srtCount > 0 ? 'complete' : 'blocked',
      },
      {
        id: 'whisper',
        label: 'Audio audit',
        detail: `${whisperCount}/${rowCount} rows include Whisper text`,
        status: rowCount > 0 && whisperCount > 0 ? 'complete' : 'blocked',
      },
      {
        id: 'entities',
        label: 'VLM/entities',
        detail: `${visualCount}/${rowCount} rows have visual descriptions · ${anomalyCount} diffs`,
        status: rowCount > 0 && visualCount > 0 ? 'complete' : 'blocked',
      },
      {
        id: 'ingest-api',
        label: 'Ingest API',
        detail: `${WATCH_INGEST_CONTRACT} ready for source jobs`,
        status: 'complete',
      },
    ]
  }, [reportWithDiff])

  const assetLibraryItems = useMemo((): AssetLibraryItem[] => {
    if (!reportWithDiff) return []
    const rows = reportWithDiff.scene_elements
    const frameCount = rows.filter((row) => sceneThumbUrl(row)).length
    const clipCount = rows.filter((row) => segmentVideoUrl(row)).length
    const srtCount = rows.filter((row) => !isEmptyTranscript(row.srt_text)).length
    const whisperCount = rows.filter((row) => !isEmptyTranscript(row.text)).length
    const visualCount = rows.filter((row) => row.visual_description_status === 'described' || Boolean(row.visual_description?.trim())).length
    const availableSignals = rows.length > 0
      ? [frameCount, clipCount, srtCount, whisperCount, visualCount].reduce((sum, count) => sum + (count > 0 ? 1 : 0), 0)
      : 0
    const diffPercent = reportWithDiff.diff_intelligence?.overall_diff_percentage ?? 0
    return [
      {
        id: `watch-report:${reportPath}`,
        kind: 'cinema',
        title: reportWithDiff.watch_report.title || 'Current Watch report',
        subtitle: `${rows.length} rows · ${frameCount} frames · ${clipCount} clips`,
        statusLabel: `${diffPercent}% diff`,
        diffPercent,
        auditProgress: Math.round((availableSignals / 5) * 100),
        selected: true,
      },
    ]
  }, [reportPath, reportWithDiff])

  const visibleAssetLibraryItems = useMemo(() => {
    const query = assetLibraryQuery.trim().toLowerCase()
    return assetLibraryItems.filter((asset) => {
      if (assetFilterKind !== 'all' && asset.kind !== assetFilterKind) return false
      if (!query) return true
      return [asset.title, asset.subtitle, asset.statusLabel, ASSET_KIND_META[asset.kind].label].join(' ').toLowerCase().includes(query)
    })
  }, [assetFilterKind, assetLibraryItems, assetLibraryQuery])

  const activeIngestStages = ingestJob?.stages ?? ingestStages
  const ingestCompleteCount = activeIngestStages.filter((stage) => stage.status === 'complete').length
  const ingestStageProgress = Math.round((ingestCompleteCount / Math.max(1, activeIngestStages.length)) * 100)
  useEffect(() => {
    if (!ingestJob?.job_id || !['queued', 'running'].includes(ingestJob.status)) return undefined
    const poll = window.setInterval(() => {
      fetch(`/api/projects/watch/ingest-jobs/${encodeURIComponent(ingestJob.job_id)}`)
        .then((response) => response.json())
        .then((payload) => {
          if (payload?.job) setIngestJob(payload.job)
        })
        .catch((err) => setIngestError(String(err)))
    }, 1400)
    return () => window.clearInterval(poll)
  }, [ingestJob?.job_id, ingestJob?.status])

  useEffect(() => {
    if (!auditRunning) return undefined
    const interval = window.setInterval(() => {
      setAuditStepIndex((current) => Math.min(current + 1, AUDIT_STEPS.length - 1))
    }, 850)
    const done = window.setTimeout(() => {
      setAuditRunning(false)
      setShowDivergencesOnly(true)
      setActiveTab('agent')
      const firstAnomaly = reportWithDiff?.diff_intelligence?.anomalies[0]
      if (firstAnomaly) setSelectedRow(firstAnomaly.index)
    }, AUDIT_STEPS.length * 850 + 250)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(done)
    }
  }, [auditRunning, reportWithDiff])

  const filteredResult = useMemo(() => {
    if (!reportWithDiff?.scene_elements) return { rows: [] as SceneElement[], compactSkippedRows: 0 }
    let rows = reportWithDiff.scene_elements.filter((row) => rowMatchesSearch(row, searchText))
    if (showDivergencesOnly) {
      rows = rows.filter((row) => !!row.diff_info)
    }
    if (activeDiffCategory) {
      rows = rows.filter((row) => row.diff_info?.category === activeDiffCategory)
    }
    const compactSkippedRows = density === 'compact' ? rows.filter((row) => !row.diff_info).length : 0
    if (density === 'compact') {
      rows = rows.filter((row) => !!row.diff_info)
    }
    return { rows, compactSkippedRows }
  }, [activeDiffCategory, density, reportWithDiff, searchText, showDivergencesOnly])

  const filteredRows = filteredResult.rows
  const compactSkippedRows = filteredResult.compactSkippedRows
  const movieDurationSeconds = useMemo(() => {
    if (!reportWithDiff?.scene_elements.length) return 1
    return Math.max(1, ...reportWithDiff.scene_elements.map(segmentEndSeconds))
  }, [reportWithDiff])

  function isolateDiffCategory(category: string): void {
    setAuditRunning(true)
    setAuditStepIndex(0)
    setActiveTab('agent')
    setActiveDiffCategory(category)
    setShowDivergencesOnly(true)
    setSearchText('')
  }

  function clearForensicFilters(): void {
    setActiveDiffCategory(null)
    setShowDivergencesOnly(false)
    setSearchText('')
  }

  function focusAuditRow(rowIndex: number): void {
    setSelectedRow(rowIndex)
    document.querySelector(`[data-watch-row-index="${rowIndex}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function openResolutionHub(row: SceneElement, entity: string): void {
    if (!row.diff_info) return
    setSelectedRow(row.index)
    setActiveTab('annotation')
    setResolutionHub({
      rowIndex: row.index,
      timecode: row.timecode,
      entity,
      sourceText: stripWhisperSource(row.srt_text ?? row.text ?? ''),
      verifiedText: actorForCharacter(entity) ? `${entity} — portrayed by ${actorForCharacter(entity)}` : `${entity} — verified movie-domain entity`,
      diffLabel: diffCategoryLabel(row.diff_info.category),
    })
  }

  function appendResolutionNote(action: 'batch_resolve' | 'mark_nominal'): void {
    if (!resolutionHub) return
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const label = action === 'batch_resolve' ? 'Batch resolve all' : 'Marked nominal'
    setResolutionNotes((current) => [
      `${timestamp} ${label}: ${resolutionHub.entity} at ${resolutionHub.timecode}`,
      ...current,
    ].slice(0, 8))
  }

  function logClipModalAuditEvent(eventName: string, payload: { boxId?: string; trackId?: string; characterName?: string; actorName?: string; timestamp?: number }): void {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const subject = payload.boxId || payload.trackId || 'clip-modal'
    const detail = payload.characterName ? ` ${payload.characterName}${payload.actorName ? ` (${payload.actorName})` : ''}` : ''
    const time = typeof payload.timestamp === 'number' ? ` at ${secondsToClock(payload.timestamp)}` : ''
    setResolutionNotes((current) => [
      `${timestamp} ${eventName}: ${subject}${detail}${time}`,
      ...current,
    ].slice(0, 8))
  }

  function viewCharacterSegments(name: string): void {
    setActiveDiffCategory(null)
    setShowDivergencesOnly(false)
    setSearchText(name)
  }

  function viewCharacterEvidence(character: CharacterIntel): void {
    const firstTimecode = character.top_divergences[0]?.timecode
    const row = reportWithDiff?.scene_elements.find((candidate) => (
      !!candidate.diff_info &&
      (!firstTimecode || candidate.timecode === firstTimecode) &&
      [candidate.text, candidate.srt_text, candidate.movie_segment].some((value) => value?.toLowerCase().includes(character.name.toLowerCase()))
    )) ?? reportWithDiff?.scene_elements.find((candidate) => (
      !!candidate.diff_info &&
      [candidate.text, candidate.srt_text, candidate.movie_segment].some((value) => value?.toLowerCase().includes(character.name.toLowerCase()))
    ))
    if (row) {
      setSelectedRow(row.index)
      setActiveDiffCategory(null)
      setShowDivergencesOnly(true)
      setSearchText(character.name)
    }
  }

  function openExpandedClipForRow(row: SceneElement): void {
    const clipSrc = segmentVideoUrl(row)
    if (!clipSrc) return
    setSelectedRow(row.index)
    setActivePlaybackRow(row.index)
    setExpandedClip({
      src: clipSrc,
      segment: row.movie_segment ?? row.timecode,
      timecode: row.timecode,
      rowIndex: row.index,
      entities: sceneEntities(row),
    })
    writeClipRowToHash(row.index)
  }

  function closeExpandedClip(): void {
    setExpandedClip(null)
    setClipModalManualDrawEnabled(false)
    setClipModalDrawMode(false)
    setClipModalDragStart(null)
    setClipModalDraftBbox(null)
    setClipModalSelectedYoloTrackId(null)
    setClipModalMemorySuggestions({})
    setClipModalYoloStatus('')
    writeClipRowToHash(null)
  }

	  function clipModalPointerPosition(event: React.PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      rect,
      point: {
        x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
        y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
      },
    }
  }

	  function onClipModalPointerDown(event: React.PointerEvent<HTMLDivElement>): void {
    if (!clipModalManualDrawEnabled) return
	    event.preventDefault()
	    event.stopPropagation()
	    const { point } = clipModalPointerPosition(event)
	    setClipModalDrawMode(true)
	    setClipModalSelectedOverlayId(null)
	    setClipModalDragStart(point)
	    setClipModalDraftBbox(null)
	    event.currentTarget.setPointerCapture(event.pointerId)
	  }

	  function onClipModalPointerMove(event: React.PointerEvent<HTMLDivElement>): void {
	    if (!clipModalManualDrawEnabled || !clipModalDragStart) return
	    event.preventDefault()
	    event.stopPropagation()
	    const { rect, point } = clipModalPointerPosition(event)
	    const nextBbox = snapBboxEdges(normalizeDragBbox(clipModalDragStart, point, rect))
	    if (clipModalDrawRafRef.current !== null) window.cancelAnimationFrame(clipModalDrawRafRef.current)
	    clipModalDrawRafRef.current = window.requestAnimationFrame(() => {
	      setClipModalDraftBbox(nextBbox)
	      clipModalDrawRafRef.current = null
	    })
	  }

	  function onClipModalPointerUp(event: React.PointerEvent<HTMLDivElement>): void {
	    if (!clipModalManualDrawEnabled || !clipModalDragStart || !expandedClipRow || !reportWithDiff) return
	    event.preventDefault()
	    event.stopPropagation()
	    const { rect, point } = clipModalPointerPosition(event)
	    const bbox = snapBboxEdges(normalizeDragBbox(clipModalDragStart, point, rect))
	    setClipModalDragStart(null)
	    setClipModalDrawMode(false)
	    setClipModalDraftBbox(null)
    if ((bbox[2] - bbox[0]) < 0.02 || (bbox[3] - bbox[1]) < 0.02) return

    const candidate = candidateCharacterForRow(expandedClipRow)
    const fallbackEntityName = expandedClip?.entities.find((entity) => actorForCharacter(entity)) || candidate?.name || expandedClip?.entities[0] || 'Unassigned'
    const entityName = clipModalCharacterName.trim() || fallbackEntityName
    const actorName = clipModalActorName.trim() || actorForCharacter(entityName) || candidate?.actor || ''
    const timestampSeconds = clipModalVideoRef.current?.currentTime ?? clipModalPlaybackSeconds
    annotationDispatch(annotationSessionActions.selectCharacter(entityName, actorName || undefined))
    annotationDispatch(annotationSessionActions.setPlaybackTime(timestampSeconds))
    annotationDispatch(annotationSessionActions.commitDraw(bbox))
    setClipModalSelectedOverlayId(null)
  }

  function clipModalAnnotationStorage(): { key: string; stored: Partial<KeyframeAnnotationDraftState>; row: SceneElement } | null {
    if (!expandedClipRow || !reportWithDiff) return null
    const key = annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    return { key, stored: readAnnotationDraft(key) || {}, row: expandedClipRow }
  }

  function clipModalYoloLabelStorage(): { key: string; labels: Record<string, WatchYoloTrackLabel>; row: SceneElement } | null {
    if (!expandedClipRow || !reportWithDiff) return null
    const key = yoloTrackLabelStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    return { key, labels: clipModalYoloLabels, row: expandedClipRow }
  }

  function selectedYoloBoxKey(timeSeconds = clipModalPlaybackSeconds): string | null {
    if (!clipModalSelectedYoloTrackId) return null
    return yoloBoxInstanceKey(clipModalSelectedYoloTrackId, timeSeconds)
  }

  function annotationBoxIdFromOverlayId(overlayId: string, row: SceneElement): string | null {
    const prefix = `annotation-${row.index}-`
    return overlayId.startsWith(prefix) ? overlayId.slice(prefix.length) : null
  }

  function writeClipModalAnnotationUpdate(next: Partial<KeyframeAnnotationDraftState>): void {
	    const storage = clipModalAnnotationStorage()
	    if (!storage) return
	    const current = storage.stored
	    writeAnnotationDraft(storage.key, {
	      characterName: (next.characterName ?? current.characterName ?? clipModalCharacterName.trim()) || 'Unassigned',
	      actorName: (next.actorName ?? current.actorName ?? clipModalActorName.trim()) || '',
	      capturedFrameDataUrl: next.capturedFrameDataUrl ?? current.capturedFrameDataUrl ?? null,
	      capturedFrameSeconds: next.capturedFrameSeconds ?? current.capturedFrameSeconds ?? null,
	      draftBbox: next.draftBbox === undefined ? current.draftBbox ?? null : next.draftBbox,
      savedBoxes: next.savedBoxes ?? (Array.isArray(current.savedBoxes) ? current.savedBoxes : []),
      adjustmentEvents: next.adjustmentEvents ?? (Array.isArray(current.adjustmentEvents) ? current.adjustmentEvents : []),
      saveStatus: next.saveStatus ?? current.saveStatus ?? '',
    })
    setClipModalAnnotationRevision((currentRevision) => currentRevision + 1)
  }

  function upsertClipModalKeyframeBox(
    stored: Partial<KeyframeAnnotationDraftState>,
    bbox: NormalizedBbox,
    timestampSeconds: number,
    characterName: string,
    actorName: string,
    status: KeyframeAnnotationBox['status'] = 'draft',
  ): KeyframeAnnotationBox[] {
    const existing = Array.isArray(stored.savedBoxes) ? stored.savedBoxes : []
    const roundedTime = Math.round(timestampSeconds * 100) / 100
    const matchingIndex = existing.findIndex((box) => (
      box.status !== 'receipt_written'
      && box.characterName === characterName
      && Math.abs((box.timestampSeconds ?? -9999) - roundedTime) < 0.08
    ))
    const nextBox: KeyframeAnnotationBox = {
      id: matchingIndex >= 0 ? existing[matchingIndex].id : `keyframe-${Date.now().toString(36)}-${Math.round(roundedTime * 100)}`,
      bbox,
      characterName,
      actorName,
      timestampSeconds: roundedTime,
      status,
    }
    if (matchingIndex >= 0) {
      return existing.map((box, index) => index === matchingIndex ? { ...box, ...nextBox } : box)
    }
    return [...existing, nextBox]
  }

  function appendClipModalAdjustmentEvent(
    stored: Partial<KeyframeAnnotationDraftState>,
    event: Omit<KeyframeAnnotationAdjustmentEvent, 'id' | 'createdAt' | 'timecode' | 'bboxDimensions'>,
  ): KeyframeAnnotationAdjustmentEvent[] {
    const existing = Array.isArray(stored.adjustmentEvents) ? stored.adjustmentEvents : []
    return [
      ...existing,
      {
        ...event,
        id: `adjustment-${Date.now().toString(36)}-${existing.length}`,
        timecode: secondsToClock(event.timestampSeconds),
        bboxDimensions: bboxDimensions(event.bbox),
        createdAt: new Date().toISOString(),
      },
    ]
  }

	  function selectClipModalAnnotation(event: React.PointerEvent<HTMLDivElement>, overlay: WatchOverlayPayloadOverlay): void {
	    if (!overlay.overlay_id.startsWith('kf:') && !overlay.overlay_id.startsWith('annotation-')) return
    annotationDispatch(annotationSessionActions.selectOverlay(overlay.overlay_id))
	    startClipModalMove(event, overlay)
	  }

  function captureClipModalOverlayDataUrl(overlay: WatchOverlayPayloadOverlay): string | null {
    const video = clipModalVideoRef.current
    if (!video || video.videoWidth <= 0 || video.videoHeight <= 0) return null
    const x = clamp01(overlay.bbox_percent.left / 100)
    const y = clamp01(overlay.bbox_percent.top / 100)
    const width = clamp01(overlay.bbox_percent.width / 100)
    const height = clamp01(overlay.bbox_percent.height / 100)
    const sourceX = Math.max(0, Math.floor(x * video.videoWidth))
    const sourceY = Math.max(0, Math.floor(y * video.videoHeight))
    const sourceWidth = Math.max(1, Math.floor(width * video.videoWidth))
    const sourceHeight = Math.max(1, Math.floor(height * video.videoHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.min(512, sourceWidth)
    canvas.height = Math.max(1, Math.round(canvas.width * (sourceHeight / sourceWidth)))
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    try {
      ctx.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height)
      return canvas.toDataURL('image/jpeg', 0.86)
    } catch {
      return null
    }
  }

  async function requestClipModalMemorySuggestion(overlay: WatchOverlayPayloadOverlay): Promise<void> {
    if (!expandedClipRow || !reportWithDiff) return
    const imageDataUrl = captureClipModalOverlayDataUrl(overlay)
    if (!imageDataUrl) {
      setClipModalYoloStatus(`Selected ${overlay.track_id}; Memory crop unavailable until the video frame is loaded.`)
      return
    }
    setClipModalYoloStatus(`Querying Memory/Qdrant for ${overlay.track_id}...`)
    try {
      const response = await fetch('/api/projects/watch/identity-suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_uid: watchAssetUid(reportWithDiff.watch_report.title),
          row_index: expandedClipRow.index,
          time_seconds: clipModalPlaybackSeconds,
          track_id: overlay.track_id,
          image_data_url: imageDataUrl,
          q: `Who does this YOLO person crop most look like in ${reportWithDiff.watch_report.title} row ${expandedClipRow.index}?`,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as WatchIdentitySuggestionResponse
      const suggestion = parseMemorySuggestion({ ...data, track_id: overlay.track_id })
      if (!suggestion) {
        setClipModalYoloStatus(`Memory returned no character suggestion for ${overlay.track_id}.`)
        return
      }
      setClipModalMemorySuggestions((current) => ({
        ...current,
        [overlay.track_id]: { ...suggestion, trackId: overlay.track_id },
      }))
      setClipModalYoloStatus(`${suggestion.characterName}?${typeof suggestion.confidence === 'number' ? ` ${suggestion.confidence.toFixed(2)}` : ''} suggested for ${overlay.track_id}.`)
    } catch (err) {
      setClipModalYoloStatus(`Memory suggestion failed for ${overlay.track_id}: ${String(err)}`)
    }
  }

  function selectClipModalYoloTrack(event: React.PointerEvent<HTMLDivElement | HTMLButtonElement>, overlay: WatchOverlayPayloadOverlay): void {
    event.preventDefault()
    event.stopPropagation()
    setClipModalManualDrawEnabled(false)
    setClipModalDrawMode(false)
    setClipModalDragStart(null)
    setClipModalDraftBbox(null)
    setClipModalSelectedOverlayId(overlay.overlay_id)
    setClipModalSelectedYoloTrackId(overlay.track_id)

    const storage = clipModalYoloLabelStorage()
    const latestEvent = latestYoloLabelEventForTrack(clipModalYoloLabelEvents, overlay.track_id, clipModalPlaybackSeconds)
    const eventLabel = latestEvent ? yoloLabelFromEvent(latestEvent) : undefined
    const isRejectedFrame = Boolean(latestEvent && eventLabel === null)
      || Boolean(clipModalYoloBoxRejections[yoloBoxInstanceKey(overlay.track_id, clipModalPlaybackSeconds)])
    const label = latestEvent
      ? eventLabel
      : isRejectedFrame
        ? null
        : storage?.labels[overlay.track_id] ?? clipModalMemorySuggestions[overlay.track_id]
    if (label) {
      setClipModalCharacterName(label.characterName)
      setClipModalActorName(label.actorName || actorForCharacter(label.characterName) || '')
    } else if (isRejectedFrame) {
      setClipModalCharacterName('Unassigned')
      setClipModalActorName('')
    }
    const rejectedSince = latestEvent ? yoloLabelEventTime(latestEvent) : null
    setClipModalYoloStatus(isRejectedFrame
      ? `YOLO person box ${overlay.track_id} is unassigned from ${(rejectedSince ?? clipModalPlaybackSeconds).toFixed(2)}s until the next saved character assignment.`
      : `YOLO person box ${overlay.track_id} selected. Choose the character, then save, unassign this frame, or reset the whole track.`)
    void requestClipModalMemorySuggestion(overlay)
  }

  async function saveClipModalYoloTrackLabel(): Promise<void> {
    const storage = clipModalYoloLabelStorage()
    if (!storage || !clipModalSelectedYoloTrackId || !expandedClipRow || !reportWithDiff) return
    const characterName = clipModalCharacterName.trim()
    if (!characterName || characterName === 'Unassigned') {
      await unassignClipModalYoloBoxFrame()
      return
    }
    const actorName = clipModalActorName.trim() || actorForCharacter(characterName) || ''
    const timeSeconds = clipModalVideoRef.current?.currentTime ?? clipModalPlaybackSeconds
    const roundedTimeSeconds = Math.round(timeSeconds * 100) / 100
    const boxKey = selectedYoloBoxKey(roundedTimeSeconds)
    const labels = {
      ...storage.labels,
      [clipModalSelectedYoloTrackId]: {
        trackId: clipModalSelectedYoloTrackId,
        characterName,
        actorName,
        status: 'accepted' as const,
        source: 'human' as const,
        confidence: 1,
        updatedAt: new Date().toISOString(),
      },
    }
    writeYoloTrackLabels(storage.key, labels)
    setClipModalYoloLabels(labels)
    if (boxKey) {
      setClipModalYoloBoxRejections((current) => {
        if (!current[boxKey]) return current
        const next = { ...current }
        delete next[boxKey]
        return next
      })
    }
    setClipModalYoloLabelEvents((current) => upsertYoloLabelEvent(current, {
      action: 'accept',
      status: 'accepted',
      track_id: clipModalSelectedYoloTrackId,
      box_key: boxKey || undefined,
      time_seconds: roundedTimeSeconds,
      character_name: characterName,
      actor_name: actorName,
      confidence: 1,
      created_at: new Date().toISOString(),
    }))
    setClipModalYoloLabelRevision((current) => current + 1)
    setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} accepted as ${characterName}; persisting Watch label...`)
    try {
      const response = await fetch('/api/projects/watch/yolo-labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'accept',
          asset_uid: watchAssetUid(reportWithDiff.watch_report.title),
          row_index: expandedClipRow.index,
          timecode: expandedClipRow.timecode,
          movie_segment: expandedClipRow.movie_segment,
          time_seconds: roundedTimeSeconds,
          box_key: boxKey,
          track_id: clipModalSelectedYoloTrackId,
          character_name: characterName,
          actor_name: actorName,
          confidence: 1,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const serverLabels = data?.labels && typeof data.labels === 'object'
        ? data.labels as Record<string, WatchYoloTrackLabel>
        : labels
      const serverRejections = data?.box_rejections && typeof data.box_rejections === 'object'
        ? data.box_rejections as Record<string, WatchYoloBoxRejection>
        : undefined
      const serverEvents = readYoloLabelEvents(data?.events)
      setClipModalYoloLabels(serverLabels)
      if (serverRejections) setClipModalYoloBoxRejections(serverRejections)
      if (serverEvents.length > 0) setClipModalYoloLabelEvents(serverEvents)
      writeYoloTrackLabels(storage.key, serverLabels)
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} accepted as ${characterName}; persisted to Watch${data?.memory_sync === 'stored' ? ' and Memory' : ''}.`)
    } catch (err) {
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} accepted as ${characterName} locally, but server persistence failed: ${String(err)}`)
    }
    logClipModalAuditEvent('YOLO_TRACK_LABEL_ACCEPTED', { trackId: clipModalSelectedYoloTrackId, characterName, actorName })
  }

  async function unassignClipModalYoloBoxFrame(): Promise<void> {
    if (!clipModalSelectedYoloTrackId || !expandedClipRow || !reportWithDiff) return
    const timeSeconds = clipModalVideoRef.current?.currentTime ?? clipModalPlaybackSeconds
    const roundedTimeSeconds = Math.round(timeSeconds * 100) / 100
    const boxKey = selectedYoloBoxKey(roundedTimeSeconds) ?? yoloBoxInstanceKey(clipModalSelectedYoloTrackId, roundedTimeSeconds)
    const rejection: WatchYoloBoxRejection = {
      boxKey,
      trackId: clipModalSelectedYoloTrackId,
      timeSeconds: roundedTimeSeconds,
      status: 'rejected',
      source: 'human',
      updatedAt: new Date().toISOString(),
    }
    setClipModalYoloBoxRejections((current) => ({ ...current, [boxKey]: rejection }))
    setClipModalMemorySuggestions((current) => {
      const next = { ...current }
      delete next[clipModalSelectedYoloTrackId]
      return next
    })
    setClipModalYoloLabelEvents((current) => upsertYoloLabelEvent(current, {
      action: 'reject_box',
      status: 'rejected_box',
      track_id: clipModalSelectedYoloTrackId,
      box_key: boxKey,
      time_seconds: roundedTimeSeconds,
      created_at: rejection.updatedAt,
    }))
    setClipModalYoloLabelRevision((current) => current + 1)
    setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} unassigned from ${rejection.timeSeconds.toFixed(2)}s until the next saved character assignment.`)
    try {
      const response = await fetch('/api/projects/watch/yolo-labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'reject_box',
          asset_uid: watchAssetUid(reportWithDiff.watch_report.title),
          row_index: expandedClipRow.index,
          timecode: expandedClipRow.timecode,
          movie_segment: expandedClipRow.movie_segment,
          time_seconds: roundedTimeSeconds,
          box_key: boxKey,
          track_id: clipModalSelectedYoloTrackId,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const serverRejections = data?.box_rejections && typeof data.box_rejections === 'object'
        ? data.box_rejections as Record<string, WatchYoloBoxRejection>
        : { [boxKey]: rejection }
      const serverEvents = readYoloLabelEvents(data?.events)
      setClipModalYoloBoxRejections(serverRejections)
      if (serverEvents.length > 0) setClipModalYoloLabelEvents(serverEvents)
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} unassigned from ${rejection.timeSeconds.toFixed(2)}s and persisted as a sequence stop.`)
    } catch (err) {
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} unassigned at this frame locally, but server persistence failed: ${String(err)}`)
    }
    logClipModalAuditEvent('YOLO_BOX_FRAME_UNASSIGNED', { trackId: clipModalSelectedYoloTrackId, boxId: boxKey, timestamp: rejection.timeSeconds })
  }

  async function resetClipModalYoloTrackLabel(): Promise<void> {
    const storage = clipModalYoloLabelStorage()
    if (!storage || !clipModalSelectedYoloTrackId || !expandedClipRow || !reportWithDiff) return
    const labels = { ...storage.labels }
    delete labels[clipModalSelectedYoloTrackId]
    writeYoloTrackLabels(storage.key, labels)
    setClipModalYoloLabels(labels)
    setClipModalMemorySuggestions((current) => {
      const next = { ...current }
      delete next[clipModalSelectedYoloTrackId]
      return next
    })
    setClipModalYoloLabelEvents((current) => upsertYoloLabelEvent(current, {
      action: 'reset',
      status: 'reset',
      track_id: clipModalSelectedYoloTrackId,
      time_seconds: clipModalPlaybackSeconds,
      created_at: new Date().toISOString(),
    }))
    setClipModalYoloLabelRevision((current) => current + 1)
    setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} reset to ${yoloTrackDisplayName(clipModalSelectedYoloTrackId)}.`)
    try {
      const response = await fetch('/api/projects/watch/yolo-labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'reset',
          asset_uid: watchAssetUid(reportWithDiff.watch_report.title),
          row_index: expandedClipRow.index,
          timecode: expandedClipRow.timecode,
          movie_segment: expandedClipRow.movie_segment,
          time_seconds: clipModalPlaybackSeconds,
          track_id: clipModalSelectedYoloTrackId,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const serverLabels = data?.labels && typeof data.labels === 'object'
        ? data.labels as Record<string, WatchYoloTrackLabel>
        : labels
      const serverRejections = data?.box_rejections && typeof data.box_rejections === 'object'
        ? data.box_rejections as Record<string, WatchYoloBoxRejection>
        : undefined
      const serverEvents = readYoloLabelEvents(data?.events)
      setClipModalYoloLabels(serverLabels)
      if (serverRejections) setClipModalYoloBoxRejections(serverRejections)
      if (serverEvents.length > 0) setClipModalYoloLabelEvents(serverEvents)
      writeYoloTrackLabels(storage.key, serverLabels)
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} reset to ${yoloTrackDisplayName(clipModalSelectedYoloTrackId)} and persisted.`)
    } catch (err) {
      setClipModalYoloStatus(`${clipModalSelectedYoloTrackId} reset locally, but server persistence failed: ${String(err)}`)
    }
    logClipModalAuditEvent('YOLO_TRACK_LABEL_RESET', { trackId: clipModalSelectedYoloTrackId })
  }

  function promoteToKeyframe(overlay: WatchOverlayPayloadOverlay): void {
    const storage = clipModalAnnotationStorage()
    if (!storage) return
    const characterName = overlay.identity_candidate?.name || clipModalCharacterName || storage.stored.characterName || 'Unassigned'
    const actorName = overlay.identity_candidate?.actor_name || clipModalActorName || actorForCharacter(characterName) || storage.stored.actorName || ''
    const timestampSeconds = clipModalVideoRef.current?.currentTime ?? overlay.valid_at_media_time_seconds ?? 0
    const bbox: NormalizedBbox = [
      overlay.bbox_percent.left / 100,
      overlay.bbox_percent.top / 100,
      (overlay.bbox_percent.left + overlay.bbox_percent.width) / 100,
      (overlay.bbox_percent.top + overlay.bbox_percent.height) / 100,
    ]
    const savedBoxes = upsertClipModalKeyframeBox(storage.stored, bbox, timestampSeconds, characterName, actorName, 'draft')
    const promotedBox = savedBoxes[savedBoxes.length - 1]
    const adjustmentEvents = appendClipModalAdjustmentEvent(storage.stored, {
      type: 'promote',
      boxId: promotedBox?.id ?? overlay.overlay_id,
      characterName,
      actorName,
      timestampSeconds,
      bbox,
    })
    writeAnnotationDraft(storage.key, {
      characterName,
      actorName,
      capturedFrameDataUrl: storage.stored.capturedFrameDataUrl ?? null,
      capturedFrameSeconds: timestampSeconds,
      draftBbox: null,
      savedBoxes,
      adjustmentEvents,
      saveStatus: `Interpolated box promoted at ${timestampSeconds.toFixed(2)}s.`,
    })
    setClipModalAnnotationRevision((current) => current + 1)
    setClipModalSelectedOverlayId(`annotation-${storage.row.index}-${promotedBox?.id ?? overlay.overlay_id}`)
    logClipModalAuditEvent('INTERPOLATION_PROMOTED', { boxId: promotedBox?.id ?? overlay.overlay_id, timestamp: timestampSeconds })
  }

  function bboxForClipModalOverlay(overlay: WatchOverlayPayloadOverlay): NormalizedBbox | null {
    if (overlay.overlay_id.startsWith('kf:')) {
      return [
        overlay.bbox_percent.left / 100,
        overlay.bbox_percent.top / 100,
        (overlay.bbox_percent.left + overlay.bbox_percent.width) / 100,
        (overlay.bbox_percent.top + overlay.bbox_percent.height) / 100,
      ]
    }
    const storage = clipModalAnnotationStorage()
    if (!storage) return null
    const boxId = annotationBoxIdFromOverlayId(overlay.overlay_id, storage.row)
    if (!boxId) return null
    if (boxId === 'draft-bbox') return storage.stored.draftBbox ?? null
    return (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).find((box) => box.id === boxId)?.bbox ?? null
  }

  function pointInClipModalViewport(event: React.PointerEvent<HTMLDivElement>): { rect: DOMRect; point: { x: number; y: number } } | null {
    const viewport = event.currentTarget.closest('[data-qid="watch:clip-modal:evidence-viewport"]')
    if (!viewport) return null
    const rect = viewport.getBoundingClientRect()
    return {
      rect,
      point: {
        x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
        y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
      },
    }
  }

  function startClipModalMove(event: React.PointerEvent<HTMLDivElement>, overlay: WatchOverlayPayloadOverlay): void {
    const bbox = bboxForClipModalOverlay(overlay)
    const viewportPoint = pointInClipModalViewport(event)
    if (!bbox || !viewportPoint) return
    event.preventDefault()
    event.stopPropagation()
    event.currentTarget.focus()
    event.currentTarget.setPointerCapture(event.pointerId)
    setClipModalDrawMode(false)
    setClipModalSelectedOverlayId(overlay.overlay_id)
    setClipModalMoveState({ overlayId: overlay.overlay_id, startPoint: viewportPoint.point, startBbox: bbox })
  }

  function onClipModalMoveDrag(event: React.PointerEvent<HTMLDivElement>): void {
    if (!clipModalMoveState) return
    const viewportPoint = pointInClipModalViewport(event)
    if (!viewportPoint) return
    if (clipModalMoveState.overlayId.startsWith('kf:')) {
      event.preventDefault()
      event.stopPropagation()
      const dx = (viewportPoint.point.x - clipModalMoveState.startPoint.x) / viewportPoint.rect.width
      const dy = (viewportPoint.point.y - clipModalMoveState.startPoint.y) / viewportPoint.rect.height
      const moved = snapBboxEdges(moveBboxByDelta(clipModalMoveState.startBbox, dx, dy))
      if (clipModalMoveRafRef.current !== null) window.cancelAnimationFrame(clipModalMoveRafRef.current)
      clipModalMoveRafRef.current = window.requestAnimationFrame(() => {
        annotationDispatch(annotationSessionActions.moveSelectedBox(moved))
        clipModalMoveRafRef.current = null
      })
      return
    }
    const storage = clipModalAnnotationStorage()
    if (!storage) return
    const boxId = annotationBoxIdFromOverlayId(clipModalMoveState.overlayId, storage.row)
    if (!boxId) return
    event.preventDefault()
    event.stopPropagation()
    const dx = (viewportPoint.point.x - clipModalMoveState.startPoint.x) / viewportPoint.rect.width
    const dy = (viewportPoint.point.y - clipModalMoveState.startPoint.y) / viewportPoint.rect.height
    const moved = snapBboxEdges(moveBboxByDelta(clipModalMoveState.startBbox, dx, dy))
    if (boxId === 'draft-bbox') {
      if (clipModalMoveRafRef.current !== null) window.cancelAnimationFrame(clipModalMoveRafRef.current)
      clipModalMoveRafRef.current = window.requestAnimationFrame(() => {
        writeClipModalAnnotationUpdate({
          draftBbox: moved,
          saveStatus: 'Draft keyframe box moved.',
        })
        clipModalMoveRafRef.current = null
      })
    } else {
      const savedBoxes = (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).map((box) => (
        box.id === boxId ? { ...box, bbox: moved } : box
      ))
      if (clipModalMoveRafRef.current !== null) window.cancelAnimationFrame(clipModalMoveRafRef.current)
      clipModalMoveRafRef.current = window.requestAnimationFrame(() => {
        writeClipModalAnnotationUpdate({
          savedBoxes,
          saveStatus: 'Selected keyframe box moved.',
        })
        clipModalMoveRafRef.current = null
      })
    }
  }

  function stopClipModalMove(event: React.PointerEvent<HTMLDivElement>): void {
    if (!clipModalMoveState) return
    if (clipModalMoveState.overlayId.startsWith('kf:')) {
      event.preventDefault()
      event.stopPropagation()
      setClipModalMoveState(null)
      return
    }
    const storage = clipModalAnnotationStorage()
    const boxId = storage ? annotationBoxIdFromOverlayId(clipModalMoveState.overlayId, storage.row) : null
    const box = boxId && storage && boxId !== 'draft-bbox'
      ? (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).find((candidateBox) => candidateBox.id === boxId)
      : null
    if (storage && boxId && box) {
      const adjustmentEvents = appendClipModalAdjustmentEvent(storage.stored, {
        type: 'move',
        boxId,
        characterName: box.characterName,
        actorName: box.actorName,
        timestampSeconds: box.timestampSeconds ?? clipModalVideoRef.current?.currentTime ?? 0,
        bbox: box.bbox,
      })
      writeClipModalAnnotationUpdate({
        adjustmentEvents,
        saveStatus: `Keyframe moved at ${(box.timestampSeconds ?? 0).toFixed(2)}s.`,
      })
    }
    event.preventDefault()
    event.stopPropagation()
    setClipModalMoveState(null)
  }

  function startClipModalResize(event: React.PointerEvent<HTMLDivElement>, overlay: WatchOverlayPayloadOverlay, handle: BboxResizeHandle): void {
    if (overlay.overlay_id.startsWith('kf:')) {
      const bbox = bboxForClipModalOverlay(overlay)
      if (!bbox) return
      event.preventDefault()
      event.stopPropagation()
      event.currentTarget.focus()
      const viewport = event.currentTarget.closest('[data-qid="watch:clip-modal:evidence-viewport"]')
      if (!viewport) return
      const rect = viewport.getBoundingClientRect()
      const point = {
        x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
        y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
      }
      event.currentTarget.setPointerCapture(event.pointerId)
      annotationDispatch(annotationSessionActions.selectOverlay(overlay.overlay_id))
      setClipModalSelectedOverlayId(overlay.overlay_id)
      setClipModalResizeState({ overlayId: overlay.overlay_id, handle, startPoint: point, startBbox: bbox })
      return
    }
    const storage = clipModalAnnotationStorage()
    if (!storage) return
    const boxId = annotationBoxIdFromOverlayId(overlay.overlay_id, storage.row)
    if (!boxId) return
    const bbox = boxId === 'draft-bbox'
      ? storage.stored.draftBbox
      : (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).find((box) => box.id === boxId)?.bbox
    if (!bbox) return
	    event.preventDefault()
	    event.stopPropagation()
	    event.currentTarget.focus()
	    const viewport = event.currentTarget.closest('[data-qid="watch:clip-modal:evidence-viewport"]')
    if (!viewport) return
    const rect = viewport.getBoundingClientRect()
    const point = {
      x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
      y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setClipModalSelectedOverlayId(overlay.overlay_id)
    setClipModalResizeState({ overlayId: overlay.overlay_id, handle, startPoint: point, startBbox: bbox })
  }

  function onClipModalResizeMove(event: React.PointerEvent<HTMLDivElement>): void {
    if (!clipModalResizeState) return
    event.preventDefault()
    event.stopPropagation()
    const viewport = event.currentTarget.closest('[data-qid="watch:clip-modal:evidence-viewport"]')
    if (!viewport) return
    const rect = viewport.getBoundingClientRect()
    const point = {
      x: clamp01((event.clientX - rect.left) / rect.width) * rect.width,
      y: clamp01((event.clientY - rect.top) / rect.height) * rect.height,
    }
    const dx = (point.x - clipModalResizeState.startPoint.x) / rect.width
    const dy = (point.y - clipModalResizeState.startPoint.y) / rect.height
    const resized = snapBboxEdges(resizeBboxFromHandle(clipModalResizeState.startBbox, clipModalResizeState.handle, dx, dy))
    if (clipModalResizeState.overlayId.startsWith('kf:')) {
      if (clipModalResizeRafRef.current !== null) window.cancelAnimationFrame(clipModalResizeRafRef.current)
      clipModalResizeRafRef.current = window.requestAnimationFrame(() => {
        annotationDispatch(annotationSessionActions.resizeSelectedBox(resized))
        clipModalResizeRafRef.current = null
      })
      return
    }
    const storage = clipModalAnnotationStorage()
    if (!storage) return
    const boxId = annotationBoxIdFromOverlayId(clipModalResizeState.overlayId, storage.row)
    if (!boxId) return
    if (boxId === 'draft-bbox') {
      if (clipModalResizeRafRef.current !== null) window.cancelAnimationFrame(clipModalResizeRafRef.current)
      clipModalResizeRafRef.current = window.requestAnimationFrame(() => {
        writeClipModalAnnotationUpdate({
          draftBbox: resized,
          saveStatus: 'Draft keyframe box resized.',
        })
        clipModalResizeRafRef.current = null
      })
    } else {
      const savedBoxes = (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).map((box) => (
        box.id === boxId ? { ...box, bbox: resized } : box
      ))
      if (clipModalResizeRafRef.current !== null) window.cancelAnimationFrame(clipModalResizeRafRef.current)
      clipModalResizeRafRef.current = window.requestAnimationFrame(() => {
        writeClipModalAnnotationUpdate({
          savedBoxes,
          saveStatus: 'Selected keyframe box resized.',
        })
        clipModalResizeRafRef.current = null
      })
    }
  }

  function stopClipModalResize(event: React.PointerEvent<HTMLDivElement>): void {
    if (!clipModalResizeState) return
    if (clipModalResizeState.overlayId.startsWith('kf:')) {
      event.preventDefault()
      event.stopPropagation()
      setClipModalResizeState(null)
      return
    }
    const storage = clipModalAnnotationStorage()
    const boxId = storage ? annotationBoxIdFromOverlayId(clipModalResizeState.overlayId, storage.row) : null
    const box = boxId && storage && boxId !== 'draft-bbox'
      ? (Array.isArray(storage.stored.savedBoxes) ? storage.stored.savedBoxes : []).find((candidateBox) => candidateBox.id === boxId)
      : null
    if (storage && boxId && box) {
      const adjustmentEvents = appendClipModalAdjustmentEvent(storage.stored, {
        type: 'resize',
        boxId,
        characterName: box.characterName,
        actorName: box.actorName,
        timestampSeconds: box.timestampSeconds ?? clipModalVideoRef.current?.currentTime ?? 0,
        bbox: box.bbox,
      })
      writeClipModalAnnotationUpdate({
        adjustmentEvents,
        saveStatus: `Keyframe resized at ${(box.timestampSeconds ?? 0).toFixed(2)}s.`,
      })
    }
    event.preventDefault()
    event.stopPropagation()
    setClipModalResizeState(null)
  }
  useEffect(() => {
    if (!reportWithDiff || expandedClip) return
    const rowIndex = readClipRowFromHash()
    if (rowIndex == null) return
    const row = reportWithDiff.scene_elements.find((candidate) => candidate.index === rowIndex)
    if (row && segmentVideoUrl(row)) {
      openExpandedClipForRow(row)
    }
  }, [expandedClip, reportWithDiff])

	  useEffect(() => {
	    setClipModalDrawMode(false)
	    setClipModalDragStart(null)
	    setClipModalDraftBbox(null)
	    setClipModalSelectedOverlayId(null)
	    setClipModalResizeState(null)
	    setClipModalMoveState(null)
	    setClipModalPlaybackSeconds(0)
	    setClipModalDurationSeconds(0)
	    setClipModalPaused(false)
	  }, [expandedClip?.rowIndex])

	  function runForensicAudit(): void {
	    setAuditRunning(true)
	    setAuditStepIndex(0)
    setShowDivergencesOnly(false)
    setActiveDiffCategory(null)
  }

  async function startWatchIngest(): Promise<void> {
    const source = pendingSource.trim()
    if (!source || ingestJob?.status === 'running') return
    setIngestError('')
    setIngestPipelineOpen(true)
    try {
      const response = await fetch('/api/projects/watch/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.error ? String(payload.error) : `watch_ingest_http_${response.status}`)
      setIngestJob(payload.job)
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : String(err))
    }
  }

  function syncSegmentPlayback(row: SceneElement, video: HTMLVideoElement): void {
    setActivePlaybackRow(row.index)
    setSelectedRow(row.index)
    focusAuditRow(row.index)
    if (!pauseOnDivergence || !row.diff_info || video.currentTime < 0.35 || pausedDivergenceRows.has(row.index)) return
    video.pause()
    setPausedDivergenceRows((current) => new Set(current).add(row.index))
    setForensicPause({
      rowIndex: row.index,
      timecode: row.timecode,
      label: diffCategoryLabel(row.diff_info.category),
      detail: row.diff_info.detail,
    })
    setActiveTab('agent')
  }

  const sceneContext = useMemo(() => {
    if (selectedRow == null || !reportWithDiff) return undefined
    const row = reportWithDiff.scene_elements.find((r) => r.index === selectedRow)
    if (!row) return undefined
    return {
      timecode: row.timecode,
      rowIndex: row.index,
      movieTitle: reportWithDiff.watch_report.title,
      movieSegment: row.movie_segment,
    } as WatchChatAdapterOptions['sceneContext']
  }, [selectedRow, reportWithDiff])

	  const expandedClipRow = expandedClip && reportWithDiff
	    ? reportWithDiff.scene_elements.find((row) => row.index === expandedClip.rowIndex) ?? null
	    : null

  const annotationSessionRow = useMemo((): SessionRow | null => {
    if (!expandedClipRow || !reportWithDiff) return null
    const duration = Math.max(
      clipModalDurationSeconds,
      segmentEndSeconds(expandedClipRow) - segmentStartSeconds(expandedClipRow.movie_segment || expandedClipRow.timecode),
      1,
    )
    return {
      rowIndex: expandedClipRow.index,
      movieTitle: reportWithDiff.watch_report.title,
      segmentStartSeconds: 0,
      segmentEndSeconds: duration,
      fps: 24,
    }
  }, [clipModalDurationSeconds, expandedClipRow, reportWithDiff])

	  const clipModalCharacterOptions = useMemo(() => {
	    if (!expandedClipRow) return ['Unassigned']
	    const candidate = candidateCharacterForRow(expandedClipRow)
	    const values = [
	      ...(expandedClip?.entities ?? []),
	      ...sceneEntities(expandedClipRow),
	      candidate?.name,
	      ...ENTITY_PATTERNS.map((entry) => entry.name),
	      'Unassigned',
	    ]
	    return Array.from(new Set(values.filter((value): value is string => !!value && value.trim().length > 0)))
	  }, [expandedClip, expandedClipRow])

	  function updateClipModalCharacter(name: string): void {
	    setClipModalCharacterName(name)
	    const actor = actorForCharacter(name)
	    setClipModalActorName(actor || '')
    annotationDispatch(annotationSessionActions.selectCharacter(name, actor || undefined))
	  }

	  function toggleClipModalPlayback(): void {
	    const video = clipModalVideoRef.current
	    if (!video) return
	    if (video.paused) {
	      void video.play()
	    } else {
	      video.pause()
	    }
	  }

	  function seekClipModalPlayback(value: number): void {
	    const video = clipModalVideoRef.current
	    if (!video || !Number.isFinite(value)) return
	    const duration = Number.isFinite(video.duration) && video.duration > 0
	      ? video.duration
	      : Math.max(clipModalDurationSeconds, clipModalPlaybackSeconds, 1)
	    const nextSeconds = Math.max(0, Math.min(duration, value))
	    video.currentTime = nextSeconds
	    setClipModalPlaybackSeconds(nextSeconds)
    annotationDispatch(annotationSessionActions.setPlaybackTime(nextSeconds))
	  }

	  useEffect(() => {
	    if (!expandedClipRow || !reportWithDiff) return
	    const key = annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    const yoloKey = yoloTrackLabelStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    const stored = readAnnotationDraft(key)
    const candidate = candidateCharacterForRow(expandedClipRow)
	    const fallbackCharacter = expandedClip?.entities.find((entity) => actorForCharacter(entity)) || candidate?.name || expandedClip?.entities[0] || 'Unassigned'
	    const nextCharacterName = stored?.characterName || fallbackCharacter
	    const nextActorName = stored?.actorName || actorForCharacter(nextCharacterName) || candidate?.actor || ''
	    setClipModalCharacterName(nextCharacterName)
	    setClipModalActorName(nextActorName)
    setClipModalManualDrawEnabled(false)
    setClipModalSelectedYoloTrackId(null)
    setClipModalYoloStatus('')
    setClipModalMemorySuggestions({})
    setClipModalYoloLabels(readYoloTrackLabels(yoloKey))
    setClipModalYoloBoxRejections({})
    setClipModalYoloLabelEvents([])
    if (annotationSessionRow) {
      annotationDispatch(annotationSessionActions.hydrateFromMemory(
        annotationSessionRow,
        annotationSessionRecordsFromDraft(expandedClipRow, stored),
      ))
      annotationDispatch(annotationSessionActions.selectCharacter(nextCharacterName, nextActorName || undefined))
    }
  }, [expandedClip, expandedClipRow, reportWithDiff])

  useEffect(() => {
    if (!expandedClipRow || !reportWithDiff) return undefined
    let cancelled = false
    const localKey = yoloTrackLabelStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    const assetUid = watchAssetUid(reportWithDiff.watch_report.title)
    const params = new URLSearchParams({
      asset_uid: assetUid,
      row_index: String(expandedClipRow.index),
    })
    fetch(`/api/projects/watch/yolo-labels?${params.toString()}`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((data) => {
        if (cancelled) return
        const serverLabels = data?.labels && typeof data.labels === 'object'
          ? data.labels as Record<string, WatchYoloTrackLabel>
          : {}
        const merged = { ...readYoloTrackLabels(localKey), ...serverLabels }
        const serverRejections = data?.box_rejections && typeof data.box_rejections === 'object'
          ? data.box_rejections as Record<string, WatchYoloBoxRejection>
          : {}
        const serverEvents = readYoloLabelEvents(data?.events)
        setClipModalYoloLabels(merged)
        setClipModalYoloBoxRejections(serverRejections)
        setClipModalYoloLabelEvents(serverEvents)
        writeYoloTrackLabels(localKey, merged)
      })
      .catch((err) => {
        if (!cancelled) {
          setClipModalYoloStatus(`Server YOLO label load failed; using local cache only: ${String(err)}`)
        }
      })
    return () => {
      cancelled = true
    }
  }, [expandedClipRow, reportWithDiff])

  useEffect(() => {
    if (!expandedClipRow || !reportWithDiff || annotationSession.row.rowIndex !== expandedClipRow.index) return
    const key = annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    const stored = readAnnotationDraft(key)
    const active = selectActiveCharacter(annotationSession)
    writeAnnotationDraft(key, {
      characterName: active?.characterName || clipModalCharacterName || stored?.characterName || 'Unassigned',
      actorName: active?.actorName || clipModalActorName || stored?.actorName || '',
      capturedFrameDataUrl: stored?.capturedFrameDataUrl ?? null,
      capturedFrameSeconds: clipModalPlaybackSeconds,
      draftBbox: null,
      savedBoxes: savedBoxesFromAnnotationSession(annotationSession),
      adjustmentEvents: Array.isArray(stored?.adjustmentEvents) ? stored.adjustmentEvents : [],
      saveStatus: stored?.saveStatus ?? '',
    })
    setClipModalAnnotationRevision((current) => current + 1)
  }, [annotationSession.revision, expandedClipRow, reportWithDiff])

	  useEffect(() => {
	    if (!expandedClipRow) return undefined

	    function handleDeleteKey(event: KeyboardEvent): void {
	      if (event.key !== 'Delete' && event.key !== 'Backspace') return
	      const target = event.target as HTMLElement | null
	      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
	      event.preventDefault()
      annotationDispatch(annotationSessionActions.setPlaybackTime(clipModalVideoRef.current?.currentTime ?? clipModalPlaybackSeconds))
      annotationDispatch(annotationSessionActions.deleteSelectedExactKeyframe())
	      setClipModalSelectedOverlayId(null)
	    }

	    window.addEventListener('keydown', handleDeleteKey)
	    return () => window.removeEventListener('keydown', handleDeleteKey)
	  }, [expandedClipRow, clipModalPlaybackSeconds])

	  if (loadError) return <div style={{ padding: 24, color: '#ff4757' }}>Failed to load report: {loadError}</div>
  if (!reportWithDiff) return <div style={{ padding: 24, color: '#6b7a8f' }}>Loading Watch report...</div>

  const activeFilterLabel = activeDiffCategory
    ? `${diffCategoryLabel(activeDiffCategory)} Divergences (${reportWithDiff.diff_intelligence?.category_counts[activeDiffCategory] ?? filteredRows.length})`
    : showDivergencesOnly
      ? `All Divergences (${filteredRows.length})`
      : searchText.trim()
        ? `Search: ${searchText.trim()} (${filteredRows.length})`
        : ''

  function beginSidebarResize(event: React.PointerEvent<HTMLDivElement>): void {
    event.preventDefault()
    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handleMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.min(620, Math.max(300, window.innerWidth - moveEvent.clientX))
      setSidebarWidth(nextWidth)
    }
    const handleUp = () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
    }

    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
  }

  const activeAuditStep = auditRunning ? AUDIT_STEPS[auditStepIndex] : 'Ready'
  const leftPaneWidth = leftRailCollapsed ? 44 : 240
  const rightPaneWidth = rightSidebarCollapsed ? 42 : sidebarWidth

  const eventModalOverlays = expandedClip && overlayPayload
    ? overlaysForClip(expandedClip, overlayPayload)
    : []
  const clipModalYoloLabelKey = expandedClipRow
    ? yoloTrackLabelStorageKey(reportWithDiff.watch_report.title, expandedClipRow)
    : ''
  void clipModalYoloLabelRevision
  void clipModalYoloLabelKey
  const labeledEventModalOverlays = eventModalOverlays.map((overlay) => (
    yoloOverlayWithLabel(
      overlay,
      yoloLabelForOverlay(overlay, clipModalYoloLabelEvents, clipModalYoloLabels, clipModalMemorySuggestions, clipModalYoloBoxRejections, clipModalPlaybackSeconds),
    )
  ))
  const sessionVisibleOverlays = expandedClipRow
    ? selectVisibleOverlays(annotationSession, clipModalPlaybackSeconds)
    : []
  const annotationModalOverlays = expandedClipRow
    ? sessionVisibleOverlays.map((overlay) => sessionOverlayToWatchOverlay(expandedClipRow, overlay))
    : []
  void clipModalAnnotationRevision
  const clipModalStoredDraft = expandedClipRow
    ? readAnnotationDraft(annotationDraftStorageKey(reportWithDiff.watch_report.title, expandedClipRow))
    : null
  const clipModalYoloSequenceEvents = [...clipModalYoloLabelEvents]
    .sort((a, b) => yoloLabelEventSortValue(a, 0) - yoloLabelEventSortValue(b, 0))
  const clipModalSelectedYoloStateEvent = clipModalSelectedYoloTrackId
    ? latestYoloLabelEventForTrack(clipModalYoloLabelEvents, clipModalSelectedYoloTrackId, clipModalPlaybackSeconds)
    : null
  const clipModalSelectedYoloStateLabel = clipModalSelectedYoloStateEvent
    ? yoloLabelFromEvent(clipModalSelectedYoloStateEvent)
    : null
  const clipModalYoloSequenceRows = clipModalYoloSequenceEvents
    .filter((event) => !clipModalSelectedYoloTrackId || event.track_id === clipModalSelectedYoloTrackId)
    .map((event, index) => yoloSequenceRowFromEvent(event, index))
    .slice(-8)
  const clipModalWatchSequenceRows = expandedClipRow
    ? watchSequenceRowsFromAnnotationSession(annotationSession)
    : []
  const clipModalIdentitySequenceRows = [
    ...clipModalYoloSequenceRows,
    ...clipModalWatchSequenceRows,
  ].sort((a, b) => a.sortValue - b.sortValue).slice(-12)
  const clipModalYoloSequenceSummary = clipModalYoloSequenceEvents
    .slice(-5)
    .map((event) => {
      const time = yoloLabelEventTime(event)
      const label = yoloLabelFromEvent(event)
      const display = label?.characterName || 'Unassigned'
      return `${time == null ? '--' : time.toFixed(2)}s ${event.track_id} ${display}`
    })
    .join(' | ')
  const modalOverlays = [
    ...labeledEventModalOverlays,
    ...(clipModalManualDrawEnabled ? annotationModalOverlays : []),
  ]
  const modalOverlaySource = [
    labeledEventModalOverlays.length > 0 ? `${labeledEventModalOverlays.length} YOLO person box${labeledEventModalOverlays.length === 1 ? '' : 'es'}` : '',
    clipModalManualDrawEnabled && annotationModalOverlays.length > 0 ? `${annotationModalOverlays.length} human keyframe annotation${annotationModalOverlays.length === 1 ? '' : 's'}` : '',
  ].filter(Boolean).join(' · ')
  const clipModalDeleteTarget = selectDeleteTarget(annotationSession)
  const clipModalSessionKeyframeCount = countAnnotationSessionKeyframes(annotationSession)
  const clipModalPreviewBbox = clipModalStoredDraft?.draftBbox
    ?? clipModalStoredDraft?.savedBoxes?.find((box) => box.characterName === clipModalCharacterName)?.bbox
    ?? clipModalStoredDraft?.savedBoxes?.[0]?.bbox
    ?? null
  const clipModalPreviewImageSrc = clipModalStoredDraft?.capturedFrameDataUrl || (expandedClipRow ? sceneThumbUrl(expandedClipRow) : null)
  const clipModalAdjustmentEvents = Array.isArray(clipModalStoredDraft?.adjustmentEvents) ? clipModalStoredDraft.adjustmentEvents : []
  const clipModalLastAdjustment = clipModalAdjustmentEvents[clipModalAdjustmentEvents.length - 1]
  const clipModalTransformHandles: Array<{ handle: BboxResizeHandle; label: string; className: string }> = [
    { handle: 'nw', label: 'top-left', className: 'handle handle-tl' },
    { handle: 'n', label: 'top-center', className: 'handle handle-tc' },
    { handle: 'ne', label: 'top-right', className: 'handle handle-tr' },
    { handle: 'e', label: 'right', className: 'handle handle-r' },
    { handle: 'se', label: 'bottom-right', className: 'handle handle-br' },
    { handle: 's', label: 'bottom-center', className: 'handle handle-bc' },
    { handle: 'sw', label: 'bottom-left', className: 'handle handle-bl' },
    { handle: 'w', label: 'left', className: 'handle handle-l' },
  ]

  return (
    <div style={{ height: '100%', display: 'grid', gridTemplateColumns: `${leftPaneWidth}px minmax(0, 1fr) ${rightSidebarCollapsed ? '0px' : '6px'} ${rightPaneWidth}px`, background: '#0b0d10', color: '#e6edf3', overflow: 'hidden' }}>
      <style>{`
        @keyframes watch-status-pulse {
          0%, 100% { opacity: 0.48; box-shadow: 0 0 0 0 rgba(187,134,252,0.42); }
          50% { opacity: 1; box-shadow: 0 0 0 6px rgba(187,134,252,0); }
        }
        .status-indicator {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #bb86fc;
          animation: watch-status-pulse 1.5s infinite;
        }
        .annotation-box {
          position: absolute;
          border: 1px solid #FFD700;
          cursor: move;
          box-sizing: border-box;
          will-change: transform;
        }
        .annotation-box[data-mode="resizing"] {
          cursor: crosshair;
        }
        .annotation-box.interpolated {
          border-style: dashed;
          border-color: rgba(255, 215, 0, 0.68);
          pointer-events: auto;
        }
        .annotation-box .handle {
          position: absolute;
          width: 6px;
          height: 6px;
          background: rgba(2, 6, 7, 0.16);
          border: 1px solid #FFD700;
          border-radius: 1px;
          box-shadow: 0 0 0 1px rgba(2, 6, 7, 0.78);
          pointer-events: auto;
          z-index: 2;
          opacity: 0;
          transition: opacity 0.1s ease-in-out, background 0.1s ease-in-out, box-shadow 0.1s ease-in-out;
        }
        .annotation-box:hover .handle,
        .annotation-box[data-selected="true"] .handle,
        .annotation-box[data-mode="moving"] .handle,
        .annotation-box[data-mode="resizing"] .handle {
          opacity: 1;
        }
        .annotation-box .handle:hover,
        .annotation-box[data-mode="resizing"] .handle {
          background: rgba(2, 6, 7, 0.32);
          box-shadow: 0 0 0 1px rgba(2, 6, 7, 0.9), 0 0 8px rgba(255, 215, 0, 0.48);
        }
        .annotation-box .handle-tl { top: -4px; left: -4px; cursor: nwse-resize; }
        .annotation-box .handle-tc { top: -4px; left: 50%; margin-left: -3px; cursor: ns-resize; }
        .annotation-box .handle-tr { top: -4px; right: -4px; cursor: nesw-resize; }
        .annotation-box .handle-r { top: 50%; right: -4px; margin-top: -3px; cursor: ew-resize; }
        .annotation-box .handle-br { right: -4px; bottom: -4px; cursor: nwse-resize; }
        .annotation-box .handle-bc { left: 50%; bottom: -4px; margin-left: -3px; cursor: ns-resize; }
        .annotation-box .handle-bl { bottom: -4px; left: -4px; cursor: nesw-resize; }
        .annotation-box .handle-l { top: 50%; left: -4px; margin-top: -3px; cursor: ew-resize; }
        [data-qid="watch:clip-modal:evidence-viewport"] .clip-modal-label-editor {
          opacity: 1;
          transform: translateY(0);
          transition: none;
        }
        [data-qid="watch:clip-modal:evidence-viewport"] .clip-modal-overlay-contract {
          opacity: 0;
          transform: translateY(-5px);
          pointer-events: none;
          transition: opacity 140ms ease, transform 140ms ease;
        }
        [data-qid="watch:clip-modal:evidence-viewport"]:hover .clip-modal-overlay-contract {
          opacity: 1;
          transform: translateY(0);
        }
      `}</style>
      {/* Command rail */}
      <aside data-qid="watch:audit-rail" data-collapsed={leftRailCollapsed ? 'true' : 'false'} style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 12, padding: leftRailCollapsed ? '10px 6px 54px' : '14px 12px 54px', borderRight: '1px solid rgba(255,255,255,0.08)', background: 'rgba(9,11,13,0.98)', overflow: 'auto' }}>
        {leftRailCollapsed ? (
          <button
            type="button"
            data-qid="watch:left-rail:expand"
            aria-label="Expand Watch audit rail"
            title="Expand Watch audit rail"
            onClick={() => setLeftRailCollapsed(false)}
            style={{ width: 32, height: 32, border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, background: 'rgba(255,255,255,0.04)', color: '#f59e0b', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          >
            <SlidersHorizontal size={15} />
          </button>
        ) : (
          <>
            <div data-qid="watch:left-rail:mode-toggle" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, padding: 3, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 7, background: 'rgba(255,255,255,0.035)' }}>
              {(['library', 'audit'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  data-qid={`watch:left-rail:mode-${mode}`}
                  onClick={() => setLeftRailMode(mode)}
                  style={{ border: 0, borderRadius: 5, background: leftRailMode === mode ? 'rgba(78,161,255,0.18)' : 'transparent', color: leftRailMode === mode ? '#e6edf3' : '#8fa1b8', padding: '6px 7px', fontSize: 9, fontWeight: 850, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer' }}
                >
                  {mode === 'audit' ? 'Audit Rail' : 'Library'}
                </button>
              ))}
            </div>

            {leftRailMode === 'audit' && reportWithDiff.diff_intelligence && reportWithDiff.diff_intelligence.anomaly_count > 0 && (
              <>
                <section style={{ display: 'grid', gap: 8 }}>
                  <div style={{ color: '#f59e0b', fontSize: 9, fontWeight: 850, letterSpacing: '0.16em', textTransform: 'uppercase' }}>Forensic Audit — {reportWithDiff.diff_intelligence.overall_diff_percentage}% DIFF</div>
                  <div style={{ display: 'grid', gap: 7 }}>
                    {Object.entries(reportWithDiff.diff_intelligence.category_counts).map(([cat, count]) => {
                      if (count === 0) return null
                      return (
                        <button key={cat} type="button" onClick={() => isolateDiffCategory(cat)} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', alignItems: 'center', gap: 8, border: `1px solid ${activeDiffCategory === cat ? diffCategoryColor(cat) : 'rgba(255,255,255,0.09)'}`, borderRadius: 6, background: activeDiffCategory === cat ? 'rgba(3,218,198,0.12)' : 'rgba(255,255,255,0.035)', color: activeDiffCategory === cat ? '#e6edf3' : '#b8c2d0', padding: '7px 8px', fontSize: 10, fontWeight: 800, cursor: 'pointer', textAlign: 'left' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                            <span style={{ color: diffCategoryColor(cat) }}>{diffCategorySymbol(cat)}</span>
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{diffCategoryLabel(cat)}</span>
                            <span style={{ color: '#8fa1b8' }}>{count}</span>
                          </span>
                          <span style={{ color: '#03dac6', fontSize: 9, textTransform: 'uppercase' }}>Isolate</span>
                        </button>
                      )
                    })}
                  </div>
                </section>
                {reportWithDiff.diff_intelligence.character_intel[0] && (
                  <section style={{ display: 'grid', gap: 8, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                    <div style={{ color: '#a78bfa', fontSize: 9, fontWeight: 850, letterSpacing: '0.14em', textTransform: 'uppercase' }}>Key Entity</div>
                    <div style={{ padding: 9, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, background: 'rgba(255,255,255,0.03)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 5 }}>
                        <span style={{ color: '#e2e8f0', fontSize: 11, fontWeight: 850, textTransform: 'uppercase' }}>{reportWithDiff.diff_intelligence.character_intel[0].name}</span>
                        <span style={{ color: '#8fa1b8', fontSize: 10 }}>{reportWithDiff.diff_intelligence.character_intel[0].divergence_count} diff{reportWithDiff.diff_intelligence.character_intel[0].divergence_count === 1 ? '' : 's'}</span>
                      </div>
                      <div style={{ color: '#7f8b9d', fontSize: 10, lineHeight: 1.4, marginBottom: 8 }}>{reportWithDiff.diff_intelligence.character_intel[0].insight}</div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <button type="button" onClick={() => viewCharacterSegments(reportWithDiff.diff_intelligence!.character_intel[0].name)} style={{ border: '1px solid rgba(3,218,198,0.28)', borderRadius: 4, background: 'rgba(255,255,255,0.05)', color: '#03dac6', padding: '3px 7px', fontSize: 9, fontWeight: 800, cursor: 'pointer', textTransform: 'uppercase' }}>Segments</button>
                        <button type="button" onClick={() => viewCharacterEvidence(reportWithDiff.diff_intelligence!.character_intel[0])} style={{ border: '1px solid rgba(187,134,252,0.3)', borderRadius: 4, background: 'rgba(255,255,255,0.05)', color: '#bb86fc', padding: '3px 7px', fontSize: 9, fontWeight: 800, cursor: 'pointer', textTransform: 'uppercase' }}>Evidence</button>
                      </div>
                    </div>
                  </section>
                )}
              </>
            )}

            {leftRailMode === 'library' && (
              <section data-qid="watch:asset-library" style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <div>
                    <div style={{ color: '#4ea1ff', fontSize: 9, fontWeight: 900, letterSpacing: '0.16em', textTransform: 'uppercase' }}>Asset Library</div>
                    <div style={{ color: '#6b7a8f', fontSize: 10, marginTop: 2 }}>Movie exploration and ingest well</div>
                  </div>
                  <Film size={16} color="#4ea1ff" />
                </div>

                <div data-qid="watch:asset-library:filters" style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                  {ASSET_KIND_OPTIONS.map((filter) => (
                    <button
                      key={filter.id}
                      type="button"
                      data-qid="watch:asset-library:filter"
                      data-filter={filter.id}
                      onClick={() => setAssetFilterKind(filter.id)}
                      style={{ border: `1px solid ${assetFilterKind === filter.id ? '#03dac6' : 'rgba(255,255,255,0.09)'}`, borderRadius: 999, background: assetFilterKind === filter.id ? 'rgba(3,218,198,0.12)' : 'rgba(255,255,255,0.035)', color: assetFilterKind === filter.id ? '#d7fff9' : '#8fa1b8', padding: '4px 7px', fontSize: 9, fontWeight: 800, cursor: 'pointer' }}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>

                <label style={{ display: 'grid', gap: 5 }}>
                  <span style={{ color: '#7f8b9d', fontSize: 9, fontWeight: 850, letterSpacing: '0.12em', textTransform: 'uppercase' }}>Explore</span>
                  <input
                    data-qid="watch:asset-library:search"
                    value={assetLibraryQuery}
                    onChange={(event) => setAssetLibraryQuery(event.target.value)}
                    placeholder="Filter movies, drones, web streams"
                    style={{ height: 30, border: '1px solid rgba(78,161,255,0.18)', borderRadius: 5, background: '#0c1422', color: '#d9e3f0', padding: '0 8px', outline: 'none', fontSize: 11 }}
                  />
                </label>

                <div style={{ display: 'grid', gap: 7 }}>
                  {visibleAssetLibraryItems.map((asset) => {
                    const meta = ASSET_KIND_META[asset.kind]
                    const Icon = meta.Icon
                    return (
	                      <div
	                        key={asset.id}
	                        role="button"
	                        tabIndex={0}
	                        data-qid="watch:asset-library:item"
	                        onClick={() => {
	                          setSearchText('')
	                          setActiveDiffCategory(null)
	                          setShowDivergencesOnly(false)
	                        }}
	                        onKeyDown={(event) => {
	                          if (event.key !== 'Enter' && event.key !== ' ') return
	                          event.preventDefault()
	                          setSearchText('')
	                          setActiveDiffCategory(null)
	                          setShowDivergencesOnly(false)
	                        }}
		                        style={{ display: 'grid', gridTemplateColumns: '20px minmax(0, 1fr)', alignItems: 'start', gap: 8, minWidth: 0, textAlign: 'left', border: `1px solid ${asset.selected ? 'rgba(78,161,255,0.32)' : 'rgba(255,255,255,0.08)'}`, borderRadius: 7, background: asset.selected ? 'rgba(78,161,255,0.08)' : 'rgba(255,255,255,0.03)', color: '#dce6f1', padding: 9, cursor: 'pointer' }}
	                      >
                        <span style={{ width: 20, height: 17, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', paddingTop: 1 }}>
                          <Icon size={16} color={meta.color} />
                        </span>
	                        <span style={{ display: 'grid', gap: 4, minWidth: 0 }}>
		                          <span style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', alignItems: 'center', gap: 8, minWidth: 0 }}>
		                            <span title={asset.title} style={{ display: 'block', minWidth: 0, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11, fontWeight: 850 }}>{asset.title}</span>
	                            <span style={{ border: `1px solid ${asset.diffPercent >= 50 ? 'rgba(239,68,68,0.42)' : asset.diffPercent > 0 ? 'rgba(245,158,11,0.4)' : 'rgba(34,229,139,0.32)'}`, borderRadius: 999, background: asset.diffPercent >= 50 ? 'rgba(239,68,68,0.12)' : asset.diffPercent > 0 ? 'rgba(245,158,11,0.1)' : 'rgba(34,229,139,0.08)', color: asset.diffPercent >= 50 ? '#ffb4b4' : asset.diffPercent > 0 ? '#fbbf24' : '#22e58b', fontSize: 8, fontWeight: 900, whiteSpace: 'nowrap', padding: '1px 5px', textTransform: 'uppercase' }}>{asset.statusLabel}</span>
	                          </span>
	                          <span style={{ color: '#7f8b9d', fontSize: 10, lineHeight: 1.35 }}>{asset.subtitle}</span>
	                          <span style={{ display: 'grid', gap: 3 }}>
	                            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
	                              <span style={{ color: meta.color, fontSize: 9, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{meta.label}</span>
	                              <span style={{ color: '#8fa1b8', fontSize: 9, fontFamily: 'ui-monospace, monospace' }}>{asset.auditProgress}%</span>
	                            </span>
		                            <span aria-label="Audit completion" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={asset.auditProgress} style={{ height: 4, borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,0.08)' }}>
		                              <span style={{ display: 'block', width: `${asset.auditProgress}%`, height: '100%', background: `linear-gradient(90deg, ${meta.color}, #03dac6)` }} />
		                            </span>
		                          </span>
		                          {asset.selected && (
		                            <section data-qid="watch:asset-library:progress" style={{ display: 'grid', gap: 7, paddingTop: 6, marginTop: 2, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
		                              <button
		                                type="button"
		                                data-qid="watch:asset-library:pipeline-toggle"
		                                aria-expanded={ingestPipelineOpen}
		                                onClick={(event) => {
		                                  event.stopPropagation()
		                                  setIngestPipelineOpen((current) => !current)
		                                }}
		                                style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', alignItems: 'center', gap: 8, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, background: 'rgba(255,255,255,0.025)', color: '#dce6f1', padding: '6px 7px', cursor: 'pointer', textAlign: 'left' }}
		                              >
		                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
		                                  <GitBranch size={13} color={ingestJob?.status === 'running' ? '#4ea1ff' : '#8fa1b8'} />
		                                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 9, fontWeight: 850, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
		                                    {ingestJob?.status === 'running' ? 'Active ingest pipeline' : 'Ingest pipeline'}
		                                  </span>
		                                </span>
		                                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: '#8fa1b8', fontSize: 9, fontFamily: 'ui-monospace, monospace' }}>
		                                  {ingestCompleteCount}/{activeIngestStages.length}
		                                  <ChevronRight size={12} style={{ transform: ingestPipelineOpen ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 160ms cubic-bezier(0.4, 0, 0.2, 1)' }} />
		                                </span>
		                              </button>
		                              <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={ingestStageProgress} data-qid="watch:asset-library:progressbar" style={{ height: 4, borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,0.08)' }}>
		                                <div style={{ width: `${ingestStageProgress}%`, height: '100%', background: 'linear-gradient(90deg,#03dac6,#4ea1ff)' }} />
		                              </div>
		                              {ingestPipelineOpen && (
		                                <div data-qid="watch:asset-library:pipeline-details" style={{ display: 'grid', gap: 6, paddingTop: 1 }}>
		                                  {activeIngestStages.map((stage) => {
		                                    const statusColor = stage.status === 'complete' ? '#22e58b' : stage.status === 'running' ? '#4ea1ff' : stage.status === 'blocked' ? '#f59e0b' : '#7f8b9d'
		                                    const StageIcon = stage.status === 'complete' ? CheckCircle2 : stage.status === 'running' ? RefreshCw : stage.status === 'blocked' ? AlertTriangle : CircleDashed
		                                    return (
		                                      <div key={stage.id} data-qid="watch:asset-library:stage" data-status={stage.status} style={{ display: 'grid', gridTemplateColumns: '17px minmax(0, 1fr)', gap: 7, alignItems: 'start' }}>
		                                        <StageIcon size={13} color={statusColor} style={{ marginTop: 1 }} />
		                                        <div style={{ minWidth: 0 }}>
		                                          <div style={{ color: '#d2dbea', fontSize: 10, fontWeight: 800 }}>{stage.label}</div>
		                                          <div style={{ color: '#7f8b9d', fontSize: 9, lineHeight: 1.35, overflow: 'hidden', textOverflow: 'ellipsis' }}>{stage.detail}</div>
		                                        </div>
		                                      </div>
		                                    )
		                                  })}
		                                </div>
		                              )}
		                            </section>
		                          )}
		                        </span>
		                      </div>
                    )
                  })}
                  {visibleAssetLibraryItems.length === 0 && (
                    <div data-qid="watch:asset-library:empty" style={{ border: '1px dashed rgba(255,255,255,0.12)', borderRadius: 7, padding: 10, color: '#7f8b9d', fontSize: 10, lineHeight: 1.45 }}>
                      No loaded assets match this filter. The multi-asset backend is not connected yet.
                    </div>
                  )}
                </div>

	                <section data-qid="watch:asset-library:ingest" style={{ display: 'grid', gap: 8, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
	                  <button
	                    type="button"
	                    data-qid="watch:asset-library:ingest-toggle"
	                    onClick={() => setAssetIngestOpen((value) => !value)}
	                    style={{ display: 'grid', gridTemplateColumns: '16px minmax(0, 1fr) auto', alignItems: 'center', gap: 7, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 7, background: assetIngestOpen ? 'rgba(3,218,198,0.08)' : 'rgba(255,255,255,0.025)', color: '#e2e8f0', padding: '7px 8px', cursor: 'pointer', textAlign: 'left' }}
	                  >
	                    <Upload size={14} color="#03dac6" />
	                    <span style={{ display: 'grid', gap: 2 }}>
	                      <span style={{ fontSize: 10, fontWeight: 850, textTransform: 'uppercase', letterSpacing: '0.1em' }}>New asset</span>
	                      <span style={{ color: '#7f8b9d', fontSize: 9 }}>Movie, local path, web, RTSP, telemetry</span>
	                    </span>
	                    <ChevronRight size={13} style={{ transform: assetIngestOpen ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 160ms ease' }} />
	                  </button>
	                  {assetIngestOpen && (
	                    <div data-qid="watch:asset-library:ingest-form" style={{ display: 'grid', gap: 8 }}>
	                      <textarea
	                        data-qid="watch:asset-library:source-input"
	                        value={pendingSource}
	                        onChange={(event) => setPendingSource(event.target.value)}
	                        placeholder="Movie title, local path, YouTube URL, RTSP/telemetry source"
	                        rows={3}
	                        style={{ width: '100%', resize: 'vertical', minHeight: 58, border: '1px solid rgba(78,161,255,0.18)', borderRadius: 6, background: '#0c1422', color: '#d9e3f0', padding: 8, outline: 'none', fontSize: 10, lineHeight: 1.35, boxSizing: 'border-box' }}
	                      />
	                      <button
	                        type="button"
	                        data-qid="watch:asset-library:start-ingest"
	                        disabled={!pendingSource.trim() || ingestJob?.status === 'running'}
	                        onClick={() => { void startWatchIngest() }}
	                        title={pendingSource.trim() ? WATCH_INGEST_CONTRACT : 'Enter a movie title, URL, or local path first'}
	                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, border: `1px solid ${pendingSource.trim() ? 'rgba(3,218,198,0.32)' : 'rgba(245,158,11,0.28)'}`, borderRadius: 5, background: pendingSource.trim() ? 'rgba(3,218,198,0.09)' : 'rgba(245,158,11,0.08)', color: pendingSource.trim() ? '#03dac6' : '#fbbf24', padding: '6px 8px', fontSize: 9, fontWeight: 850, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: pendingSource.trim() && ingestJob?.status !== 'running' ? 'pointer' : 'not-allowed', opacity: pendingSource.trim() ? 1 : 0.85 }}
	                      >
	                        {ingestJob?.status === 'running' ? <RefreshCw size={13} /> : <Cpu size={13} />}
	                        {ingestJob?.status === 'running' ? 'Ingest running' : 'Start Watch ingest'}
	                      </button>
	                      {ingestError && (
	                        <div data-qid="watch:asset-library:ingest-error" style={{ color: '#ff8a8a', fontSize: 9, lineHeight: 1.35 }}>
	                          {ingestError}
	                        </div>
	                      )}
	                      {ingestJob?.report_path && (
	                        <div data-qid="watch:asset-library:report-ready" style={{ border: '1px solid rgba(78,161,255,0.26)', borderRadius: 5, background: 'rgba(78,161,255,0.08)', color: '#9dc6ff', padding: '5px 7px', fontSize: 9, fontWeight: 800, lineHeight: 1.35 }}>
	                          Report artifact: {ingestJob.report_path}
	                        </div>
	                      )}
	                    </div>
	                  )}
	                </section>

              </section>
            )}
          </>
        )}
        {!leftRailCollapsed && (
          <button
            type="button"
            data-qid="watch:left-rail:collapse"
            aria-label="Collapse Watch audit rail"
            title="Collapse Watch audit rail"
            onClick={() => setLeftRailCollapsed(true)}
            style={{ position: 'absolute', right: 8, bottom: 8, width: 30, height: 30, border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, background: 'rgba(255,255,255,0.045)', color: '#8fa1b8', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: '0 8px 22px rgba(0,0,0,0.34)' }}
          >
            <ChevronLeft size={15} />
          </button>
        )}
      </aside>

      {/* Main panel */}
      <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid #252a31', overflow: 'hidden' }}>
        {/* Search header */}
        <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid #252a31', background: '#111315' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ color: '#6b7a8f', fontSize: 10, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase' }}>Scene Search</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button onClick={() => {
                setShowDivergencesOnly(!showDivergencesOnly)
                setActiveDiffCategory(null)
              }}
                style={{ border: `1px solid ${showDivergencesOnly ? '#f59e0b' : '#223149'}`, borderRadius: 4, background: showDivergencesOnly ? 'rgba(245,158,11,0.12)' : 'transparent', color: showDivergencesOnly ? '#fbbf24' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer' }}
              >{activeDiffCategory ? `${diffCategoryLabel(activeDiffCategory)} Isolated` : showDivergencesOnly ? '✦ Divergences On' : '✦ Show Divergences'}</button>
              <button
                type="button"
                data-qid="watch:playback:pause-on-divergence"
                onClick={() => setPauseOnDivergence((value) => !value)}
                style={{ border: `1px solid ${pauseOnDivergence ? '#f59e0b' : '#223149'}`, borderRadius: 4, background: pauseOnDivergence ? 'rgba(245,158,11,0.12)' : 'transparent', color: pauseOnDivergence ? '#fbbf24' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer' }}
              >
                Pause on diff {pauseOnDivergence ? 'On' : 'Off'}
              </button>
              <div style={{ display: 'inline-flex', border: '1px solid #223149', borderRadius: 4, overflow: 'hidden' }}>
                {(['compact', 'standard', 'expanded'] as const).map((d) => (
                  <button key={d} onClick={() => setDensity(d)}
                    style={{ border: 0, background: density === d ? '#1c3558' : 'transparent', color: density === d ? '#e8f1ff' : '#8490a1', padding: '5px 9px', fontSize: 9, fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', cursor: 'pointer' }}
                  >{d}</button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Search size={15} style={{ color: '#a7b3c5', flexShrink: 0 }} />
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)}
              placeholder="Find coughs, laughs, Santa hat, bottle, or exact lines"
              style={{ flex: 1, height: 34, border: '1px solid #1f2d44', borderRadius: 4, background: '#0c1422', color: '#d9e3f0', padding: '0 10px', outline: 'none', fontSize: 12 }}
            />
          </div>
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <div style={{ color: '#6b7a8f', fontSize: 11 }}>{filteredRows.length} of {reportWithDiff.scene_elements.length} rows visible{activeDiffCategory ? ` (${diffCategoryLabel(activeDiffCategory).toLowerCase()} isolated)` : showDivergencesOnly ? ' (divergences only)' : density === 'compact' ? ` (${compactSkippedRows} nominal skipped)` : ''}</div>
            {activeFilterLabel && (
              <button type="button" className="watch-filter-breadcrumb" onClick={clearForensicFilters} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: `1px solid ${activeDiffCategory ? diffCategoryColor(activeDiffCategory) : 'rgba(78,161,255,0.32)'}`, borderRadius: 999, background: activeDiffCategory ? 'rgba(3,218,198,0.08)' : 'rgba(78,161,255,0.08)', color: '#dce5f3', padding: '4px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}>
                <span style={{ color: activeDiffCategory ? diffCategoryColor(activeDiffCategory) : '#4ea1ff' }}>Filtering:</span>
                <span>{activeFilterLabel}</span>
                <span style={{ color: '#8fa1b8' }}>×</span>
              </button>
            )}
            {forensicPause && (
              <button
                type="button"
                data-qid="watch:playback:forensic-pause"
                onClick={() => {
                  setSelectedRow(forensicPause.rowIndex)
                  focusAuditRow(forensicPause.rowIndex)
                }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid rgba(245,158,11,0.45)', borderRadius: 999, background: 'rgba(245,158,11,0.11)', color: '#ffd37c', padding: '4px 8px', fontSize: 10, fontWeight: 800, cursor: 'pointer' }}
              >
                <span>Paused:</span>
                <span>{forensicPause.label}</span>
                <span style={{ fontFamily: 'ui-monospace, monospace' }}>{forensicPause.timecode}</span>
              </button>
            )}
          </div>
        </div>

        <div data-qid="watch:table:scroll" style={{ flex: 1, overflow: 'auto' }}>
          <table data-qid="watch:table" style={{ minWidth: 1120, width: '100%', tableLayout: 'fixed', borderCollapse: 'separate', borderSpacing: '0 4px', color: '#dce6f1', fontSize: 12 }}>
            <colgroup>
              <col style={{ width: 64 }} />
              <col style={{ width: 168 }} />
              <col style={{ width: 380 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 220 }} />
            </colgroup>
            <thead>
	              <tr style={{ background: '#111315', color: '#4ea1ff', fontSize: 10, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase' }}>
	                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>Time</th>
	                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>Evidence</th>
	                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>Scene Marker</th>
	                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>Manner</th>
	                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>SRT</th>
		                <th style={{ position: 'sticky', top: 0, zIndex: 8, textAlign: 'left', padding: '10px 8px', borderBottom: '1px solid rgba(100,255,218,0.22)', background: 'rgba(17,19,21,0.96)', backdropFilter: 'blur(5px)' }}>Audio Audit</th>
	              </tr>
	              <tr>
	                <th colSpan={6} style={{ position: 'sticky', top: 36, zIndex: 7, padding: '5px 8px 7px', borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(13,15,18,0.96)', backdropFilter: 'blur(5px)' }}>
	                  <div data-qid="watch:diagnostic-ribbon" aria-label="Diagnostic ribbon" style={{ position: 'relative', height: 12, borderRadius: 999, background: 'linear-gradient(90deg, rgba(34,229,139,0.14), rgba(245,158,11,0.1), rgba(255,71,87,0.12))', border: '1px solid rgba(255,255,255,0.08)', overflow: 'hidden' }}>
	                    {reportWithDiff.diff_intelligence?.anomalies.map((anomaly) => {
	                      const row = reportWithDiff.scene_elements.find((candidate) => candidate.index === anomaly.index)
	                      const left = Math.min(99, Math.max(0, ((row ? clockToSeconds(row.timecode) : 0) / movieDurationSeconds) * 100))
	                      const color = diffCategoryColor(anomaly.category)
	                      return (
	                        <button
	                          key={`${anomaly.index}:${anomaly.category}`}
	                          type="button"
	                          data-qid="watch:diagnostic-ribbon:node"
	                          aria-label={`${diffCategoryLabel(anomaly.category)} at ${anomaly.timecode}`}
	                          title={`${anomaly.timecode} — ${diffCategoryLabel(anomaly.category)} — ${anomaly.detail}`}
	                          onClick={(event) => {
	                            event.stopPropagation()
	                            focusAuditRow(anomaly.index)
	                          }}
	                          style={{ position: 'absolute', left: `${left}%`, top: 1, bottom: 1, width: 3, transform: 'translateX(-1px)', border: 0, borderRadius: 999, background: color, boxShadow: `0 0 10px ${color}88`, cursor: 'pointer', padding: 0 }}
	                        />
	                      )
	                    })}
	                  </div>
	                </th>
	              </tr>
	            </thead>
	            <tbody>
	              {density === 'compact' && compactSkippedRows > 0 && (
	                <tr data-qid="watch:table:gap-indicator">
	                  <td colSpan={6} style={{ padding: '7px 10px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#8fa1b8', fontSize: 10, fontWeight: 760, letterSpacing: '0.1em', textTransform: 'uppercase', background: 'rgba(255,255,255,0.025)' }}>
	                    … {compactSkippedRows} nominal row{compactSkippedRows === 1 ? '' : 's'} skipped in Compact …
	                  </td>
	                </tr>
	              )}
              {filteredRows.slice(0, 20).map((row) => {
                const srtText = stripWhisperSource(row.srt_text ?? row.text ?? '')
                const whisperText = stripWhisperSource(row.text ?? '')
                const diff = row.diff_info
                const hasMismatch = !!diff
                const thumbSrc = sceneThumbUrl(row)
                const clipSrc = segmentVideoUrl(row)
                const entities = sceneEntities(row)
	                const visibleEntities = entities.slice(0, 2)
	                const hiddenEntityCount = Math.max(0, entities.length - visibleEntities.length)
	                const divergenceColor = hasMismatch ? diffCategoryColor(diff.category) : '#22e58b'
	                const isActivePlayback = activePlaybackRow === row.index
		                const filterByEntity = (entity: string) => {
		                  setActiveDiffCategory(null)
		                  setShowDivergencesOnly(false)
		                  setSearchText(entity)
		                  setActiveTab('agent')
		                }
		                const resolveOrFilterEntity = (entity: string) => {
		                  if (row.diff_info) {
		                    openResolutionHub(row, entity)
		                    return
		                  }
		                  filterByEntity(entity)
		                }
	                return (
                  <tr
                    key={row.index}
                    data-qid="watch:table:row"
                    data-watch-row-index={row.index}
                    data-playback-active={isActivePlayback ? 'true' : 'false'}
                    onClick={() => setSelectedRow(row.index)}
                    className={activeDiffCategory || showDivergencesOnly || searchText.trim() ? 'watch-row-enter' : undefined}
                    style={{
                      background: isActivePlayback ? 'rgba(100,255,218,0.065)' : selectedRow === row.index ? 'rgba(78,161,255,0.04)' : hasMismatch ? 'rgba(255,71,87,0.03)' : 'transparent',
                      borderLeft: isActivePlayback ? '3px solid #64ffda' : selectedRow === row.index ? '3px solid #4ea1ff' : hasMismatch ? `3px solid ${diffCategoryColor(diff.category)}` : '3px solid transparent',
                      boxShadow: isActivePlayback ? 'inset 0 0 0 1px rgba(100,255,218,0.09)' : 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#54d7ff', fontWeight: 700, whiteSpace: 'nowrap', verticalAlign: 'top' }}>{row.timecode}</td>
                    <td title={row.movie_segment ?? row.timecode} style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', verticalAlign: 'top', overflow: 'hidden' }}>
                      {clipSrc && (
                        <div
                          data-qid="watch:table:evidence-player"
                          onPointerDownCapture={() => {
                            setActivePlaybackRow(row.index)
                            setSelectedRow(row.index)
                          }}
                          onClickCapture={() => {
                            setActivePlaybackRow(row.index)
                            setSelectedRow(row.index)
                          }}
                          onPointerDown={(event) => {
                            event.stopPropagation()
                            setActivePlaybackRow(row.index)
                            setSelectedRow(row.index)
                          }}
                          style={{ position: 'relative', width: 148, aspectRatio: '16 / 9', overflow: 'hidden', background: '#050607', border: '1px solid rgba(255,255,255,0.1)' }}
                        >
                          <video
                            data-qid="watch:table:evidence-video"
                            src={clipSrc}
                            poster={thumbSrc ?? undefined}
                            controls
                            preload="metadata"
                            playsInline
                            onPointerDown={(event) => {
                              event.stopPropagation()
                              setActivePlaybackRow(row.index)
                              setSelectedRow(row.index)
                            }}
                            onMouseDown={(event) => {
                              event.stopPropagation()
                              setActivePlaybackRow(row.index)
                              setSelectedRow(row.index)
                            }}
                            onClick={(event) => {
                              event.stopPropagation()
                              setActivePlaybackRow(row.index)
                              setSelectedRow(row.index)
                            }}
                            onPlay={() => {
                              setActivePlaybackRow(row.index)
                              setSelectedRow(row.index)
                            }}
                            onTimeUpdate={(event) => syncSegmentPlayback(row, event.currentTarget)}
                            onEnded={() => setActivePlaybackRow((current) => (current === row.index ? null : current))}
                            style={{ width: '100%', height: '100%', display: 'block', objectFit: 'cover', background: '#050607' }}
                          />
                          <span style={{ position: 'absolute', left: 5, bottom: 4, borderRadius: 4, background: 'rgba(0,0,0,0.72)', color: '#ffd37c', padding: '1px 5px', fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 800 }}>{row.timecode}</span>
                          <button
                            type="button"
                            data-qid="watch:table:evidence-expand"
                            aria-label={`Expand segment ${row.movie_segment ?? row.timecode}`}
                            onClick={(event) => {
                              event.stopPropagation()
                              openExpandedClipForRow(row)
                            }}
                            style={{ position: 'absolute', top: 4, right: 4, width: 22, height: 22, border: '1px solid rgba(255,255,255,0.22)', borderRadius: 4, background: 'rgba(0,0,0,0.58)', color: '#dce6f1', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, lineHeight: 1 }}
                          >
                            ⛶
                          </button>
                        </div>
                      )}
                      {!clipSrc && thumbSrc ? <img src={thumbSrc} alt="" style={{ width: 148, aspectRatio: '16 / 9', objectFit: 'cover', display: 'block', border: '1px solid rgba(255,255,255,0.1)' }} /> : null}
                    </td>
	                    <td style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', verticalAlign: 'top' }}>
	                      <div title={calibratedVisualDescription(row)} style={{ color: '#a8b4c3', fontSize: 12, lineHeight: 1.45, whiteSpace: 'normal', overflowWrap: 'break-word' }}>
	                        {renderDomainEntityText(calibratedVisualDescription(row), entities, filterByEntity)}
	                      </div>
                      {entities.length > 0 && (
                        <div data-qid="watch:scene-marker:entities" style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 5 }}>
                          {visibleEntities.map((entity) => {
                            const colors = entityChipColors(entity)
                            return (
                              <button
                                key={`${row.index}:${entity}`}
                                type="button"
	                                title={`Filter table by ${entity}`}
	                                onClick={(event) => {
	                                  event.stopPropagation()
	                                  filterByEntity(entity)
	                                }}
                                style={{
                                  border: `1px solid ${colors.border}`,
                                  borderRadius: 999,
                                  background: colors.background,
                                  color: colors.color,
                                  padding: '1px 6px',
                                  fontSize: 9,
                                  fontWeight: 760,
                                  lineHeight: 1.1,
                                  cursor: 'pointer',
                                }}
                              >
                                {entity}
                              </button>
                            )
                          })}
                          {hiddenEntityCount > 0 && <span title={entities.slice(visibleEntities.length).join(', ')} style={{ color: '#93a4b8', fontSize: 9 }}>+{hiddenEntityCount}</span>}
                        </div>
                      )}
                    </td>
                    <td title={hasMismatch ? `${diffCategoryLabel(diff.category)} ${(diff.confidence * 100).toFixed(0)}% — ${diff.detail}` : 'SRT and audio audit match'} style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: divergenceColor, fontFamily: 'ui-monospace, monospace', fontSize: 11, whiteSpace: 'nowrap', verticalAlign: 'top', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <span
                        data-qid="watch:table:manner-dot"
                        aria-label={hasMismatch ? diffCategoryLabel(diff.category) : 'Match'}
                        style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 999, background: divergenceColor, boxShadow: `0 0 10px ${divergenceColor}55` }}
                      />
	                    </td>
		                    <td data-qid="watch:table:srt-cell" title={stripWhisperSource(srtText)} style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: isEmptyTranscript(srtText) ? '#6f7d91' : '#dce6f1', whiteSpace: 'normal', overflowWrap: 'break-word', lineHeight: 1.45, verticalAlign: 'top' }}>
		                      {isEmptyTranscript(srtText) ? 'No SRT line' : renderDomainEntityText(stripWhisperSource(srtText), entities, resolveOrFilterEntity, hasMismatch ? 'divergent' : 'verified')}
		                    </td>
		                    <td data-qid="watch:table:whisper-cell" title={stripWhisperSource(whisperText)} style={{ padding: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)', color: isEmptyTranscript(whisperText) ? '#6f7d91' : '#aebbd0', fontFamily: 'ui-monospace, monospace', whiteSpace: 'normal', overflowWrap: 'break-word', lineHeight: 1.45, verticalAlign: 'top' }}>
		                      {isEmptyTranscript(whisperText) ? 'No audio transcript' : renderDomainEntityText(stripWhisperSource(whisperText), entities, resolveOrFilterEntity, hasMismatch ? 'divergent' : 'verified')}
		                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div
        data-qid="watch:sidebar:resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize Watch sidebar"
        onPointerDown={beginSidebarResize}
        style={{
          display: rightSidebarCollapsed ? 'none' : 'block',
          cursor: 'col-resize',
          background: 'linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.09), rgba(255,255,255,0.02))',
          borderLeft: '1px solid rgba(255,255,255,0.04)',
          borderRight: '1px solid rgba(255,255,255,0.04)',
        }}
      />

      {/* Watch sidebar */}
      <aside
        data-qid="watch:right-sidebar"
        data-collapsed={rightSidebarCollapsed ? 'true' : 'false'}
        style={{
          position: 'relative',
          zIndex: 3,
          width: rightPaneWidth,
          minWidth: rightPaneWidth,
          maxWidth: rightPaneWidth,
          display: 'flex',
          flexDirection: 'column',
          background: '#08090b',
          borderLeft: '1px solid rgba(255,255,255,0.05)',
          boxShadow: auditRunning ? 'inset 1px 0 0 rgba(187,134,252,0.12)' : 'none',
          overflow: 'hidden',
        }}
      >
        {rightSidebarCollapsed ? (
          <button
            type="button"
            data-qid="watch:right-sidebar:expand"
            aria-label="Expand Watch sidebar"
            title="Expand Watch sidebar"
            onClick={() => setRightSidebarCollapsed(false)}
            style={{ position: 'relative', zIndex: 4, height: 44, width: 42, border: 0, borderLeft: '1px solid rgba(255,255,255,0.12)', borderBottom: '1px solid rgba(255,255,255,0.08)', background: '#111318', color: '#d7e2f0', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: 'inset 1px 0 0 rgba(187,134,252,0.12)' }}
          >
            <ChevronLeft size={16} />
          </button>
        ) : (
          <>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', borderBottom: '1px solid rgba(255,255,255,0.05)', background: auditRunning ? 'rgba(187,134,252,0.055)' : 'transparent' }}>
          <div
            data-qid="watch:agent:status-header"
            aria-live="polite"
            style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0, padding: '9px 12px', borderBottom: auditRunning ? '1px solid rgba(187,134,252,0.16)' : '1px solid transparent' }}
          >
            <span className={auditRunning ? 'status-indicator' : ''} style={auditRunning ? undefined : { width: 8, height: 8, borderRadius: 99, background: '#03dac6', boxShadow: '0 0 12px rgba(3,218,198,0.34)', flexShrink: 0 }} />
            <div style={{ minWidth: 0, color: auditRunning ? '#f4edff' : '#dce7f4', fontSize: 11, fontWeight: 820, letterSpacing: '0.08em', textTransform: 'uppercase', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {auditRunning ? activeAuditStep : `Memory pipeline ready (${filteredRows.length})`}
            </div>
          </div>
          <button
            type="button"
            data-qid="watch:agent:audit-button"
            onClick={runForensicAudit}
            disabled={auditRunning}
            style={{ minWidth: 70, height: 35, margin: 4, border: '1px solid rgba(187,134,252,0.28)', borderRadius: 5, background: auditRunning ? 'rgba(187,134,252,0.08)' : 'rgba(187,134,252,0.035)', color: auditRunning ? '#d8c6ff' : '#bb86fc', fontSize: 10, fontWeight: 820, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: auditRunning ? 'default' : 'pointer' }}
          >
            Audit
          </button>
          <button
            type="button"
            data-qid="watch:right-sidebar:collapse"
            aria-label="Collapse Forensic Audit sidebar"
            title="Collapse Forensic Audit sidebar"
            onClick={() => setRightSidebarCollapsed(true)}
            style={{ width: 42, border: 0, borderLeft: '1px solid rgba(255,255,255,0.05)', background: 'transparent', color: '#8b96a8', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <button onClick={() => setActiveTab('agent')} style={{
            flex: 1, border: 0, background: auditRunning ? 'rgba(187,134,252,0.06)' : 'transparent', color: activeTab === 'agent' ? '#dce4ef' : '#667184',
            padding: '9px 0', cursor: 'pointer', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            borderBottom: activeTab === 'agent' ? '2px solid #7aa7e8' : '2px solid transparent',
            boxShadow: auditRunning ? 'inset 0 0 20px rgba(187,134,252,0.045)' : 'none',
          }}><MessageSquareText size={14} /> Watch Agent</button>
          <button onClick={() => setActiveTab('annotation')} style={{
            flex: 1, border: 0, background: auditRunning ? 'rgba(187,134,252,0.06)' : 'transparent', color: activeTab === 'annotation' ? '#dce4ef' : '#667184',
            padding: '9px 0', cursor: 'pointer', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
            borderBottom: activeTab === 'annotation' ? '2px solid #7aa7e8' : '2px solid transparent',
            boxShadow: auditRunning ? 'inset 0 0 20px rgba(187,134,252,0.045)' : 'none',
          }}><NotebookPen size={14} /> Annotation</button>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          {activeTab === 'agent' ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
              <div style={{ flex: 1, minHeight: 0 }}>
                <SharedChatShell
                  surface="watch"
                  shellQid="watch:chat:shell"
                  className="ux-lab-watch-chat-shell"
                  hideHeader
                  showModeToggle={false}
                  defaultMode="compliance"
                  adapterOptions={{
                    watch: {
                      projectLabel: 'Watch',
                      reportPath,
                      answerModel,
                      sceneContext,
                      reportRows: reportWithDiff.scene_elements as unknown as WatchSceneRow[],
                      onMatchedRows: (rows) => { if (rows.length > 0) setSelectedRow(rows[0].rowIndex ?? null) },
                      onAnnotationTab: () => setActiveTab('annotation'),
                    },
                  }}
                  emptyTitle="Ask about this scene"
                  placeholder="What happens around 02:24?"
                  starterChips={[
                    { label: 'Audit divergences', prompt: 'Run a divergence audit for the current report and summarize the highest priority evidence.' },
                    { label: 'Isolate Willie', prompt: 'Isolate Willie dialogue and explain the strongest sanitization or semantic divergence evidence.' },
                    { label: 'Evidence report', prompt: selectedRow != null ? `Generate an evidence report for ${reportWithDiff.scene_elements.find(r => r.index === selectedRow)?.timecode ?? 'the selected scene'}.` : 'Generate an evidence report for the current Watch report.' },
                  ]}
                  sidebar
                />
              </div>
            </div>
          ) : (
            <div className="watch-body" style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
              <style>{SIDEBAR_CSS}</style>
              {selectedRow != null ? (() => {
                const row = reportWithDiff.scene_elements.find(r => r.index === selectedRow)!
	                return (<>
	                  {resolutionHub && resolutionHub.rowIndex === row.index && (
	                    <section data-qid="watch:resolution-hub" style={{ background: 'rgba(245,158,11,0.055)', border: '1px solid rgba(245,158,11,0.28)', borderRadius: 8, padding: 14 }}>
	                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
	                        <div>
	                          <div style={{ color: '#f59e0b', fontSize: 10, fontWeight: 850, letterSpacing: '0.14em', textTransform: 'uppercase' }}>Resolution Hub</div>
	                          <div style={{ color: '#dce6f1', fontSize: 12, fontWeight: 800, marginTop: 3 }}>{resolutionHub.entity} · {resolutionHub.timecode}</div>
	                        </div>
	                        <span style={{ color: '#ffd37c', fontSize: 10, fontWeight: 800, textTransform: 'uppercase' }}>{resolutionHub.diffLabel}</span>
	                      </div>
	                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
	                        <div style={{ minWidth: 0, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, background: 'rgba(0,0,0,0.2)', padding: 9 }}>
	                          <div style={{ color: '#8fa1b8', fontSize: 9, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Source</div>
	                          <div style={{ color: '#c7d2e0', fontSize: 11, lineHeight: 1.5 }}>{resolutionHub.sourceText || 'No source transcript'}</div>
	                        </div>
	                        <div style={{ minWidth: 0, border: '1px solid rgba(100,255,218,0.14)', borderRadius: 6, background: 'rgba(100,255,218,0.035)', padding: 9 }}>
	                          <div style={{ color: '#64ffda', fontSize: 9, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Verified Domain Data</div>
	                          <div style={{ color: '#dce6f1', fontSize: 11, lineHeight: 1.5 }}>{resolutionHub.verifiedText}</div>
	                        </div>
	                      </div>
	                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
	                        <button type="button" data-qid="watch:resolution:batch-resolve" onClick={() => appendResolutionNote('batch_resolve')} style={{ border: '1px solid rgba(100,255,218,0.26)', borderRadius: 5, background: 'rgba(100,255,218,0.08)', color: '#64ffda', padding: '6px 9px', fontSize: 10, fontWeight: 820, cursor: 'pointer', textTransform: 'uppercase' }}>Batch Resolve All</button>
	                        <button type="button" data-qid="watch:resolution:mark-nominal" onClick={() => appendResolutionNote('mark_nominal')} style={{ border: '1px solid rgba(255,255,255,0.12)', borderRadius: 5, background: 'rgba(255,255,255,0.05)', color: '#dce6f1', padding: '6px 9px', fontSize: 10, fontWeight: 820, cursor: 'pointer', textTransform: 'uppercase' }}>Mark as Nominal</button>
	                      </div>
	                      {resolutionNotes.length > 0 && (
	                        <div data-qid="watch:resolution:audit-trail" style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'grid', gap: 4 }}>
	                          {resolutionNotes.slice(0, 3).map((note) => (
	                            <div key={note} style={{ color: '#9aa7b7', fontSize: 10, lineHeight: 1.4 }}>{note}</div>
	                          ))}
	                        </div>
	                      )}
	                    </section>
	                  )}

	                  <CharacterKeyframeAnnotation row={row} reportTitle={reportWithDiff.watch_report.title} />

                  <OrpheusClipReview row={row} selectedTags={selectedTags} setSelectedTags={setSelectedTags} />

                  {/* Training Text */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 10 }}>TRAINING TEXT</div>
                    <div style={{ fontSize: 12, lineHeight: 1.65, color: '#9ca3af' }}>
                      {row.srt_text || row.text || 'No transcript available.'}
                    </div>
                  </section>

                  {/* Orpheus Corpus */}
                  <section style={{ background: '#111418', border: '1px solid #1a1d24', borderRadius: 8, padding: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6b7280' }}>ORPHEUS CORPUS</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                      <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase' }}>TARGET /</div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>50</div>
                    </div>
                  </section>

                  {/* Forensic Insights — SRT vs Whisper diff summary */}
                  {reportWithDiff.diff_intelligence && reportWithDiff.diff_intelligence.anomaly_count > 0 && (() => {
                    const di = reportWithDiff.diff_intelligence!
                    const cc = di.category_counts
                    return (
                      <section style={{ background: '#111418', border: '1px solid #c2410c', borderRadius: 8, padding: 14 }}>
                        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f97316', marginBottom: 10 }}>
                          FORENSIC INSIGHTS — {di.overall_diff_percentage}% DIFF
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                          {cc.sanitized > 0 && (
                            <div style={{ fontSize: 11, color: '#f59e0b' }}>
                              <span style={{ fontWeight: 700 }}>[!] Sanitized:</span> {cc.sanitized} scene(s) — SRT toned down raw language vs Whisper
                            </div>
                          )}
                          {cc.hidden_dialogue > 0 && (
                            <div style={{ fontSize: 11, color: '#a855f7' }}>
                              <span style={{ fontWeight: 700 }}>[+] Hidden:</span> {cc.hidden_dialogue} scene(s) — Whisper caught dialogue SRT omitted
                            </div>
                          )}
                          {cc.acoustic_context > 0 && (
                            <div style={{ fontSize: 11, color: '#4ea1ff' }}>
                              <span style={{ fontWeight: 700 }}>[?] Occluded:</span> {cc.acoustic_context} scene(s) — SRT captured cues Whisper missed (crowd noise, etc.)
                            </div>
                          )}
                          {cc.minor_diff > 0 && (
                            <div style={{ fontSize: 11, color: '#a0a0a0' }}>
                              <span style={{ fontWeight: 700 }}>[~] Minor Diff:</span> {cc.minor_diff} scene(s) — slight wording variation
                            </div>
                          )}
                          {cc.unknown_diff > 0 && (
                            <div style={{ fontSize: 11, color: '#a0a0a0' }}>
                              <span style={{ fontWeight: 700 }}>[?] Unknown:</span> {cc.unknown_diff} scene(s)
                            </div>
                          )}
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.55, fontStyle: 'italic' }}>
                          {di.takeaways.slice(0, 2).map((t, idx) => (
                            <div key={idx} style={{ marginBottom: 4 }}>— {t}</div>
                          ))}
                        </div>
                        {di.character_intel.length > 0 && (
                          <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 8 }}>
                            <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#a78bfa', marginBottom: 6 }}>CHARACTER TRUTH</div>
                            {di.character_intel.slice(0, 4).map((ci) => (
                              <div key={ci.name} style={{ fontSize: 10, color: '#9ca3af', lineHeight: 1.5, marginBottom: 3 }}>
                                <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{ci.name}</span>
                                <span> — {ci.insight}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </section>
                    )
                  })()}
                </>)
              })() : (
                <div style={{ color: '#6b7280', fontSize: 12 }}>Select a scene row to annotate character key frames.</div>
              )}
            </div>
          )}
        </div>
          </>
        )}
      </aside>
      {expandedClip && (
        <div
          data-qid="watch:clip-modal"
          role="dialog"
          aria-modal="true"
          aria-label={`Expanded movie segment ${expandedClip.segment}`}
          onClick={closeExpandedClip}
          style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '5vh 5vw', background: 'rgba(0,0,0,0.58)', backdropFilter: 'blur(5px)' }}
        >
          <div
            data-qid="watch:clip-modal:panel"
            onClick={(event) => event.stopPropagation()}
            style={{ width: 'min(92vw, 1180px)', maxHeight: '90vh', display: 'flex', flexDirection: 'column', gap: 10, border: '1px solid rgba(255,255,255,0.16)', background: 'rgba(8,9,11,0.82)', boxShadow: '0 22px 70px rgba(0,0,0,0.62)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ color: '#ffd37c', fontFamily: 'ui-monospace, monospace', fontSize: 12, fontWeight: 800 }}>{expandedClip.segment}</div>
              <button
                type="button"
                data-qid="watch:clip-modal:close"
                aria-label="Close expanded segment"
                onClick={closeExpandedClip}
                style={{ width: 30, height: 30, border: '1px solid rgba(255,255,255,0.16)', borderRadius: 5, background: 'rgba(255,255,255,0.06)', color: '#dce6f1', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
              >
                ×
              </button>
            </div>
            <div
              data-qid="watch:clip-modal:evidence-viewport"
              style={{ position: 'relative', width: '100%', background: '#000', overflow: 'hidden' }}
            >
              <video
                ref={clipModalVideoRef}
                data-qid="watch:clip-modal:video"
                src={expandedClip.src}
                autoPlay
                playsInline
                preload="metadata"
                onLoadedMetadata={(event) => {
                  const duration = event.currentTarget.duration
                  setClipModalDurationSeconds(Number.isFinite(duration) ? duration : 0)
                  setClipModalPaused(event.currentTarget.paused)
                }}
                onPlay={() => setClipModalPaused(false)}
                onPause={() => setClipModalPaused(true)}
                onTimeUpdate={(event) => {
                  const nextSeconds = event.currentTarget.currentTime
                  setClipModalPlaybackSeconds(nextSeconds)
                  annotationDispatch(annotationSessionActions.setPlaybackTime(nextSeconds))
                }}
                style={{ width: '100%', maxHeight: 'calc(90vh - 72px)', display: 'block', objectFit: 'contain', background: '#000' }}
              />
              {modalOverlays.length > 0 || overlayPayloadError ? (
                <div
                  data-qid="watch:clip-modal:overlay-contract"
                  className="clip-modal-overlay-contract"
                  style={{
                    position: 'absolute',
                    left: 20,
                    top: 62,
                    maxWidth: 'min(640px, calc(100% - 24px))',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    border: modalOverlays.length > 0 ? '1px solid rgba(3,218,198,0.34)' : '1px solid rgba(255,179,0,0.34)',
                    background: 'rgba(8,9,11,0.72)',
                    color: modalOverlays.length > 0 ? '#7ff7e9' : '#ffd37c',
                    padding: '6px 8px',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                    fontSize: 11,
                    fontWeight: 800,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    pointerEvents: 'none',
                  }}
                >
                  {modalOverlays.length > 0 ? modalOverlaySource : `Overlay service unavailable: ${overlayPayloadError}`}
                </div>
              ) : null}
	              <div
                data-qid="watch:clip-modal:label-editor"
                className="clip-modal-label-editor"
                onClick={(event) => event.stopPropagation()}
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: 0,
                  zIndex: 8,
                  display: 'grid',
                  gridTemplateColumns: 'auto minmax(170px, 0.95fr) minmax(260px, 1.25fr) minmax(220px, 1fr)',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderBottom: '1px solid rgba(255,215,0,0.24)',
                  background: 'linear-gradient(180deg, rgba(2,6,12,0.86), rgba(2,6,12,0.58))',
                  boxShadow: '0 12px 28px rgba(0,0,0,0.36)',
                  backdropFilter: 'blur(12px)',
                  pointerEvents: 'none',
                }}
              >
                <div
                  data-qid="watch:clip-modal:hud-title"
                  style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0, pointerEvents: 'auto' }}
                >
                  <div
                    data-qid="watch:clip-modal:identity-preview"
                    title={`${clipModalCharacterName || 'Unassigned'}${clipModalActorName ? ` · ${clipModalActorName}` : ''}`}
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: '50%',
                      overflow: 'hidden',
                      border: '1px solid rgba(255,215,0,0.68)',
                      background: 'rgba(15,23,42,0.9)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#f8fafc',
                      fontSize: 13,
                      fontWeight: 900,
                      boxShadow: '0 0 0 1px rgba(0,0,0,0.55), 0 8px 20px rgba(0,0,0,0.42)',
                      flex: '0 0 auto',
                    }}
                  >
                    {clipModalPreviewImageSrc ? (
                      <img
                        data-qid="watch:clip-modal:identity-preview-image"
                        src={clipModalPreviewImageSrc}
                        alt=""
                        style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: bboxObjectPosition(clipModalPreviewBbox), display: 'block' }}
                      />
                    ) : (
                      <span>{initialsForIdentity(clipModalCharacterName, clipModalActorName)}</span>
                    )}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: '#FFD700', fontSize: 10, fontWeight: 950, letterSpacing: '0.14em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>Annotation HUD</div>
                    <div style={{ color: '#dbe7f4', fontSize: 11, lineHeight: 1.25, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Drag the viewport to create · move boxes · resize from handles</div>
                  </div>
                </div>

                <div
                  data-qid="watch:clip-modal:playback-hud"
                  style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', alignItems: 'center', gap: 8, pointerEvents: 'auto' }}
                >
                  <button
                    type="button"
                    data-qid="watch:clip-modal:playback-toggle"
                    onClick={(event) => {
                      event.stopPropagation()
                      toggleClipModalPlayback()
                    }}
                    style={{ border: '1px solid rgba(255,215,0,0.36)', borderRadius: 999, background: 'rgba(255,215,0,0.10)', color: '#ffe785', padding: '5px 10px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    {clipModalPaused ? 'Play' : 'Pause'}
                  </button>
                  <input
                    data-qid="watch:clip-modal:playback-scrubber"
                    aria-label="Scrub movie segment"
                    type="range"
                    min={0}
                    max={Math.max(clipModalDurationSeconds, clipModalPlaybackSeconds, 1)}
                    step={0.05}
                    value={Math.min(clipModalPlaybackSeconds, clipModalDurationSeconds || clipModalPlaybackSeconds || 0)}
                    onChange={(event) => seekClipModalPlayback(Number(event.target.value))}
                    style={{ width: '100%', minWidth: 0, accentColor: '#FFD700' }}
                  />
                  <div style={{ color: '#9fb4ca', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 10, fontWeight: 850, whiteSpace: 'nowrap' }}>
                    {secondsToClock(clipModalPlaybackSeconds)} / {clipModalDurationSeconds > 0 ? secondsToClock(clipModalDurationSeconds) : '--:--'}
                  </div>
                </div>

                <div
                  data-qid="watch:clip-modal:identity-fields"
                  style={{ display: 'grid', gridTemplateColumns: 'minmax(112px, 0.8fr) minmax(140px, 1fr)', alignItems: 'end', gap: 8, pointerEvents: 'auto' }}
                >
                  <label style={{ display: 'grid', gap: 2, color: '#8ea0b8', fontSize: 9, fontWeight: 850, letterSpacing: '0.1em', textTransform: 'uppercase', minWidth: 0 }}>
                    Character
                    <select
                      data-qid="watch:clip-modal:character-input"
                      value={clipModalCharacterName}
                      onChange={(event) => updateClipModalCharacter(event.target.value)}
                      style={{ height: 28, minWidth: 0, border: '1px solid rgba(255,215,0,0.32)', borderRadius: 6, background: 'rgba(2,6,12,0.78)', color: '#f8fafc', padding: '0 8px', fontSize: 12, fontWeight: 850 }}
                    >
                      {clipModalCharacterOptions.map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                  </label>
                  <label style={{ display: 'grid', gap: 2, color: '#8ea0b8', fontSize: 9, fontWeight: 850, letterSpacing: '0.1em', textTransform: 'uppercase', minWidth: 0 }}>
                    Actor
                    <input
                      data-qid="watch:clip-modal:actor-input"
                      value={clipModalActorName}
                      onChange={(event) => {
                        const nextActor = event.target.value
                        setClipModalActorName(nextActor)
                        if (clipModalCharacterName.trim()) {
                          annotationDispatch(annotationSessionActions.selectCharacter(clipModalCharacterName, nextActor || undefined))
                        }
                      }}
                      placeholder="Optional actor / identity source"
                      style={{ height: 28, minWidth: 0, border: '1px solid rgba(255,215,0,0.32)', borderRadius: 6, background: 'rgba(2,6,12,0.78)', color: '#f8fafc', padding: '0 8px', fontSize: 12, fontWeight: 850 }}
                    />
                  </label>
                </div>

                <div
                  data-qid="watch:clip-modal:adjustment-ledger"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    gap: 7,
                    minWidth: 0,
                    color: '#d6e2f0',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                    fontSize: 10,
                    fontWeight: 850,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    pointerEvents: 'auto',
                  }}
                >
                  <button
                    type="button"
                    data-qid="watch:clip-modal:manual-draw-toggle"
                    aria-pressed={clipModalManualDrawEnabled}
                    onClick={(event) => {
                      event.stopPropagation()
                      setClipModalManualDrawEnabled((enabled) => !enabled)
                      setClipModalDrawMode(false)
                      setClipModalDragStart(null)
                      setClipModalDraftBbox(null)
                      setClipModalYoloStatus(clipModalManualDrawEnabled ? 'Manual annotation drawing disabled.' : 'Manual annotation drawing enabled.')
                    }}
                    title="Enable manual box drawing"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: clipModalManualDrawEnabled ? '1px solid rgba(45,212,191,0.6)' : '1px solid rgba(148,163,184,0.28)', borderRadius: 6, background: clipModalManualDrawEnabled ? 'rgba(20,184,166,0.2)' : 'rgba(15,23,42,0.72)', color: clipModalManualDrawEnabled ? '#67e8f9' : '#dbe7f4', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                  >
                    <Pencil size={13} />
                    Draw
                  </button>
                  <button
                    type="button"
                    data-qid="watch:clip-modal:save-yolo-label"
                    disabled={!clipModalSelectedYoloTrackId}
                    onClick={(event) => {
                      event.stopPropagation()
                      void saveClipModalYoloTrackLabel()
                    }}
                    title="Accept selected YOLO track as the selected character"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid rgba(45,212,191,0.42)', borderRadius: 6, background: clipModalSelectedYoloTrackId ? 'rgba(20,184,166,0.18)' : 'rgba(15,23,42,0.32)', color: clipModalSelectedYoloTrackId ? '#99f6e4' : '#64748b', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: clipModalSelectedYoloTrackId ? 'pointer' : 'default', whiteSpace: 'nowrap' }}
                  >
                    Save YOLO
                  </button>
                  <button
                    type="button"
                    data-qid="watch:clip-modal:reset-yolo-label"
                    disabled={!clipModalSelectedYoloTrackId}
                    onClick={(event) => {
                      event.stopPropagation()
                      void resetClipModalYoloTrackLabel()
                    }}
                    title="Reject/reset selected YOLO track label"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid rgba(248,113,113,0.42)', borderRadius: 6, background: clipModalSelectedYoloTrackId ? 'rgba(127,29,29,0.32)' : 'rgba(15,23,42,0.32)', color: clipModalSelectedYoloTrackId ? '#fecaca' : '#64748b', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: clipModalSelectedYoloTrackId ? 'pointer' : 'default', whiteSpace: 'nowrap' }}
                  >
                    Reset YOLO
                  </button>
                  <button
                    type="button"
                    data-qid="watch:clip-modal:unassign-yolo-frame"
                    disabled={!clipModalSelectedYoloTrackId}
                    onClick={(event) => {
                      event.stopPropagation()
                      void unassignClipModalYoloBoxFrame()
                    }}
                    title="Unassign only the selected YOLO box at the current frame"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid rgba(250,204,21,0.42)', borderRadius: 6, background: clipModalSelectedYoloTrackId ? 'rgba(113,63,18,0.32)' : 'rgba(15,23,42,0.32)', color: clipModalSelectedYoloTrackId ? '#fde68a' : '#64748b', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: clipModalSelectedYoloTrackId ? 'pointer' : 'default', whiteSpace: 'nowrap' }}
                  >
                    Unassign frame
                  </button>
                  <button
                    type="button"
                    data-qid="watch:clip-modal:clear-keyframes"
                    disabled={clipModalSessionKeyframeCount === 0}
                    onClick={(event) => {
                      event.stopPropagation()
                      annotationDispatch(annotationSessionActions.clearSegment())
                      setClipModalSelectedOverlayId(null)
                    }}
                    title="Clear all keyframes in this video segment"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid rgba(148,163,184,0.28)', borderRadius: 6, background: clipModalSessionKeyframeCount === 0 ? 'rgba(15,23,42,0.32)' : 'rgba(15,23,42,0.72)', color: clipModalSessionKeyframeCount === 0 ? '#64748b' : '#dbe7f4', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: clipModalSessionKeyframeCount === 0 ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
                  >
                    <Trash2 size={13} />
                    Clear
                  </button>
                  <button
                    type="button"
                    data-qid="watch:clip-modal:delete-keyframe"
                    disabled={!clipModalDeleteTarget}
                    onClick={(event) => {
                      event.stopPropagation()
                      annotationDispatch(annotationSessionActions.deleteSelectedExactKeyframe())
                      setClipModalSelectedOverlayId(null)
                    }}
                    title="Delete exact keyframe at the current frame for the selected character"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: '1px solid rgba(248,113,113,0.42)', borderRadius: 6, background: clipModalDeleteTarget ? 'rgba(127,29,29,0.42)' : 'rgba(15,23,42,0.32)', color: clipModalDeleteTarget ? '#fecaca' : '#64748b', padding: '5px 8px', fontSize: 10, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: clipModalDeleteTarget ? 'pointer' : 'default', whiteSpace: 'nowrap' }}
                  >
                    <Trash2 size={13} />
                    Delete
                  </button>
                  <span style={{ border: '1px solid rgba(255,215,0,0.28)', borderRadius: 999, background: 'rgba(255,215,0,0.08)', color: '#ffe785', padding: '5px 8px' }}>{clipModalSessionKeyframeCount} KF</span>
                  <span style={{ border: '1px solid rgba(45,212,191,0.18)', borderRadius: 999, background: 'rgba(3,218,198,0.055)', color: '#9fb4ca', padding: '5px 8px' }}>{clipModalAdjustmentEvents.length} adj</span>
                  {clipModalSelectedYoloTrackId ? <span style={{ border: '1px solid rgba(34,211,238,0.24)', borderRadius: 999, background: 'rgba(8,145,178,0.12)', color: '#67e8f9', padding: '5px 8px' }}>{clipModalSelectedYoloTrackId}</span> : null}
                  {clipModalLastAdjustment ? <span title={`${clipModalLastAdjustment.type} ${clipModalLastAdjustment.timecode}`} style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: '#9fb4ca' }}>{clipModalLastAdjustment.type} {clipModalLastAdjustment.timecode}</span> : null}
                  {clipModalYoloStatus ? <span title={clipModalYoloStatus} style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: '#9fb4ca' }}>{clipModalYoloStatus}</span> : null}
                  {clipModalYoloSequenceSummary ? <span title={clipModalYoloSequenceSummary} style={{ overflow: 'hidden', textOverflow: 'ellipsis', color: '#67e8f9' }}>Seq: {clipModalYoloSequenceSummary}</span> : null}
                </div>
              </div>
              {clipModalIdentitySequenceRows.length > 0 ? (
                <section
                  data-qid="watch:clip-modal:yolo-identity-sequence"
                  aria-label="Watch identity sequence"
                  onClick={(event) => event.stopPropagation()}
                  style={{
                    position: 'absolute',
                    left: 14,
                    top: 58,
                    zIndex: 9,
                    width: 300,
                    maxWidth: 'calc(100% - 28px)',
                    border: '1px solid rgba(34,211,238,0.28)',
                    borderRadius: 8,
                    background: 'rgba(2,6,12,0.82)',
                    boxShadow: '0 16px 36px rgba(0,0,0,0.42)',
                    backdropFilter: 'blur(10px)',
                    padding: 10,
                    display: 'grid',
                    gap: 8,
                    pointerEvents: 'auto',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <div style={{ color: '#67e8f9', fontSize: 10, fontWeight: 950, letterSpacing: '0.14em', textTransform: 'uppercase' }}>Identity sequence ledger</div>
                    <div style={{ color: '#9fb4ca', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 10, fontWeight: 850 }}>
                      {clipModalSelectedYoloTrackId || 'watch + yolo'}
                    </div>
                  </div>
                  {clipModalSelectedYoloTrackId ? (
                    <div
                      data-qid="watch:clip-modal:yolo-identity-current-state"
                      style={{
                        border: '1px solid rgba(148,163,184,0.18)',
                        borderRadius: 6,
                        background: 'rgba(15,23,42,0.64)',
                        padding: '7px 8px',
                        display: 'grid',
                        gap: 3,
                      }}
                    >
                      <div style={{ color: '#94a3b8', fontSize: 9, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase' }}>State at {clipModalPlaybackSeconds.toFixed(2)}s</div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{ color: clipModalSelectedYoloStateLabel ? '#f8fafc' : '#fde68a', fontSize: 13, fontWeight: 900 }}>
                          {clipModalSelectedYoloStateLabel?.characterName || (clipModalSelectedYoloStateEvent ? 'Unassigned' : 'Unknown')}
                        </span>
                        <span style={{ color: '#9fb4ca', fontSize: 10, fontWeight: 850 }}>
                          {clipModalSelectedYoloStateEvent
                            ? isYoloIdentityStopEvent(clipModalSelectedYoloStateEvent)
                              ? 'sequence stop'
                              : 'accepted'
                            : 'no prior event'}
                        </span>
                      </div>
                    </div>
                  ) : null}
                  <div style={{ display: 'grid', gap: 5, maxHeight: 168, overflow: 'auto' }}>
                    {clipModalIdentitySequenceRows.map((row) => (
                      <div
                        key={row.key}
                        data-qid="watch:clip-modal:yolo-identity-sequence-row"
                        data-track-id={row.trackId}
                        data-sequence-state={row.tone}
                        data-sequence-source={row.source}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '54px minmax(0, 1fr)',
                          gap: 7,
                          alignItems: 'start',
                          borderLeft: `3px solid ${row.tone === 'accept' ? '#a78bfa' : row.tone === 'reset' ? '#fca5a5' : '#facc15'}`,
                          background: row.tone === 'accept' ? 'rgba(167,139,250,0.10)' : row.tone === 'reset' ? 'rgba(248,113,113,0.10)' : 'rgba(250,204,21,0.10)',
                          borderRadius: 5,
                          padding: '5px 7px',
                        }}
                      >
                        <span style={{ color: '#dbeafe', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 10, fontWeight: 900 }}>{row.timeLabel}</span>
                        <span style={{ minWidth: 0 }}>
                          <span style={{ display: 'block', color: '#f8fafc', fontSize: 11, fontWeight: 900, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.trackId} · {row.stateLabel}</span>
                          <span style={{ display: 'block', color: '#94a3b8', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.source.toUpperCase()} · {row.detailLabel}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
              <div
	                data-qid="watch:clip-modal:draw-surface"
	                onPointerDown={onClipModalPointerDown}
	                onPointerMove={onClipModalPointerMove}
	                onPointerUp={onClipModalPointerUp}
	                onPointerCancel={() => {
	                  setClipModalDrawMode(false)
	                  setClipModalDragStart(null)
	                  setClipModalDraftBbox(null)
	                }}
	                style={{
                  position: 'absolute',
                  inset: 0,
                  zIndex: 5,
                  pointerEvents: clipModalManualDrawEnabled ? 'auto' : 'none',
                  cursor: clipModalManualDrawEnabled ? 'crosshair' : 'default',
                  background: clipModalDrawMode ? 'rgba(0,0,0,0.025)' : 'transparent',
                  touchAction: 'none',
	                }}
	              >
	                {clipModalDraftBbox ? (
	                  <div
	                    data-qid="watch:clip-modal:draft-overlay"
	                    style={{
	                      position: 'absolute',
	                      ...bboxStyle(clipModalDraftBbox),
	                      border: '1px dashed #FFD700',
	                      background: 'rgba(255,179,0,0.12)',
	                      boxShadow: '0 0 0 1px rgba(0,0,0,0.28), 0 0 22px rgba(255,179,0,0.18)',
	                      boxSizing: 'border-box',
	                      pointerEvents: 'none',
	                    }}
	                  >
	                    <div
	                      data-qid="watch:clip-modal:draft-overlay-label"
	                      style={{
	                        position: 'absolute',
	                        left: -1,
	                        top: -24,
	                        background: '#FFD700',
	                        color: '#020607',
	                        padding: '3px 7px',
	                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
	                        fontSize: 10,
	                        fontWeight: 900,
	                        letterSpacing: '0.08em',
	                        textTransform: 'uppercase',
	                        whiteSpace: 'nowrap',
	                      }}
	                    >
	                      {clipModalCharacterName || 'Unassigned'}
	                    </div>
	                  </div>
	                ) : null}
	              </div>
	              {modalOverlays.map((overlay) => {
	                const candidate = overlay.identity_candidate
	                const stroke = overlay.render_policy.stroke_color ?? '#03dac6'
	                const fillOpacity = overlay.render_policy.fill_opacity ?? 0.1
	                const fill = stroke === '#22d3ee'
	                  ? `rgba(34,211,238,${fillOpacity})`
                    : stroke === '#a78bfa'
                      ? `rgba(167,139,250,${fillOpacity})`
                      : stroke === '#facc15'
                        ? `rgba(250,204,21,${fillOpacity})`
	                      : `rgba(255,179,0,${fillOpacity})`
	                const isAnnotationOverlay = overlay.overlay_id.startsWith('kf:') || overlay.overlay_id.startsWith('annotation-')
	                const isYoloOverlay = !isAnnotationOverlay
	                const isPromotableOverlay = false
	                const isSelectedOverlay = clipModalSelectedOverlayId === overlay.overlay_id
	                const overlayMode = clipModalResizeState?.overlayId === overlay.overlay_id ? 'resizing' : clipModalMoveState?.overlayId === overlay.overlay_id ? 'moving' : 'idle'
	                const overlayStrokeStyle = overlay.render_policy.stroke ?? 'solid'
	                const overlayBorder = isAnnotationOverlay
	                  ? '1px solid #FFD700'
	                  : `${overlayStrokeStyle === 'solid' ? 2 : 1}px ${overlayStrokeStyle} ${stroke}`
	                const overlayLabelBackground = isAnnotationOverlay ? '#FFD700' : stroke
                    const overlayLabelTop = overlay.bbox_percent.top < 4 ? 0 : -30
                    const labelText = isYoloOverlay && !candidate
                      ? yoloTrackDisplayName(overlay.track_id)
                      : candidate?.status === 'PROVISIONAL' && typeof candidate.confidence === 'number'
                        ? `${candidate.name}? ${candidate.confidence.toFixed(2)}`
                        : candidate?.name ?? overlay.detected_class
                    const overlayZIndex = isSelectedOverlay ? 90 : isYoloOverlay ? 70 : isAnnotationOverlay ? 60 : 16
	                return (
	                  <div
	                    key={overlay.overlay_id}
	                    className={`annotation-box ${overlay.classification === 'interpolated_keyframe' ? 'interpolated' : ''}`}
	                    data-qid="watch:clip-modal:event-overlay"
	                    data-overlay-id={overlay.overlay_id}
		                    data-track-id={overlay.track_id}
		                    data-identity-status={overlay.identity_status}
		                    data-selected={isSelectedOverlay ? 'true' : 'false'}
		                    data-mode={overlayMode}
		                    tabIndex={isAnnotationOverlay || isYoloOverlay || isPromotableOverlay ? 0 : undefined}
		                    onPointerDown={isAnnotationOverlay || isPromotableOverlay ? (event) => selectClipModalAnnotation(event, overlay) : isYoloOverlay ? (event) => selectClipModalYoloTrack(event, overlay) : undefined}
		                    onPointerMove={isAnnotationOverlay ? onClipModalMoveDrag : undefined}
		                    onPointerUp={isAnnotationOverlay ? stopClipModalMove : undefined}
		                    onPointerCancel={isAnnotationOverlay ? stopClipModalMove : undefined}
	                    style={{
	                      position: 'absolute',
	                      left: `${overlay.bbox_percent.left}%`,
	                      top: `${overlay.bbox_percent.top}%`,
	                      width: `${overlay.bbox_percent.width}%`,
	                      height: `${overlay.bbox_percent.height}%`,
	                      border: overlayBorder,
	                      background: isAnnotationOverlay ? 'transparent' : fill,
	                      boxSizing: 'border-box',
	                      pointerEvents: isAnnotationOverlay || isYoloOverlay || isPromotableOverlay ? 'auto' : 'none',
	                      cursor: isAnnotationOverlay ? 'move' : isYoloOverlay ? 'pointer' : isPromotableOverlay ? 'copy' : 'default',
	                      zIndex: overlayZIndex,
	                      boxShadow: isAnnotationOverlay
	                        ? '0 0 0 1px rgba(0,0,0,0.32), 0 0 16px rgba(255,215,0,0.16)'
	                        : `0 0 0 1px rgba(0,0,0,0.32), 0 0 24px ${fill}`,
	                    }}
	                  >
                    <div
                      data-qid="watch:clip-modal:event-overlay-label"
                      role={isYoloOverlay ? 'button' : undefined}
                      tabIndex={isYoloOverlay ? 0 : undefined}
                      onPointerDown={isYoloOverlay ? (event) => selectClipModalYoloTrack(event, overlay) : undefined}
                      style={{
                        position: 'absolute',
                        left: -2,
                        top: overlayLabelTop,
                        zIndex: 140,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 6,
                        maxWidth: 360,
                        background: overlayLabelBackground,
                        color: '#020607',
                        padding: '3px 7px',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                        fontSize: 11,
                        fontWeight: 900,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        whiteSpace: 'nowrap',
                        pointerEvents: isYoloOverlay ? 'auto' : 'none',
                        cursor: isYoloOverlay ? 'pointer' : 'default',
                        boxShadow: '0 6px 14px rgba(0,0,0,0.35)',
                      }}
                    >
	                      <span>{labelText}</span>
                      {isYoloOverlay && isSelectedOverlay ? (
                        <select
                          data-qid="watch:clip-modal:inline-yolo-character-select"
                          value={clipModalCharacterName || ''}
                          onPointerDown={(event) => {
                            event.stopPropagation()
                          }}
                          onClick={(event) => {
                            event.stopPropagation()
                          }}
                          onChange={(event) => {
                            event.stopPropagation()
                            const nextName = event.target.value
                            if (nextName === '__reset__') {
                              void resetClipModalYoloTrackLabel()
                              return
                            }
                            if (nextName === '__unassign_frame__') {
                              void unassignClipModalYoloBoxFrame()
                              return
                            }
                            setClipModalCharacterName(nextName)
                            setClipModalActorName(actorForCharacter(nextName) || '')
                          }}
                          style={{
                            height: 24,
                            minWidth: 132,
                            border: '1px solid rgba(2,6,12,0.36)',
                            borderRadius: 5,
                            background: '#020617',
                            color: '#f8fafc',
                            font: 'inherit',
                            fontSize: 10,
                            fontWeight: 900,
                            letterSpacing: '0.06em',
                            textTransform: 'none',
                          }}
                        >
                          <option value="">Choose character</option>
                          <option value="__unassign_frame__">Unassign this frame</option>
                          <option value="__reset__">Reset to {yoloTrackDisplayName(overlay.track_id)}</option>
                          {CHARACTER_OPTIONS.map((name) => (
                            <option key={name} value={name}>{name}</option>
                          ))}
                        </select>
                      ) : null}
	                      {candidate?.actor_name ? <span style={{ opacity: 0.78 }}>{candidate.actor_name}</span> : null}
	                      {candidate?.status === 'PROVISIONAL' ? <span style={{ opacity: 0.62 }}>suggested</span> : candidate ? <span style={{ opacity: 0.62 }}>{overlay.identity_status}</span> : null}
	                    </div>
	                    {isAnnotationOverlay ? (
	                      <>
	                        {clipModalTransformHandles.map((item) => (
	                          <div
	                            key={item.handle}
	                            className={item.className}
	                            data-qid="watch:clip-modal:resize-handle"
	                            data-handle-type={item.label}
	                            tabIndex={0}
	                            onPointerDown={(event) => startClipModalResize(event, overlay, item.handle)}
	                            onPointerMove={onClipModalResizeMove}
	                            onPointerUp={stopClipModalResize}
	                            onPointerCancel={stopClipModalResize}
	                          />
	                        ))}
	                      </>
	                    ) : null}
	                  </div>
	                )
	              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default WatchReportView
