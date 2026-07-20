import type {
  MemorySyncState,
  YoloLabelEvent,
  YoloLabelReceipt,
  YoloReceiptStore,
} from './yoloReceiptStore'
import { eventMemoryDocumentKey } from './yoloReceiptStore'

const inFlightRetryEventIds = new Set<string>()

export async function withYoloMemorySyncClaim<T>(
  eventId: string,
  work: () => Promise<T>,
  busyValue: T,
): Promise<T> {
  if (inFlightRetryEventIds.has(eventId)) return busyValue
  inFlightRetryEventIds.add(eventId)
  try {
    return await work()
  } finally {
    inFlightRetryEventIds.delete(eventId)
  }
}

export async function deliverYoloEventToMemory(input: {
  memoryDaemonUrl: string
  receipt: YoloLabelReceipt
  event: YoloLabelEvent
}): Promise<{
  ok: boolean
  error: string | null
}> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8_000)
  try {
    const label = input.event.action === 'accept'
      ? {
          trackId: input.event.track_id,
          characterName: input.event.character_name,
          actorName: input.event.actor_name || '',
          status: 'accepted',
          source: 'human',
          confidence: typeof input.event.confidence === 'number' ? input.event.confidence : 1,
          updatedAt: input.event.created_at,
        }
      : null
    const boxRejection = input.event.action === 'reject_box' || input.event.action === 'reset_box'
      ? {
          boxKey: input.event.box_key,
          trackId: input.event.track_id,
          timeSeconds: input.event.time_seconds,
          status: input.event.action === 'reset_box' ? 'reset_box' : 'rejected',
          source: 'human',
          updatedAt: input.event.created_at,
        }
      : null
    const retrievalText = boxRejection
      ? `Watch YOLO person box ${input.event.track_id} for ${input.receipt.asset_uid} row ${input.receipt.row_index} stopped at ${input.event.time_seconds}s; identity must not propagate across this stop.`
      : label
        ? `Watch YOLO person box ${input.event.track_id} for ${input.receipt.asset_uid} row ${input.receipt.row_index} accepted as ${label.characterName}.`
        : `Watch YOLO person box ${input.event.track_id} for ${input.receipt.asset_uid} row ${input.receipt.row_index} reset to unassigned YOLO track state.`
    const response = await fetch(`${input.memoryDaemonUrl}/store`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Caller-Skill': 'watch',
      },
      signal: controller.signal,
      body: JSON.stringify({
        collection: 'watch_yolo_track_labels',
        document: {
          _key: eventMemoryDocumentKey(input.event.id),
          kind: 'watch_yolo_track_label_event',
          schema: 'watch.yolo_track_label_event.v1',
          asset_uid: input.receipt.asset_uid,
          row_index: input.receipt.row_index,
          track_id: input.event.track_id,
          action: input.event.action,
          event_id: input.event.id,
          event: input.event,
          label,
          box_rejection: boxRejection,
          receipt_path: input.receipt.receipt_path,
          retrieval_text: retrievalText,
          updated_at: new Date().toISOString(),
        },
      }),
    })
    if (!response.ok) return { ok: false, error: `memory_store_http_${response.status}` }
    const data = await response.json().catch(() => null) as { ok?: boolean; stored?: boolean; status?: string } | null
    if (data?.ok !== true && data?.stored !== true && data?.status !== 'stored') {
      return { ok: false, error: 'memory_store_not_ok' }
    }
    return { ok: true, error: null }
  } catch (error) {
    return { ok: false, error: String(error) }
  } finally {
    clearTimeout(timeout)
  }
}

export async function syncYoloEventToMemory(input: {
  memoryDaemonUrl: string
  receipt: YoloLabelReceipt
  event: YoloLabelEvent
}): Promise<{
  ok: boolean
  error: string | null
}> {
  return withYoloMemorySyncClaim(
    input.event.id,
    () => deliverYoloEventToMemory(input),
    { ok: false, error: 'memory_sync_in_flight' },
  )
}

export async function retryYoloMemorySync(input: {
  store: YoloReceiptStore
  memoryDaemonUrl: string
  assetUid?: string
  rowIndex?: number
  eventId?: string
}): Promise<{
  attempted: number
  stored: number
  failed: number
  results: Array<{
    event_id: string
    state: MemorySyncState
    error: string | null
  }>
}> {
  const hasAssetScope = typeof input.assetUid === 'string' && input.assetUid.length > 0
  const hasRowScope = Number.isFinite(input.rowIndex)
  const candidates = hasAssetScope && hasRowScope
    ? (await input.store.read(input.assetUid as string, input.rowIndex as number)).events
      .map((event) => ({ receipt: null as YoloLabelReceipt | null, event }))
    : (await input.store.listRetryableEvents())
      .filter(({ receipt }) => !hasAssetScope || receipt.asset_uid === input.assetUid)
      .filter(({ receipt }) => !hasRowScope || receipt.row_index === input.rowIndex)

  let attempted = 0
  let stored = 0
  let failed = 0
  const results: Array<{ event_id: string; state: MemorySyncState; error: string | null }> = []

  for (const candidate of candidates) {
    let receipt = candidate.receipt
    let event = candidate.event
    if (input.eventId && event.id !== input.eventId) continue
    const claimed = await withYoloMemorySyncClaim(event.id, async () => {
      receipt = receipt
        ? await input.store.read(receipt.asset_uid, receipt.row_index)
        : await input.store.read(input.assetUid as string, input.rowIndex as number)
      event = receipt.events.find((item) => item.id === event.id) ?? event
      if (event.memory_sync.state !== 'pending' && event.memory_sync.state !== 'failed') return false
      attempted += 1
      const result = await deliverYoloEventToMemory({
        memoryDaemonUrl: input.memoryDaemonUrl,
        receipt,
        event,
      })
      const nextState: MemorySyncState = result.ok ? 'stored' : 'failed'
      await input.store.updateMemorySync(receipt.asset_uid, receipt.row_index, event.id, {
        state: nextState,
        lastError: result.error,
      })
      if (result.ok) stored += 1
      else failed += 1
      results.push({ event_id: event.id, state: nextState, error: result.error })
      return true
    }, false)
    if (!claimed) continue
  }

  return { attempted, stored, failed, results }
}
