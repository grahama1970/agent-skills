import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer as createHttpServer, type IncomingMessage } from 'node:http'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

import { yoloLabelForOverlay } from '../components/WatchReportView'
import { retryYoloMemorySync, syncYoloEventToMemory } from '../server/yoloMemorySync'
import { eventMemoryDocumentKey, YoloReceiptStore } from '../server/yoloReceiptStore'
import { projectYoloTrackLabelAtTime } from '../src/yoloLabelProjection'

type YoloReceipt = {
  schema: string
  receipt_format_version: number
  revision: number
  asset_uid: string
  row_index: number
  labels: Record<string, { characterName?: string; actorName?: string; confidence?: number }>
  box_rejections: Record<string, unknown>
  events: Array<{
    id: string
    sequence: number
    idempotency_key: string
    action: string
    status: string
    track_id: string
    box_key: string
    time_seconds: number | null
    character_name?: string
    actor_name?: string
    memory_sync: {
      state: string
      attempts: number
      last_error: string | null
    }
  }>
  receipt_path: string
  memory_sync?: string
  memory_sync_error?: string
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const assetUid = 'watch_row10_yolo_receipt_fixture'
const rowIndex = 10
const trackId = 'track_15'
const stopBoxKey = 'track_15@179'

async function unusedLocalPort(): Promise<number> {
  const reservation = createServer()
  await new Promise<void>((resolve, reject) => {
    reservation.once('error', reject)
    reservation.listen(0, '127.0.0.1', resolve)
  })
  const address = reservation.address() as AddressInfo | null
  assert.ok(address && Number.isInteger(address.port), 'failed to reserve a local test port')
  await new Promise<void>((resolve, reject) => {
    reservation.close((error) => error ? reject(error) : resolve())
  })
  return address.port
}

async function readRequestJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  let body = ''
  for await (const chunk of req) {
    body += chunk
  }
  return JSON.parse(body) as Record<string, unknown>
}

async function withMemoryCapture(
  work: (baseUrl: string, captured: Array<Record<string, unknown>>) => Promise<void>,
  responseBody: Record<string, unknown> = { ok: true },
): Promise<void> {
  const captured: Array<Record<string, unknown>> = []
  const server = createHttpServer(async (req, res) => {
    if (req.method !== 'POST' || req.url !== '/store') {
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: false }))
      return
    }
    captured.push(await readRequestJson(req))
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(responseBody))
  })
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address() as AddressInfo | null
  assert.ok(address && Number.isInteger(address.port), 'failed to start memory capture server')
  try {
    await work(`http://127.0.0.1:${address.port}`, captured)
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve())
    })
  }
}

async function requestJson(
  baseUrl: string,
  method: 'GET' | 'POST',
  route: string,
  body?: Record<string, unknown>,
  idempotencyKey?: string,
): Promise<YoloReceipt> {
  const response = await fetch(`${baseUrl}${route}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await response.text()
  assert.equal(response.status, 200, `${method} ${route} returned ${response.status}: ${text}`)
  return JSON.parse(text) as YoloReceipt
}

async function postJsonStatus(
  baseUrl: string,
  route: string,
  body: Record<string, unknown>,
  idempotencyKey: string,
): Promise<{ status: number; json: Record<string, unknown> }> {
  const response = await fetch(`${baseUrl}${route}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(body),
  })
  const text = await response.text()
  return {
    status: response.status,
    json: JSON.parse(text) as Record<string, unknown>,
  }
}

async function requestProjection(baseUrl: string, seconds: number): Promise<unknown> {
  const params = new URLSearchParams({
    asset_uid: assetUid,
    row_index: String(rowIndex),
    track_id: trackId,
    time_seconds: String(seconds),
  })
  const response = await fetch(`${baseUrl}/api/projects/watch/yolo-labels/projected?${params}`)
  const text = await response.text()
  assert.equal(response.status, 200, text)
  return JSON.parse(text)
}

async function waitForApi(baseUrl: string, child: ChildProcess, diagnostics: () => string): Promise<void> {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Watch API exited before readiness\n${diagnostics()}`)
    try {
      const response = await fetch(`${baseUrl}/api/projects/watch/health`)
      if (response.ok) return
    } catch {
      // server has not bound yet
    }
    await delay(50)
  }
  throw new Error(`Watch API did not become ready\n${diagnostics()}`)
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null) return
  const gracefulClose = once(child, 'close')
  child.kill('SIGTERM')
  await Promise.race([gracefulClose, delay(2_000)])
  if (child.exitCode === null) {
    const forcedClose = once(child, 'close')
    child.kill('SIGKILL')
    await forcedClose
  }
}

async function startServer(receiptDir: string, apiPort: number, unavailableMemoryPort: number) {
  let stdout = ''
  let stderr = ''
  const tsxCommand = path.join(
    uiRoot,
    'node_modules',
    '.bin',
    process.platform === 'win32' ? 'tsx.cmd' : 'tsx',
  )
  const child = spawn(tsxCommand, ['server/index.ts'], {
    cwd: uiRoot,
    env: {
      ...process.env,
      WATCH_API_PORT: String(apiPort),
      WATCH_YOLO_LABEL_DIR: receiptDir,
      MEMORY_DAEMON_URL: `http://127.0.0.1:${unavailableMemoryPort}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  child.stdout?.setEncoding('utf-8')
  child.stderr?.setEncoding('utf-8')
  child.stdout?.on('data', (chunk: string) => {
    stdout = `${stdout}${chunk}`.slice(-8_000)
  })
  child.stderr?.on('data', (chunk: string) => {
    stderr = `${stderr}${chunk}`.slice(-8_000)
  })
  const baseUrl = `http://127.0.0.1:${apiPort}`
  await waitForApi(baseUrl, child, () => `${stdout}\n${stderr}`)
  return { child, baseUrl }
}

async function main(): Promise<void> {
  await withMemoryCapture(async (memoryDaemonUrl, captured) => {
    const acceptEvent = {
      id: 'accept-event-with-later-stop',
      sequence: 1,
      idempotency_key: 'accept-event-with-later-stop-key',
      action: 'accept' as const,
      asset_uid: assetUid,
      row_index: rowIndex,
      track_id: trackId,
      box_key: 'track_15@100',
      time_seconds: 1,
      timecode: '04:00',
      movie_segment: '04:00-04:24',
      created_at: '2026-01-01T00:00:00.000Z',
      status: 'accepted',
      character_name: 'Marcus',
      actor_name: 'Tony Cox',
      confidence: 1,
      memory_sync: {
        state: 'failed' as const,
        attempts: 1,
        last_error: 'previous_failure',
        updated_at: '2026-01-01T00:00:00.000Z',
      },
    }
    const result = await syncYoloEventToMemory({
      memoryDaemonUrl,
      receipt: {
        schema: 'watch.yolo_track_labels.v1',
        receipt_format_version: 2,
        revision: 3,
        asset_uid: assetUid,
        row_index: rowIndex,
        timecode: '04:00',
        movie_segment: '04:00-04:24',
        labels: {},
        box_rejections: {
          'track_15@100': {
            boxKey: 'track_15@100',
            trackId,
            timeSeconds: 1.79,
            status: 'rejected',
            source: 'human',
            updatedAt: '2026-01-01T00:00:01.000Z',
          },
        },
        events: [acceptEvent],
        receipt_path: 'watch_row10_yolo_receipt_fixture_row0010.json',
        updated_at: '2026-01-01T00:00:01.000Z',
      },
      event: acceptEvent,
    })
    assert.deepEqual(result, { ok: true, error: null })
    assert.equal(captured.length, 1)
    const document = captured[0].document as Record<string, unknown>
    assert.equal(captured[0].collection, 'watch_yolo_track_labels')
    assert.equal((document.label as Record<string, unknown>).characterName, 'Marcus')
    assert.equal(document.box_rejection, null)
    assert.match(String(document.retrieval_text), /accepted as Marcus/)
    assert.doesNotMatch(String(document.retrieval_text), /stopped/)
  })

  await withMemoryCapture(async (memoryDaemonUrl) => {
    const result = await syncYoloEventToMemory({
      memoryDaemonUrl,
      receipt: {
        schema: 'watch.yolo_track_labels.v1',
        receipt_format_version: 2,
        revision: 1,
        asset_uid: assetUid,
        row_index: rowIndex,
        timecode: '04:00',
        movie_segment: '04:00-04:24',
        labels: {},
        box_rejections: {},
        events: [],
        receipt_path: 'watch_row10_yolo_receipt_fixture_row0010.json',
        updated_at: '2026-01-01T00:00:00.000Z',
      },
      event: {
        id: 'strict-ok-event',
        sequence: 1,
        idempotency_key: 'strict-ok-event-key',
        action: 'accept',
        asset_uid: assetUid,
        row_index: rowIndex,
        track_id: trackId,
        box_key: 'track_15@100',
        time_seconds: 1,
        timecode: '04:00',
        movie_segment: '04:00-04:24',
        created_at: '2026-01-01T00:00:00.000Z',
        status: 'accepted',
        character_name: 'Marcus',
        actor_name: 'Tony Cox',
        confidence: 1,
        memory_sync: {
          state: 'pending',
          attempts: 0,
          last_error: null,
          updated_at: '2026-01-01T00:00:00.000Z',
        },
      },
    })
    assert.deepEqual(result, { ok: false, error: 'memory_store_not_ok' })
  }, { ok: 'true' })

  assert.equal(
    projectYoloTrackLabelAtTime({
      trackId: 'legacy_track',
      timeSeconds: 2,
      events: [{ action: 'accept', track_id: 'legacy_track', time_seconds: null, character_name: 'Wrong' }],
      labels: { legacy_track: { characterName: 'Legacy Label' } },
    })?.characterName,
    'Legacy Label',
  )
  assert.equal(
    projectYoloTrackLabelAtTime({
      trackId: 'legacy_track',
      timeSeconds: 4,
      events: [
        { sequence: 1, action: 'accept', track_id: 'legacy_track', time_seconds: 5, character_name: 'Future' },
        { sequence: 2, action: 'accept', track_id: 'legacy_track', time_seconds: 1, character_name: 'Earlier' },
      ],
      labels: {},
    })?.characterName,
    'Earlier',
  )
  assert.equal(
    projectYoloTrackLabelAtTime({
      trackId: 'legacy_track',
      timeSeconds: 5,
      events: [
        { sequence: 1, action: 'accept', track_id: 'legacy_track', time_seconds: 5, character_name: 'Future' },
        { sequence: 2, action: 'accept', track_id: 'legacy_track', time_seconds: 1, character_name: 'Earlier' },
      ],
      labels: {},
    })?.characterName,
    'Future',
  )

  const receiptDir = await mkdtemp(path.join(tmpdir(), 'watch-yolo-label-receipt-'))
  const apiPort = await unusedLocalPort()
  const unavailableMemoryPort = await unusedLocalPort()
  const receiptRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(assetUid)}&row_index=${rowIndex}`
  let child: ChildProcess | null = null

  try {
    const monotonicStore = new YoloReceiptStore(receiptDir)
    const monotonicMutation = await monotonicStore.applyMutation({
      idempotencyKey: 'stored-monotonic-accept',
      action: 'accept',
      assetUid: 'watch_stored_monotonic_fixture',
      rowIndex: 31,
      trackId: 'track_stored',
      boxKey: 'track_stored@100',
      timeSeconds: 1,
      timecode: '00:01',
      movieSegment: '00:00-00:02',
      characterName: 'Stored Identity',
      actorName: '',
      confidence: 1,
    })
    const storedReceipt = await monotonicStore.updateMemorySync(
      'watch_stored_monotonic_fixture',
      31,
      monotonicMutation.event.id,
      { state: 'stored', lastError: null },
    )
    const afterFailedDowngrade = await monotonicStore.updateMemorySync(
      'watch_stored_monotonic_fixture',
      31,
      monotonicMutation.event.id,
      { state: 'failed', lastError: 'late_failure' },
    )
    assert.equal(afterFailedDowngrade.events[0].memory_sync.state, 'stored')
    assert.equal(afterFailedDowngrade.events[0].memory_sync.last_error, null)
    assert.equal(afterFailedDowngrade.revision, storedReceipt.revision)

    for (const legacyAssetUid of ['legacy_same_id_a', 'legacy_same_id_b']) {
      await writeFile(path.join(receiptDir, `${legacyAssetUid}_row0032.json`), `${JSON.stringify({
        schema: 'watch.yolo_track_labels.v1',
        revision: 1,
        asset_uid: legacyAssetUid,
        row_index: 32,
        labels: {},
        box_rejections: {},
        events: [
          {
            id: 'duplicate_legacy_id',
            sequence: 1,
            action: 'accept',
            status: 'accepted',
            track_id: 'track_legacy',
            box_key: 'track_legacy@100',
            time_seconds: 1,
            character_name: 'Legacy Identity',
            created_at: '2026-01-01T00:00:00.000Z',
          },
        ],
        receipt_path: `${legacyAssetUid}_row0032.json`,
        updated_at: '2026-01-01T00:00:00.000Z',
      }, null, 2)}\n`, 'utf-8')
    }
    const sameLegacyIdA = await monotonicStore.read('legacy_same_id_a', 32)
    const sameLegacyIdB = await monotonicStore.read('legacy_same_id_b', 32)
    assert.equal(sameLegacyIdA.events[0].idempotency_key, 'legacy:duplicate_legacy_id')
    assert.equal(sameLegacyIdB.events[0].idempotency_key, 'legacy:duplicate_legacy_id')
    assert.notEqual(sameLegacyIdA.events[0].id, sameLegacyIdB.events[0].id)

    const storedOldIdAssetUid = 'legacy_stored_old_event_id'
    const storedOldIdRowIndex = 33
    await writeFile(path.join(receiptDir, `${storedOldIdAssetUid}_row0033.json`), `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      receipt_format_version: 2,
      revision: 1,
      asset_uid: storedOldIdAssetUid,
      row_index: storedOldIdRowIndex,
      labels: {},
      box_rejections: {},
      events: [
        {
          id: 'pre_fix_unscoped_event_id',
          sequence: 1,
          idempotency_key: 'stored-before-canonical-event-id',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@100',
          time_seconds: 1,
          character_name: 'Canonical Retry',
          created_at: '2026-01-01T00:00:00.000Z',
          memory_sync: {
            state: 'stored',
            attempts: 1,
            last_error: null,
            updated_at: '2026-01-01T00:00:01.000Z',
          },
        },
      ],
      receipt_path: `${storedOldIdAssetUid}_row0033.json`,
      updated_at: '2026-01-01T00:00:01.000Z',
    }, null, 2)}\n`, 'utf-8')
    const migratedStoredOldId = await monotonicStore.read(storedOldIdAssetUid, storedOldIdRowIndex)
    const migratedStoredEvent = migratedStoredOldId.events[0]
    assert.notEqual(migratedStoredEvent.id, 'pre_fix_unscoped_event_id')
    assert.equal(migratedStoredEvent.memory_sync.state, 'pending')
    assert.match(migratedStoredEvent.memory_sync.last_error ?? '', /memory_key_changed_during_event_id_migration/)
    await withMemoryCapture(async (memoryDaemonUrl, captured) => {
      const retry = await retryYoloMemorySync({
        store: monotonicStore,
        memoryDaemonUrl,
        assetUid: storedOldIdAssetUid,
        rowIndex: storedOldIdRowIndex,
      })
      assert.equal(retry.attempted, 1)
      assert.equal(retry.stored, 1)
      assert.equal(retry.failed, 0)
      assert.equal(captured.length, 1)
      const document = captured[0].document as Record<string, unknown>
      assert.equal(document.event_id, migratedStoredEvent.id)
      assert.equal(document._key, eventMemoryDocumentKey(migratedStoredEvent.id))
      const afterRetry = await monotonicStore.read(storedOldIdAssetUid, storedOldIdRowIndex)
      assert.equal(afterRetry.events[0].id, migratedStoredEvent.id)
      assert.equal(afterRetry.events[0].memory_sync.state, 'stored')
    })

    const started = await startServer(receiptDir, apiPort, unavailableMemoryPort)
    child = started.child
    const baseUrl = started.baseUrl
    const common = {
      asset_uid: assetUid,
      row_index: rowIndex,
      track_id: trackId,
      timecode: '04:00',
      movie_segment: '04:00-04:24',
    }

    const legacyAssetUid = 'watch_legacy_null_backdate_fixture'
    const legacyRowIndex = 11
    const legacyReceiptPath = path.join(receiptDir, `${legacyAssetUid}_row0011.json`)
    await writeFile(legacyReceiptPath, `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      revision: 2,
      asset_uid: legacyAssetUid,
      row_index: legacyRowIndex,
      labels: {},
      box_rejections: {},
      events: [
        {
          id: 'legacy_timed_5',
          sequence: 1,
          idempotency_key: 'legacy:timed-5',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@500',
          time_seconds: 5,
          character_name: 'Future Identity',
          created_at: '2026-01-01T00:00:00.000Z',
        },
        {
          id: 'legacy_null_later',
          sequence: 2,
          idempotency_key: 'legacy:null-later',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@unknown',
          time_seconds: null,
          character_name: 'Null Legacy Identity',
          created_at: '2026-01-01T00:00:01.000Z',
        },
      ],
      receipt_path: `${legacyAssetUid}_row0011.json`,
      updated_at: '2026-01-01T00:00:01.000Z',
    }, null, 2)}\n`, 'utf-8')

    const backdated = await postJsonStatus(baseUrl, '/api/projects/watch/yolo-labels', {
      asset_uid: legacyAssetUid,
      row_index: legacyRowIndex,
      track_id: 'track_legacy',
      action: 'accept',
      time_seconds: 4,
      box_key: 'track_legacy@400',
      character_name: 'Backdated Identity',
      actor_name: '',
      confidence: 1,
    }, 'backdated-before-timed-event')
    assert.equal(backdated.status, 409)
    assert.equal(backdated.json.code, 'OUT_OF_ORDER_TRACK_EVENT')
    const legacyRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(legacyAssetUid)}&row_index=${legacyRowIndex}`
    const legacyAfterBackdate = await requestJson(baseUrl, 'GET', legacyRoute)
    assert.deepEqual(legacyAfterBackdate.events.map((event) => event.idempotency_key), ['legacy:timed-5', 'legacy:null-later'])
    assert.equal(legacyAfterBackdate.events.every((event) => event.id.startsWith('yolo_label_')), true)

    const legacyIdempotencyAssetUid = 'watch_legacy_idempotency_fixture'
    const legacyIdempotencyRowIndex = 12
    const legacyIdempotencyReceiptPath = path.join(receiptDir, `${legacyIdempotencyAssetUid}_row0012.json`)
    await writeFile(legacyIdempotencyReceiptPath, `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      revision: 1,
      asset_uid: legacyIdempotencyAssetUid,
      row_index: legacyIdempotencyRowIndex,
      labels: {},
      box_rejections: {},
      events: [
        {
          id: 'legacy_no_fingerprint',
          sequence: 1,
          idempotency_key: 'legacy:legacy_no_fingerprint',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@100',
          time_seconds: 1,
          character_name: 'Original Identity',
          created_at: '2026-01-01T00:00:00.000Z',
        },
      ],
      receipt_path: `${legacyIdempotencyAssetUid}_row0012.json`,
      updated_at: '2026-01-01T00:00:00.000Z',
    }, null, 2)}\n`, 'utf-8')
    const legacyConflict = await postJsonStatus(baseUrl, '/api/projects/watch/yolo-labels', {
      asset_uid: legacyIdempotencyAssetUid,
      row_index: legacyIdempotencyRowIndex,
      track_id: 'track_legacy',
      action: 'accept',
      time_seconds: 2,
      box_key: 'track_legacy@200',
      character_name: 'Different Identity',
      actor_name: '',
      confidence: 1,
    }, 'legacy:legacy_no_fingerprint')
    assert.equal(legacyConflict.status, 409)
    assert.equal(legacyConflict.json.code, 'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD')
    const legacyConflictRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(legacyIdempotencyAssetUid)}&row_index=${legacyIdempotencyRowIndex}`
    const legacyAfterConflict = await requestJson(baseUrl, 'GET', legacyConflictRoute)
    assert.deepEqual(legacyAfterConflict.events.map((event) => event.idempotency_key), ['legacy:legacy_no_fingerprint'])
    assert.equal(legacyAfterConflict.events[0].id.startsWith('yolo_label_'), true)

    const legacyMaxTimeAssetUid = 'watch_legacy_max_time_fixture'
    const legacyMaxTimeRowIndex = 13
    const legacyMaxTimeReceiptPath = path.join(receiptDir, `${legacyMaxTimeAssetUid}_row0013.json`)
    await writeFile(legacyMaxTimeReceiptPath, `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      revision: 2,
      asset_uid: legacyMaxTimeAssetUid,
      row_index: legacyMaxTimeRowIndex,
      labels: {},
      box_rejections: {},
      events: [
        {
          id: 'legacy_time_5_sequence_1',
          sequence: 1,
          idempotency_key: 'legacy:time-5-sequence-1',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@500',
          time_seconds: 5,
          character_name: 'Future Identity',
          created_at: '2026-01-01T00:00:00.000Z',
        },
        {
          id: 'legacy_time_1_sequence_2',
          sequence: 2,
          idempotency_key: 'legacy:time-1-sequence-2',
          action: 'accept',
          status: 'accepted',
          track_id: 'track_legacy',
          box_key: 'track_legacy@100',
          time_seconds: 1,
          character_name: 'Earlier Identity',
          created_at: '2026-01-01T00:00:01.000Z',
        },
      ],
      receipt_path: `${legacyMaxTimeAssetUid}_row0013.json`,
      updated_at: '2026-01-01T00:00:01.000Z',
    }, null, 2)}\n`, 'utf-8')
    const maxTimeBackdated = await postJsonStatus(baseUrl, '/api/projects/watch/yolo-labels', {
      asset_uid: legacyMaxTimeAssetUid,
      row_index: legacyMaxTimeRowIndex,
      track_id: 'track_legacy',
      action: 'accept',
      time_seconds: 4,
      box_key: 'track_legacy@400',
      character_name: 'Backdated Identity',
      actor_name: '',
      confidence: 1,
    }, 'backdated-before-max-timed-event')
    assert.equal(maxTimeBackdated.status, 409)
    assert.equal(maxTimeBackdated.json.code, 'OUT_OF_ORDER_TRACK_EVENT')
    const legacyMaxTimeRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(legacyMaxTimeAssetUid)}&row_index=${legacyMaxTimeRowIndex}`
    const legacyAfterMaxTimeBackdate = await requestJson(baseUrl, 'GET', legacyMaxTimeRoute)
    assert.deepEqual(legacyAfterMaxTimeBackdate.events.map((event) => event.idempotency_key), ['legacy:time-5-sequence-1', 'legacy:time-1-sequence-2'])
    assert.equal(legacyAfterMaxTimeBackdate.events.every((event) => event.id.startsWith('yolo_label_')), true)

    const collisionRowIndex = 14
    const collisionA = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      asset_uid: 'asset/a',
      row_index: collisionRowIndex,
      track_id: 'track_collision',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_collision@100',
      character_name: 'Slash Asset',
      actor_name: '',
      confidence: 1,
    }, 'collision-a-accept')
    const collisionB = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      asset_uid: 'asset?a',
      row_index: collisionRowIndex,
      track_id: 'track_collision',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_collision@100',
      character_name: 'Question Asset',
      actor_name: '',
      confidence: 1,
    }, 'collision-b-accept')
    assert.notEqual(collisionA.receipt_path, collisionB.receipt_path)
    const collisionARoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent('asset/a')}&row_index=${collisionRowIndex}`
    const collisionBRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent('asset?a')}&row_index=${collisionRowIndex}`
    const collisionARead = await requestJson(baseUrl, 'GET', collisionARoute)
    const collisionBRead = await requestJson(baseUrl, 'GET', collisionBRoute)
    assert.equal(collisionARead.labels.track_collision?.characterName, 'Slash Asset')
    assert.equal(collisionBRead.labels.track_collision?.characterName, 'Question Asset')

    const legacyCollisionRowIndex = 15
    await writeFile(path.join(receiptDir, 'asset_a_row0015.json'), `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      revision: 1,
      asset_uid: 'asset/a',
      row_index: legacyCollisionRowIndex,
      labels: {
        track_collision: {
          trackId: 'track_collision',
          characterName: 'Legacy Slash Asset',
          status: 'accepted',
          source: 'human',
          confidence: 1,
          updatedAt: '2026-01-01T00:00:00.000Z',
        },
      },
      box_rejections: {},
      events: [],
      receipt_path: 'asset_a_row0015.json',
      updated_at: '2026-01-01T00:00:00.000Z',
    }, null, 2)}\n`, 'utf-8')
    const legacyCollisionB = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      asset_uid: 'asset?a',
      row_index: legacyCollisionRowIndex,
      track_id: 'track_collision',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_collision@100',
      character_name: 'Fresh Question Asset',
      actor_name: '',
      confidence: 1,
    }, 'legacy-collision-b-accept')
    assert.notEqual(legacyCollisionB.receipt_path, 'asset_a_row0015.json')
    assert.equal(legacyCollisionB.labels.track_collision?.characterName, 'Fresh Question Asset')

    const legacyBadRowAssetUid = 'legacy_bad_row_asset'
    await writeFile(path.join(receiptDir, `${legacyBadRowAssetUid}_row0016.json`), `${JSON.stringify({
      schema: 'watch.yolo_track_labels.v1',
      revision: 1,
      asset_uid: legacyBadRowAssetUid,
      row_index: 17,
      labels: {},
      box_rejections: {},
      events: [],
      receipt_path: `${legacyBadRowAssetUid}_row0016.json`,
      updated_at: '2026-01-01T00:00:00.000Z',
    }, null, 2)}\n`, 'utf-8')
    const legacyBadRow = await postJsonStatus(baseUrl, '/api/projects/watch/yolo-labels', {
      asset_uid: legacyBadRowAssetUid,
      row_index: 16,
      track_id: 'track_bad_row',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_bad_row@100',
      character_name: 'Bad Row',
      actor_name: '',
      confidence: 1,
    }, 'legacy-bad-row-accept')
    assert.equal(legacyBadRow.status, 422)
    assert.equal(legacyBadRow.json.code, 'MALFORMED_YOLO_RECEIPT')

    const retryScopeRowIndex = 21
    const retryScopeA = 'watch_retry_scope_a'
    const retryScopeB = 'watch_retry_scope_b'
    await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      asset_uid: retryScopeA,
      row_index: retryScopeRowIndex,
      track_id: 'track_retry',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_retry@100',
      character_name: 'Retry A',
      actor_name: '',
      confidence: 1,
    }, 'retry-scope-a-accept')
    await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      asset_uid: retryScopeB,
      row_index: retryScopeRowIndex,
      track_id: 'track_retry',
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_retry@100',
      character_name: 'Retry B',
      actor_name: '',
      confidence: 1,
    }, 'retry-scope-b-accept')
    const retryAssetOnly = await postJsonStatus(baseUrl, '/api/projects/watch/yolo-labels/retry-memory-sync', {
      asset_uid: retryScopeA,
    }, 'retry-scope-a-only')
    assert.equal(retryAssetOnly.status, 200)
    assert.equal(retryAssetOnly.json.attempted, 1)
    assert.equal(retryAssetOnly.json.failed, 1)
    const retryScopeBRoute = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(retryScopeB)}&row_index=${retryScopeRowIndex}`
    const retryScopeBAfter = await requestJson(baseUrl, 'GET', retryScopeBRoute)
    assert.equal(retryScopeBAfter.events[0].memory_sync.attempts, 1)

    const acceptedMarcus = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      ...common,
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_15@100',
      character_name: 'Marcus',
      actor_name: 'Tony Cox',
      confidence: 1,
    }, 'row10-accept-marcus')
    assert.equal(acceptedMarcus.memory_sync, 'failed')
    assert.equal(acceptedMarcus.events[0].memory_sync.state, 'failed')
    assert.equal(acceptedMarcus.events[0].memory_sync.attempts, 1)

    const duplicateMarcus = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      ...common,
      action: 'accept',
      time_seconds: 1,
      box_key: 'track_15@100',
      character_name: 'Marcus',
      actor_name: 'Tony Cox',
      confidence: 1,
    }, 'row10-accept-marcus')
    assert.equal(duplicateMarcus.events.length, 1)
    assert.equal(duplicateMarcus.revision, acceptedMarcus.revision)

    const stopped = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      ...common,
      action: 'reject_box',
      time_seconds: 1.79,
      box_key: stopBoxKey,
    }, 'row10-stop')
    assert.equal(stopped.memory_sync, 'failed')

    const acceptedWillie = await requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', {
      ...common,
      action: 'accept',
      time_seconds: 4.54,
      box_key: 'track_15@454',
      character_name: 'Willie',
      actor_name: 'Billy Bob Thornton',
      confidence: 1,
    }, 'row10-accept-willie')
    assert.equal(acceptedWillie.memory_sync, 'failed')

    const rehydrated = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.equal(rehydrated.schema, 'watch.yolo_track_labels.v1')
    assert.equal(rehydrated.receipt_format_version, 2)
    assert.deepEqual(rehydrated.events.map((event) => event.sequence), [1, 2, 3])
    assert.deepEqual(rehydrated.events.map((event) => event.idempotency_key), [
      'row10-accept-marcus',
      'row10-stop',
      'row10-accept-willie',
    ])
    assert.deepEqual(rehydrated.events.map((event) => event.action), ['accept', 'reject_box', 'accept'])
    assert.ok(rehydrated.revision >= 6, 'receipt revision should increment for event and sync state persists')
    assert.equal(rehydrated.labels[trackId]?.characterName, 'Willie')
    assert.equal(rehydrated.events.every((event) => event.memory_sync.state === 'failed'), true)
    assert.equal(path.isAbsolute(rehydrated.receipt_path), false)

    const persistedPath = path.join(receiptDir, rehydrated.receipt_path)
    const persisted = JSON.parse(await readFile(persistedPath, 'utf-8')) as YoloReceipt
    assert.deepEqual(persisted.events, rehydrated.events)
    assert.deepEqual(persisted.labels, rehydrated.labels)
    assert.deepEqual(persisted.box_rejections, rehydrated.box_rejections)

    await stopChild(child)
    child = null

    const restarted = await startServer(receiptDir, apiPort, unavailableMemoryPort)
    child = restarted.child
    const afterRestart = await requestJson(restarted.baseUrl, 'GET', receiptRoute)
    assert.deepEqual(afterRestart.events, rehydrated.events)

    const projectionBefore = await requestProjection(restarted.baseUrl, 0.5) as { label: null | { characterName: string } }
    const projectionJustBeforeMarcus = await requestProjection(restarted.baseUrl, 0.999) as { label: null | { characterName: string } }
    const projectionAtMarcus = await requestProjection(restarted.baseUrl, 1) as { label: null | { characterName: string } }
    const projectionMarcus = await requestProjection(restarted.baseUrl, 1.2) as { label: null | { characterName: string } }
    const projectionJustBeforeStop = await requestProjection(restarted.baseUrl, 1.789) as { label: null | { characterName: string } }
    const projectionAtStop = await requestProjection(restarted.baseUrl, 1.79) as { label: null | { characterName: string } }
    const projectionStop = await requestProjection(restarted.baseUrl, 2.02) as { label: null | { characterName: string } }
    const projectionJustBeforeWillie = await requestProjection(restarted.baseUrl, 4.539) as { label: null | { characterName: string } }
    const projectionAtWillie = await requestProjection(restarted.baseUrl, 4.54) as { label: null | { characterName: string } }
    const projectionWillie = await requestProjection(restarted.baseUrl, 5) as { label: null | { characterName: string } }
    assert.equal(projectionBefore.label, null)
    assert.equal(projectionJustBeforeMarcus.label, null)
    assert.equal(projectionAtMarcus.label?.characterName, 'Marcus')
    assert.equal(projectionMarcus.label?.characterName, 'Marcus')
    assert.equal(projectionJustBeforeStop.label?.characterName, 'Marcus')
    assert.equal(projectionAtStop.label, null)
    assert.equal(projectionStop.label, null)
    assert.equal(projectionJustBeforeWillie.label, null)
    assert.equal(projectionAtWillie.label?.characterName, 'Willie')
    assert.equal(projectionWillie.label?.characterName, 'Willie')

    assert.deepEqual(
      projectionStop.label,
      projectYoloTrackLabelAtTime({
        trackId,
        timeSeconds: 2.02,
        events: afterRestart.events,
        labels: afterRestart.labels,
      }),
    )

    const overlay = {
      overlay_id: trackId,
      segment_id: 'row10',
      track_id: trackId,
      time_range: { start_seconds: 0, end_seconds: 24 },
      anchor_media_time_seconds: 0,
      valid_at_media_time_seconds: 0,
      bbox_policy: 'detector',
      track_lifecycle_status: 'active',
      stale_after_ms: 0,
      detected_class: 'person',
      classification: 'person',
      identity_status: 'YOLO_TRACK',
      visibility_proof: true,
      bbox_percent: { left: 10, top: 10, width: 40, height: 70 },
      render_policy: {},
    } as Parameters<typeof yoloLabelForOverlay>[0]

    assert.equal(
      yoloLabelForOverlay(
        overlay,
        [],
        {
          [trackId]: {
            trackId,
            characterName: 'Marcus',
            actorName: 'Tony Cox',
            status: 'accepted',
            source: 'human',
            confidence: 1,
            updatedAt: '2026-01-01T00:00:00.000Z',
          },
        },
        {},
        {
          'track_15@179': {
            boxKey: 'track_15@179',
            trackId,
            timeSeconds: 1.79,
            status: 'rejected',
            source: 'human',
            updatedAt: '2026-01-01T00:00:01.000Z',
          },
        },
        1.789,
      )?.characterName,
      'Marcus',
    )
    assert.equal(
      yoloLabelForOverlay(
        overlay,
        [],
        {
          [trackId]: {
            trackId,
            characterName: 'Marcus',
            actorName: 'Tony Cox',
            status: 'accepted',
            source: 'human',
            confidence: 1,
            updatedAt: '2026-01-01T00:00:00.000Z',
          },
        },
        {},
        {
          'track_15@179': {
            boxKey: 'track_15@179',
            trackId,
            timeSeconds: 1.79,
            status: 'rejected',
            source: 'human',
            updatedAt: '2026-01-01T00:00:01.000Z',
          },
        },
        1.79,
      ),
      null,
    )

    assert.equal(
      yoloLabelForOverlay(
        overlay,
        [],
        {
          [trackId]: {
            trackId,
            characterName: 'Marcus',
            actorName: 'Tony Cox',
            status: 'accepted',
            source: 'human',
            confidence: 1,
            updatedAt: '2026-01-01T00:00:00.000Z',
          },
        },
        {},
        {
          'track_15@100': {
            boxKey: 'track_15@100',
            trackId,
            timeSeconds: 1,
            status: 'rejected',
            source: 'human',
            updatedAt: '2026-01-01T00:00:01.000Z',
          },
        },
        1,
      ),
      null,
    )

    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 0.5), null)
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 0.999), null)
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 1)?.characterName, 'Marcus')
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 1.2)?.characterName, 'Marcus')
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 1.789)?.characterName, 'Marcus')
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 1.79), null)
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 2.02), null)
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 4.539), null)
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 4.54)?.characterName, 'Willie')
    assert.equal(yoloLabelForOverlay(overlay, afterRestart.events, afterRestart.labels, {}, {}, 5)?.characterName, 'Willie')
  } finally {
    if (child) await stopChild(child)
    await rm(receiptDir, { recursive: true, force: true })
  }
}

main()
  .then(() => {
    console.log('watchYoloLabelReceiptReplay smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
