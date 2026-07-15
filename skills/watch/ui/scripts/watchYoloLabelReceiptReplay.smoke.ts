import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

import { yoloLabelForOverlay } from '../components/WatchReportView'

type ReceiptEvent = {
  action: string
  status?: string
  track_id: string
  box_key?: string
  time_seconds?: number | null
  character_name?: string
  actor_name?: string
  confidence?: number
}

type ReceiptLabel = {
  trackId: string
  characterName: string
  actorName?: string
  status: 'accepted'
  source: 'human'
  confidence?: number
  updatedAt: string
}

type ReceiptRejection = {
  boxKey: string
  trackId: string
  timeSeconds: number
  status: 'rejected'
  source: 'human'
  updatedAt: string
}

type YoloReceipt = {
  schema: string
  asset_uid: string
  row_index: number
  labels: Record<string, ReceiptLabel>
  box_rejections: Record<string, ReceiptRejection>
  events: ReceiptEvent[]
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

async function requestJson(
  baseUrl: string,
  method: 'GET' | 'POST',
  route: string,
  body?: Record<string, unknown>,
): Promise<YoloReceipt> {
  const response = await fetch(`${baseUrl}${route}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await response.text()
  assert.equal(
    response.status,
    200,
    `${method} ${route} returned ${response.status}: ${text}`,
  )
  return JSON.parse(text) as YoloReceipt
}

async function waitForApi(
  baseUrl: string,
  child: ChildProcess,
  diagnostics: () => string,
  spawnFailure: () => Error | null,
): Promise<void> {
  const route = `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(assetUid)}&row_index=${rowIndex}`
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const failure = spawnFailure()
    if (failure) throw failure
    if (child.exitCode !== null) {
      throw new Error(`Watch API exited before readiness with ${child.exitCode}\n${diagnostics()}`)
    }
    try {
      const response = await fetch(`${baseUrl}${route}`)
      if (response.ok) return
    } catch {
      // The server has not bound the socket yet.
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

async function main(): Promise<void> {
  const receiptDir = await mkdtemp(path.join(tmpdir(), 'watch-yolo-label-receipt-'))
  const apiPort = await unusedLocalPort()
  const unavailableMemoryPort = await unusedLocalPort()
  const baseUrl = `http://127.0.0.1:${apiPort}`
  const receiptRoute =
    `/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(assetUid)}&row_index=${rowIndex}`

  let stdout = ''
  let stderr = ''
  let spawnError: Error | null = null

  const tsxCommand = process.platform === 'win32' ? 'tsx.cmd' : 'tsx'
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
  child.on('error', (error) => {
    spawnError = error
  })

  try {
    await waitForApi(
      baseUrl,
      child,
      () => `${stdout}\n${stderr}`,
      () => spawnError,
    )

    const common = {
      asset_uid: assetUid,
      row_index: rowIndex,
      track_id: trackId,
      timecode: '04:00',
      movie_segment: '04:00-04:24',
    }

    const acceptedMarcus = await requestJson(
      baseUrl,
      'POST',
      '/api/projects/watch/yolo-labels',
      {
        ...common,
        action: 'accept',
        time_seconds: 1,
        box_key: 'track_15@100',
        character_name: 'Marcus',
        actor_name: 'Tony Cox',
        confidence: 1,
      },
    )
    assert.equal(acceptedMarcus.memory_sync, 'failed')
    assert.ok(acceptedMarcus.memory_sync_error)

    const afterMarcus = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.equal(afterMarcus.labels[trackId]?.characterName, 'Marcus')
    assert.equal(afterMarcus.events.length, 1)
    assert.equal(afterMarcus.events[0]?.action, 'accept')
    assert.equal(afterMarcus.events[0]?.character_name, 'Marcus')
    assert.equal(afterMarcus.events[0]?.time_seconds, 1)

    const stopped = await requestJson(
      baseUrl,
      'POST',
      '/api/projects/watch/yolo-labels',
      {
        ...common,
        action: 'reject_box',
        time_seconds: 1.79,
        box_key: stopBoxKey,
      },
    )
    assert.equal(stopped.memory_sync, 'failed')
    assert.ok(stopped.memory_sync_error)

    const afterStop = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.equal(afterStop.events.length, 2)
    assert.equal(afterStop.events[1]?.action, 'reject_box')
    assert.equal(afterStop.events[1]?.status, 'rejected_box')
    assert.equal(afterStop.events[1]?.time_seconds, 1.79)
    assert.equal(afterStop.box_rejections[stopBoxKey]?.trackId, trackId)
    assert.equal(afterStop.box_rejections[stopBoxKey]?.timeSeconds, 1.79)

    const acceptedWillie = await requestJson(
      baseUrl,
      'POST',
      '/api/projects/watch/yolo-labels',
      {
        ...common,
        action: 'accept',
        time_seconds: 4.54,
        box_key: 'track_15@454',
        character_name: 'Willie',
        actor_name: 'Billy Bob Thornton',
        confidence: 1,
      },
    )
    assert.equal(acceptedWillie.memory_sync, 'failed')
    assert.ok(acceptedWillie.memory_sync_error)

    const rehydrated = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.equal(rehydrated.labels[trackId]?.characterName, 'Willie')
    assert.equal(rehydrated.box_rejections[stopBoxKey]?.status, 'rejected')
    assert.deepEqual(
      rehydrated.events.map((event) => ({
        action: event.action,
        status: event.status,
        character_name: event.character_name ?? null,
        time_seconds: event.time_seconds,
      })),
      [
        { action: 'accept', status: 'accepted', character_name: 'Marcus', time_seconds: 1 },
        { action: 'reject_box', status: 'rejected_box', character_name: null, time_seconds: 1.79 },
        { action: 'accept', status: 'accepted', character_name: 'Willie', time_seconds: 4.54 },
      ],
    )

    const persisted = JSON.parse(await readFile(rehydrated.receipt_path, 'utf-8')) as YoloReceipt
    assert.equal(path.dirname(rehydrated.receipt_path), receiptDir)
    assert.deepEqual(persisted.events, rehydrated.events)
    assert.deepEqual(persisted.labels, rehydrated.labels)
    assert.deepEqual(persisted.box_rejections, rehydrated.box_rejections)

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

    const events = rehydrated.events as Parameters<typeof yoloLabelForOverlay>[1]
    const labels = rehydrated.labels as Parameters<typeof yoloLabelForOverlay>[2]
    const rejections = rehydrated.box_rejections as Parameters<typeof yoloLabelForOverlay>[4]

    assert.equal(
      yoloLabelForOverlay(overlay, events, labels, {}, rejections, 0.5)?.characterName ?? null,
      null,
    )
    assert.equal(
      yoloLabelForOverlay(overlay, events, labels, {}, rejections, 1.2)?.characterName,
      'Marcus',
    )
    assert.equal(
      yoloLabelForOverlay(overlay, events, labels, {}, rejections, 2.02)?.characterName ?? null,
      null,
    )
    assert.equal(
      yoloLabelForOverlay(overlay, events, labels, {}, rejections, 5)?.characterName,
      'Willie',
    )
  } finally {
    await stopChild(child)
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
