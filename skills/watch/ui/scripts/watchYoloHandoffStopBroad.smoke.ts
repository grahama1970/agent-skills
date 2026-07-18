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

type YoloReceipt = {
  schema: string
  asset_uid: string
  row_index: number
  labels: Record<string, unknown>
  box_rejections: Record<string, { trackId: string; status: string; timeSeconds: number }>
  events: ReceiptEvent[]
  receipt_path: string
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const assetUid = 'watch_handoff_stop_broad_fixture'
const rowIndex = 11

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
  assert.equal(response.status, 200, `${method} ${route} returned ${response.status}: ${text}`)
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

function overlayFor(trackId: string) {
  return {
    overlay_id: trackId,
    segment_id: `row${rowIndex}`,
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
}

async function main(): Promise<void> {
  const receiptDir = await mkdtemp(path.join(tmpdir(), 'watch-yolo-handoff-broad-'))
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
      timecode: '04:24',
      movie_segment: '04:24-04:48',
    }
    const post = (body: Record<string, unknown>) =>
      requestJson(baseUrl, 'POST', '/api/projects/watch/yolo-labels', { ...common, ...body })

    // track_21: two full assign -> stop -> reassign cycles (broad handoff-stop).
    await post({ track_id: 'track_21', action: 'accept', time_seconds: 1, box_key: 'track_21@100', character_name: 'Marcus', actor_name: 'Tony Cox', confidence: 1 })
    await post({ track_id: 'track_21', action: 'reject_box', time_seconds: 2, box_key: 'track_21@200' })
    await post({ track_id: 'track_21', action: 'accept', time_seconds: 3, box_key: 'track_21@300', character_name: 'Willie', actor_name: 'Billy Bob Thornton', confidence: 1 })
    await post({ track_id: 'track_21', action: 'reject_box', time_seconds: 4, box_key: 'track_21@400' })
    await post({ track_id: 'track_21', action: 'accept', time_seconds: 5, box_key: 'track_21@500', character_name: 'Marcus', actor_name: 'Tony Cox', confidence: 1 })

    // track_22: single accept, never stopped — must be isolated from track_21 stops.
    await post({ track_id: 'track_22', action: 'accept', time_seconds: 1.2, box_key: 'track_22@120', character_name: 'Willie', actor_name: 'Billy Bob Thornton', confidence: 1 })

    // track_23: rejection arrives before any accept — a rejected box must never
    // create or resurrect an identity.
    await post({ track_id: 'track_23', action: 'reject_box', time_seconds: 0.8, box_key: 'track_23@80' })
    await post({ track_id: 'track_23', action: 'accept', time_seconds: 3, box_key: 'track_23@300', character_name: 'Sue', actor_name: 'Lauren Graham', confidence: 1 })

    const receipt = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.equal(receipt.events.length, 8)

    const events = receipt.events as Parameters<typeof yoloLabelForOverlay>[1]
    const labels = receipt.labels as Parameters<typeof yoloLabelForOverlay>[2]
    const rejections = receipt.box_rejections as Parameters<typeof yoloLabelForOverlay>[4]
    const labelAt = (trackId: string, time: number) =>
      yoloLabelForOverlay(overlayFor(trackId), events, labels, {}, rejections, time)?.characterName ?? null

    // track_21 epochs: every stop closes the previous identity and no epoch
    // leaks into the next.
    assert.equal(labelAt('track_21', 0.5), null)
    assert.equal(labelAt('track_21', 1.5), 'Marcus')
    assert.equal(labelAt('track_21', 2.5), null)
    assert.equal(labelAt('track_21', 3.5), 'Willie')
    assert.equal(labelAt('track_21', 4.5), null)
    assert.equal(labelAt('track_21', 6), 'Marcus')

    // track_22 is unaffected by track_21 stops at the same timestamps.
    assert.equal(labelAt('track_22', 0.5), null)
    assert.equal(labelAt('track_22', 2.5), 'Willie')
    assert.equal(labelAt('track_22', 4.5), 'Willie')
    assert.equal(labelAt('track_22', 6), 'Willie')

    // track_23: rejection before any accept yields no identity anywhere before
    // the accept; the accept then bounds the identity start.
    assert.equal(labelAt('track_23', 0.8), null)
    assert.equal(labelAt('track_23', 2), null)
    assert.equal(labelAt('track_23', 3.5), 'Sue')

    // Rejected boxes are recorded as rejections, never as labels.
    assert.equal(receipt.box_rejections['track_21@200']?.status, 'rejected')
    assert.equal(receipt.box_rejections['track_21@400']?.status, 'rejected')
    assert.equal(receipt.box_rejections['track_23@80']?.status, 'rejected')
    for (const rejectedKey of ['track_21@200', 'track_21@400', 'track_23@80']) {
      assert.ok(!(rejectedKey in receipt.labels), `rejected box ${rejectedKey} must not appear in labels`)
    }

    // Poisoning resistance on the stale-label fallback path: a track with no
    // events falls back to the labels record, but a rejection at the exact box
    // instant still wins.
    const staleLabels = {
      track_99: {
        trackId: 'track_99',
        characterName: 'Marcus',
        status: 'accepted',
        source: 'human',
        updatedAt: new Date().toISOString(),
      },
    } as Parameters<typeof yoloLabelForOverlay>[2]
    const staleRejections = {
      'track_99@150': {
        boxKey: 'track_99@150',
        trackId: 'track_99',
        timeSeconds: 1.5,
        status: 'rejected',
        source: 'human',
        updatedAt: new Date().toISOString(),
      },
    } as Parameters<typeof yoloLabelForOverlay>[4]
    assert.equal(
      yoloLabelForOverlay(overlayFor('track_99'), [], staleLabels, {}, staleRejections, 1.5)?.characterName ?? null,
      null,
    )
    assert.equal(
      yoloLabelForOverlay(overlayFor('track_99'), [], staleLabels, {}, staleRejections, 3)?.characterName,
      'Marcus',
    )

    // Rehydration: the persisted receipt equals the served state.
    const persisted = JSON.parse(await readFile(receipt.receipt_path, 'utf-8')) as YoloReceipt
    assert.equal(path.dirname(receipt.receipt_path), receiptDir)
    assert.deepEqual(persisted.events, receipt.events)
    assert.deepEqual(persisted.labels, receipt.labels)
    assert.deepEqual(persisted.box_rejections, receipt.box_rejections)

    const reread = await requestJson(baseUrl, 'GET', receiptRoute)
    assert.deepEqual(reread.events, receipt.events)
    assert.deepEqual(reread.labels, receipt.labels)
    assert.deepEqual(reread.box_rejections, receipt.box_rejections)
  } finally {
    await stopChild(child)
    await rm(receiptDir, { recursive: true, force: true })
  }
}

main()
  .then(() => {
    console.log('watchYoloHandoffStopBroad smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
