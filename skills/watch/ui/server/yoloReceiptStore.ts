import { createHash } from 'node:crypto'
import { constants } from 'node:fs'
import {
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
} from 'node:fs/promises'
import path from 'node:path'

export type YoloLabelAction =
  | 'accept'
  | 'reject'
  | 'reset'
  | 'reject_box'
  | 'reset_box'

export type MemorySyncState =
  | 'pending'
  | 'stored'
  | 'failed'
  | 'legacy_unverified'

export type EventMemorySync = {
  state: MemorySyncState
  attempts: number
  last_error: string | null
  updated_at: string
}

export type YoloLabelEvent = {
  id: string
  sequence: number
  idempotency_key: string
  request_fingerprint?: string
  action: YoloLabelAction
  asset_uid: string
  row_index: number
  track_id: string
  box_key: string
  time_seconds: number | null
  timecode: string | null
  movie_segment: string | null
  created_at: string
  status: string
  character_name?: string
  actor_name?: string
  confidence?: number
  memory_sync: EventMemorySync
}

export type YoloLabelReceipt = {
  schema: 'watch.yolo_track_labels.v1'
  receipt_format_version: 2
  revision: number
  asset_uid: string
  row_index: number
  timecode: string | null
  movie_segment: string | null
  labels: Record<string, unknown>
  box_rejections: Record<string, unknown>
  events: YoloLabelEvent[]
  receipt_path: string
  updated_at: string | null
}

export type ApplyMutationInput = {
  idempotencyKey: string
  action: YoloLabelAction
  assetUid: string
  rowIndex: number
  trackId: string
  boxKey: string
  timeSeconds: number | null
  timecode: string | null
  movieSegment: string | null
  characterName?: string
  actorName?: string
  confidence?: number
}

export class MalformedYoloReceiptError extends Error {
  constructor(message: string, readonly receiptPath: string) {
    super(message)
    this.name = 'MalformedYoloReceiptError'
  }
}

export class IdempotencyConflictError extends Error {
  readonly code = 'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD'

  constructor(message = 'idempotency key reused with a different payload') {
    super(message)
    this.name = 'IdempotencyConflictError'
  }
}

export class OutOfOrderTrackEventError extends Error {
  readonly code = 'OUT_OF_ORDER_TRACK_EVENT'

  constructor(message = 'track event time is earlier than the latest persisted event for this track') {
    super(message)
    this.name = 'OutOfOrderTrackEventError'
  }
}

function safeFilePart(value: unknown, fallback: string): string {
  const raw = typeof value === 'string' && value.trim() ? value.trim() : fallback
  return raw.replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || fallback
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`)
      .join(',')}}`
  }
  return JSON.stringify(value)
}

export function eventIdFor(assetUid: string, rowIndex: number, idempotencyKey: string): string {
  return `yolo_label_${sha256(`watch.yolo_track_label_event.v1\0${assetUid}\0${rowIndex}\0${idempotencyKey}`)}`
}

export function fingerprintFor(input: ApplyMutationInput): string {
  return sha256(stableJson({
    action: input.action,
    track_id: input.trackId,
    box_key: input.boxKey,
    time_seconds: input.timeSeconds,
    character_name: input.characterName ?? null,
    actor_name: input.actorName ?? null,
    confidence: input.confidence ?? null,
    timecode: input.timecode,
    movie_segment: input.movieSegment,
  }))
}

function legacyLabelFileName(assetUid: string, rowIndex: number): string {
  return `${safeFilePart(assetUid, 'watch_asset')}_row${String(rowIndex).padStart(4, '0')}.json`
}

function labelFileName(assetUid: string, rowIndex: number): string {
  return `${safeFilePart(assetUid, 'watch_asset')}_${sha256(assetUid).slice(0, 16)}_row${String(rowIndex).padStart(4, '0')}.json`
}

function validateRelativeReceiptPath(relativePath: string): string {
  const normalized = relativePath.split(path.sep).join('/')
  if (normalized.startsWith('/') || normalized.includes('\0')) {
    throw new Error('receipt path must be relative')
  }
  const parts = normalized.split('/')
  if (parts.some((part) => part === '..')) {
    throw new Error('receipt path traversal is not allowed')
  }
  return normalized
}

function statusForAction(action: YoloLabelAction): string {
  if (action === 'accept') return 'accepted'
  if (action === 'reject_box') return 'rejected_box'
  if (action === 'reset_box') return 'reset_box'
  return action
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

async function atomicWriteJson(finalPath: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(finalPath), { recursive: true })
  const tempPath = path.join(
    path.dirname(finalPath),
    `.${path.basename(finalPath)}.${process.pid}.${Date.now()}.tmp`,
  )
  let handle: Awaited<ReturnType<typeof open>> | null = null
  try {
    handle = await open(tempPath, constants.O_CREAT | constants.O_TRUNC | constants.O_WRONLY, 0o600)
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, 'utf-8')
    await handle.sync()
    await handle.close()
    handle = null
    await rename(tempPath, finalPath)
    if (process.platform === 'linux') {
      const parent = await open(path.dirname(finalPath), constants.O_RDONLY)
      try {
        await parent.sync()
      } finally {
        await parent.close()
      }
    }
  } catch (error) {
    if (handle) {
      try {
        await handle.close()
      } catch {
        // ignore close cleanup failure; original error is more useful
      }
    }
    await rm(tempPath, { force: true })
    throw error
  }
}

export class YoloReceiptStore {
  private locks = new Map<string, Promise<void>>()

  constructor(private readonly rootDir: string) {}

  async read(assetUid: string, rowIndex: number): Promise<YoloLabelReceipt> {
    return this.withLock(assetUid, rowIndex, async () => this.readUnlocked(assetUid, rowIndex))
  }

  async applyMutation(input: ApplyMutationInput): Promise<{
    receipt: YoloLabelReceipt
    event: YoloLabelEvent
    deduplicated: boolean
  }> {
    return this.withLock(input.assetUid, input.rowIndex, async () => {
      if (!Number.isFinite(input.timeSeconds)) {
        throw new Error('time_seconds must be finite for new label mutations')
      }
      if ((input.timeSeconds ?? 0) < 0) {
        throw new Error('time_seconds must be nonnegative')
      }
      const receipt = await this.readUnlocked(input.assetUid, input.rowIndex)
      const existing = receipt.events.find((event) => event.idempotency_key === input.idempotencyKey)
      const fingerprint = fingerprintFor(input)
      if (existing) {
        if (!existing.request_fingerprint || existing.request_fingerprint !== fingerprint) {
          throw new IdempotencyConflictError()
        }
        return { receipt, event: existing, deduplicated: true }
      }

      const latestTimed = receipt.events
        .filter((event) => event.track_id === input.trackId && typeof event.time_seconds === 'number' && Number.isFinite(event.time_seconds))
        .sort((a, b) => (a.time_seconds ?? 0) - (b.time_seconds ?? 0))
        .at(-1)
      if (latestTimed && Number(input.timeSeconds) < Number(latestTimed.time_seconds)) {
        throw new OutOfOrderTrackEventError()
      }

      const now = new Date().toISOString()
      const maxSequence = receipt.events.reduce((max, event) => Math.max(max, event.sequence || 0), 0)
      const event: YoloLabelEvent = {
        id: eventIdFor(input.assetUid, input.rowIndex, input.idempotencyKey),
        sequence: maxSequence + 1,
        idempotency_key: input.idempotencyKey,
        request_fingerprint: fingerprint,
        action: input.action,
        asset_uid: input.assetUid,
        row_index: input.rowIndex,
        track_id: input.trackId,
        box_key: input.boxKey,
        time_seconds: input.timeSeconds,
        timecode: input.timecode,
        movie_segment: input.movieSegment,
        created_at: now,
        status: statusForAction(input.action),
        memory_sync: {
          state: 'pending',
          attempts: 0,
          last_error: null,
          updated_at: now,
        },
      }
      if (input.action === 'accept') {
        event.character_name = input.characterName
        event.actor_name = input.actorName
        event.confidence = input.confidence
      }

      const labels = { ...receipt.labels }
      const boxRejections = { ...receipt.box_rejections }

      if (input.action === 'accept') {
        labels[input.trackId] = {
          trackId: input.trackId,
          characterName: input.characterName,
          actorName: input.actorName || '',
          status: 'accepted',
          source: 'human',
          confidence: typeof input.confidence === 'number' ? input.confidence : 1,
          updatedAt: now,
        }
        delete boxRejections[input.boxKey]
      } else if (input.action === 'reject' || input.action === 'reset') {
        delete labels[input.trackId]
      } else if (input.action === 'reject_box' || input.action === 'reset_box') {
        delete labels[input.trackId]
        boxRejections[input.boxKey] = {
          boxKey: input.boxKey,
          trackId: input.trackId,
          timeSeconds: input.timeSeconds ?? 0,
          status: 'rejected',
          source: 'human',
          updatedAt: now,
        }
      }

      const nextReceipt: YoloLabelReceipt = {
        ...receipt,
        revision: receipt.revision + 1,
        timecode: input.timecode ?? receipt.timecode,
        movie_segment: input.movieSegment ?? receipt.movie_segment,
        labels,
        box_rejections: boxRejections,
        events: [...receipt.events, event],
        updated_at: now,
      }
      await this.persist(nextReceipt)
      return { receipt: nextReceipt, event, deduplicated: false }
    })
  }

  async updateMemorySync(
    assetUid: string,
    rowIndex: number,
    eventId: string,
    update: {
      state: MemorySyncState
      lastError?: string | null
    },
  ): Promise<YoloLabelReceipt> {
    return this.withLock(assetUid, rowIndex, async () => {
      const receipt = await this.readUnlocked(assetUid, rowIndex)
      let found = false
      let changed = false
      const now = new Date().toISOString()
      const events = receipt.events.map((event) => {
        if (event.id !== eventId) return event
        found = true
        if (event.memory_sync?.state === 'stored' && update.state !== 'stored') return event
        changed = true
        return {
          ...event,
          memory_sync: {
            state: update.state,
            attempts: (event.memory_sync?.attempts ?? 0) + 1,
            last_error: update.lastError === undefined ? event.memory_sync?.last_error ?? null : update.lastError,
            updated_at: now,
          },
        }
      })
      if (!found) throw new Error(`event not found: ${eventId}`)
      if (!changed) return receipt
      const nextReceipt = {
        ...receipt,
        revision: receipt.revision + 1,
        events,
        updated_at: now,
      }
      await this.persist(nextReceipt)
      return nextReceipt
    })
  }

  async listRetryableEvents(limit?: number): Promise<Array<{
    receipt: YoloLabelReceipt
    event: YoloLabelEvent
  }>> {
    const results: Array<{ receipt: YoloLabelReceipt; event: YoloLabelEvent }> = []
    await mkdir(this.rootDir, { recursive: true })
    const entries = await readdir(this.rootDir, { withFileTypes: true })
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      if (!entry.isFile() || !entry.name.endsWith('.json')) continue
      const receipt = await this.readReceiptPath(entry.name)
      for (const event of receipt.events) {
        if (event.memory_sync.state !== 'pending' && event.memory_sync.state !== 'failed') continue
        results.push({ receipt, event })
        if (limit != null && results.length >= limit) return results
      }
    }
    return results
  }

  private async withLock<T>(assetUid: string, rowIndex: number, work: () => Promise<T>): Promise<T> {
    const key = `${assetUid}\0${rowIndex}`
    const previous = this.locks.get(key) ?? Promise.resolve()
    let release!: () => void
    const current = new Promise<void>((resolve) => {
      release = resolve
    })
    const lock = previous.then(() => current, () => current)
    this.locks.set(key, lock)
    await previous.catch(() => undefined)
    try {
      return await work()
    } finally {
      release()
      if (this.locks.get(key) === lock) this.locks.delete(key)
    }
  }

  private receiptRelativePath(assetUid: string, rowIndex: number): string {
    return labelFileName(assetUid, rowIndex)
  }

  private receiptAbsolutePath(relativePath: string): string {
    return path.join(this.rootDir, validateRelativeReceiptPath(relativePath))
  }

  private emptyReceipt(assetUid: string, rowIndex: number): YoloLabelReceipt {
    return {
      schema: 'watch.yolo_track_labels.v1',
      receipt_format_version: 2,
      revision: 0,
      asset_uid: assetUid,
      row_index: rowIndex,
      timecode: null,
      movie_segment: null,
      labels: {},
      box_rejections: {},
      events: [],
      receipt_path: this.receiptRelativePath(assetUid, rowIndex),
      updated_at: null,
    }
  }

  private async readUnlocked(assetUid: string, rowIndex: number): Promise<YoloLabelReceipt> {
    const relativePath = this.receiptRelativePath(assetUid, rowIndex)
    try {
      return await this.readReceiptPath(relativePath, assetUid, rowIndex)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }

    const legacyRelativePath = legacyLabelFileName(assetUid, rowIndex)
    if (legacyRelativePath !== relativePath) {
      try {
        return await this.readReceiptPath(legacyRelativePath, assetUid, rowIndex)
      } catch (error) {
        if (
          error instanceof MalformedYoloReceiptError
          && error.message.includes('asset_uid or row_index does not match receipt path')
        ) {
          const legacyReceipt = await this.readReceiptPath(legacyRelativePath)
          if (legacyReceipt.asset_uid === assetUid) throw error
          return this.emptyReceipt(assetUid, rowIndex)
        }
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
    }
    return this.emptyReceipt(assetUid, rowIndex)
  }

  private async readReceiptPath(relativePath: string, expectedAssetUid?: string, expectedRowIndex?: number): Promise<YoloLabelReceipt> {
    const absolutePath = this.receiptAbsolutePath(relativePath)
    let raw: string
    try {
      raw = await readFile(absolutePath, 'utf-8')
    } catch (error) {
      throw error
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch (error) {
      throw new MalformedYoloReceiptError(`malformed YOLO receipt JSON: ${String(error)}`, relativePath)
    }
    if (!parsed || typeof parsed !== 'object') {
      throw new MalformedYoloReceiptError('malformed YOLO receipt: root must be an object', relativePath)
    }
    const migrated = this.migrateReceipt(parsed as Record<string, unknown>, relativePath, expectedAssetUid, expectedRowIndex)
    if (
      (expectedAssetUid && migrated.asset_uid !== expectedAssetUid)
      || (expectedRowIndex != null && migrated.row_index !== expectedRowIndex)
    ) {
      throw new MalformedYoloReceiptError('malformed YOLO receipt: asset_uid or row_index does not match receipt path', relativePath)
    }
    return migrated
  }

  private migrateReceipt(
    receipt: Record<string, unknown>,
    relativePath: string,
    expectedAssetUid?: string,
    expectedRowIndex?: number,
  ): YoloLabelReceipt {
    if (receipt.schema !== 'watch.yolo_track_labels.v1') {
      throw new MalformedYoloReceiptError('malformed YOLO receipt: unexpected schema', relativePath)
    }
    const assetUid = typeof receipt.asset_uid === 'string' ? receipt.asset_uid : expectedAssetUid
    const rowIndex = Number.isFinite(Number(receipt.row_index)) ? Number(receipt.row_index) : expectedRowIndex
    if (!assetUid || !Number.isFinite(rowIndex)) {
      throw new MalformedYoloReceiptError('malformed YOLO receipt: missing asset_uid or row_index', relativePath)
    }
    const normalizedRowIndex = rowIndex as number
    const now = new Date().toISOString()
    const events = Array.isArray(receipt.events) ? receipt.events : []
    const migratedEvents = events.map((rawEvent, index): YoloLabelEvent => {
      const event = rawEvent && typeof rawEvent === 'object' ? rawEvent as Record<string, unknown> : {}
      const legacyId = typeof event.id === 'string' ? event.id : `legacy_event_${index + 1}`
      const action = typeof event.action === 'string' ? event.action as YoloLabelAction : 'reset'
      const idempotencyKey = typeof event.idempotency_key === 'string'
        ? event.idempotency_key
        : `legacy:${legacyId}`
      const canonicalId = eventIdFor(assetUid, normalizedRowIndex, idempotencyKey)
      const memorySync = event.memory_sync && typeof event.memory_sync === 'object'
        ? event.memory_sync as Record<string, unknown>
        : null
      const migratedMemoryState = typeof memorySync?.state === 'string'
        ? memorySync.state as MemorySyncState
        : 'legacy_unverified'
      const memoryKeyChanged = legacyId !== canonicalId
      const memorySyncState = migratedMemoryState === 'stored' && memoryKeyChanged
        ? 'pending'
        : migratedMemoryState
      const memorySyncLastError = migratedMemoryState === 'stored' && memoryKeyChanged
        ? `memory_key_changed_during_event_id_migration:${legacyId}`
        : typeof memorySync?.last_error === 'string'
          ? memorySync.last_error
          : null
      return {
        id: canonicalId,
        sequence: Number.isFinite(Number(event.sequence)) ? Number(event.sequence) : index + 1,
        idempotency_key: idempotencyKey,
        request_fingerprint: typeof event.request_fingerprint === 'string' ? event.request_fingerprint : undefined,
        action,
        asset_uid: typeof event.asset_uid === 'string' ? event.asset_uid : assetUid,
        row_index: Number.isFinite(Number(event.row_index)) ? Number(event.row_index) : normalizedRowIndex,
        track_id: typeof event.track_id === 'string' ? event.track_id : '',
        box_key: typeof event.box_key === 'string' ? event.box_key : '',
        time_seconds: typeof event.time_seconds === 'number' && Number.isFinite(event.time_seconds) ? event.time_seconds : null,
        timecode: typeof event.timecode === 'string' ? event.timecode : null,
        movie_segment: typeof event.movie_segment === 'string' ? event.movie_segment : null,
        created_at: typeof event.created_at === 'string' ? event.created_at : now,
        status: typeof event.status === 'string' ? event.status : statusForAction(action),
        character_name: typeof event.character_name === 'string' ? event.character_name : undefined,
        actor_name: typeof event.actor_name === 'string' ? event.actor_name : undefined,
        confidence: typeof event.confidence === 'number' ? event.confidence : undefined,
        memory_sync: {
          state: memorySyncState,
          attempts: Number.isFinite(Number(memorySync?.attempts)) ? Number(memorySync?.attempts) : 0,
          last_error: memorySyncLastError,
          updated_at: typeof memorySync?.updated_at === 'string' ? memorySync.updated_at : now,
        },
      }
    })

    const rawReceiptPath = typeof receipt.receipt_path === 'string'
      ? receipt.receipt_path
      : this.receiptRelativePath(assetUid, normalizedRowIndex)
    const nextRelativePath = rawReceiptPath.startsWith('/')
      ? this.receiptRelativePath(assetUid, normalizedRowIndex)
      : validateRelativeReceiptPath(rawReceiptPath)

    return {
      schema: 'watch.yolo_track_labels.v1',
      receipt_format_version: 2,
      revision: Number.isFinite(Number(receipt.revision)) ? Number(receipt.revision) : 0,
      asset_uid: assetUid,
      row_index: normalizedRowIndex,
      timecode: typeof receipt.timecode === 'string' ? receipt.timecode : null,
      movie_segment: typeof receipt.movie_segment === 'string' ? receipt.movie_segment : null,
      labels: receipt.labels && typeof receipt.labels === 'object' ? { ...receipt.labels as Record<string, unknown> } : {},
      box_rejections: receipt.box_rejections && typeof receipt.box_rejections === 'object' ? { ...receipt.box_rejections as Record<string, unknown> } : {},
      events: migratedEvents,
      receipt_path: nextRelativePath,
      updated_at: typeof receipt.updated_at === 'string' ? receipt.updated_at : null,
    }
  }

  private async persist(receipt: YoloLabelReceipt): Promise<void> {
    if (hasOwn(receipt as unknown as Record<string, unknown>, 'memory_sync')) {
      delete (receipt as unknown as Record<string, unknown>).memory_sync
    }
    await atomicWriteJson(this.receiptAbsolutePath(receipt.receipt_path), receipt)
  }
}

export function eventMemoryDocumentKey(eventId: string): string {
  return sha256(eventId)
}
