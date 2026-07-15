import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

type IdentitySuggestionResponse = {
  schema: string
  status: string
  track_id: string
  suggestion: {
    character_name: string
    actor_name?: string
    confidence: number
    basis?: string[]
    tentative: boolean
    display_label?: string
  } | null
  memory?: {
    schema: string
    found?: boolean
    confidence?: number
    suggestions?: Array<{
      character_name: string
      actor_name?: string
      confidence?: number
      tentative?: boolean
      display_label?: string
    }>
    qdrant?: {
      collection?: string
      returned_hits?: number
      usable_hits?: number
    }
    proof_scope?: {
      mocked?: boolean
      live?: boolean
      exercised?: string[]
      proves?: string[]
      does_not_prove?: string[]
    }
  }
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const watchRoot = path.resolve(uiRoot, '..')
const assetUid = 'bad_santa_unrated_2003_brrip_xvidhd_720p_npw'
const rowIndex = 9
const trackId = 'track_2'
const timeSeconds = 12.515
const cropPath = path.join(
  watchRoot,
  'docs/architecture/generated/watch_identity_qdrant_marcus_eval',
  '20260704T172759115162Z_yolo_track_2_only/crops',
  'sample_15_12.515_marcus_detector_9_track_2_interpolated.png',
)
const row9ReceiptPath = path.join(
  watchRoot,
  'docs/architecture/generated/watch_yolo_track_labels',
  `${assetUid}_row0009.json`,
)

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

async function optionalFileBytes(filePath: string): Promise<Buffer | null> {
  if (!existsSync(filePath)) return null
  return readFile(filePath)
}

async function waitForMemory(memoryBaseUrl: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      const response = await fetch(`${memoryBaseUrl}/health`, {
        headers: { 'X-Caller-Skill': 'watch' },
      })
      if (response.ok) return
    } catch {
      // Keep polling; this is a live dependency, not a mocked service.
    }
    await delay(100)
  }
  throw new Error(`Memory daemon is not reachable at ${memoryBaseUrl}; live suggestion smoke cannot run`)
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
  const memoryBaseUrl = process.env.MEMORY_DAEMON_URL || 'http://127.0.0.1:8601'
  await waitForMemory(memoryBaseUrl)

  const crop = await readFile(cropPath)
  assert.ok(crop.byteLength > 1_000, `expected a real crop image at ${cropPath}`)
  const imageDataUrl = `data:image/png;base64,${crop.toString('base64')}`
  const receiptBefore = await optionalFileBytes(row9ReceiptPath)

  const apiPort = await unusedLocalPort()
  const baseUrl = `http://127.0.0.1:${apiPort}`
  let stdout = ''
  let stderr = ''
  let spawnError: Error | null = null

  const tsxCommand = process.platform === 'win32' ? 'tsx.cmd' : 'tsx'
  const child = spawn(tsxCommand, ['server/index.ts'], {
    cwd: uiRoot,
    env: {
      ...process.env,
      WATCH_API_PORT: String(apiPort),
      MEMORY_DAEMON_URL: memoryBaseUrl,
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

    const response = await fetch(`${baseUrl}/api/projects/watch/identity-suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        asset_uid: assetUid,
        row_index: rowIndex,
        track_id: trackId,
        time_seconds: timeSeconds,
        image_data_url: imageDataUrl,
        q: 'Who does this YOLO person crop most look like in Bad Santa row 9?',
      }),
    })
    const text = await response.text()
    assert.equal(response.status, 200, `identity-suggestions returned ${response.status}: ${text}`)

    const data = JSON.parse(text) as IdentitySuggestionResponse
    assert.equal(data.schema, 'watch.identity_suggestions.v1')
    assert.equal(data.status, 'ok')
    assert.equal(data.track_id, trackId)
    assert.ok(data.suggestion, 'expected a tentative Watch suggestion')
    assert.equal(data.suggestion.character_name, 'Marcus')
    assert.equal(data.suggestion.tentative, true)
    assert.ok(
      data.suggestion.confidence >= 0.82,
      `expected Marcus confidence >= 0.82, got ${data.suggestion.confidence}`,
    )
    assert.match(data.suggestion.display_label || '', /^Marcus\?\s+0\.\d+/)

    assert.equal(data.memory?.schema, 'memory.watch_identity_crop_recall.v1')
    assert.equal(data.memory?.found, true)
    assert.ok(
      typeof data.memory?.confidence === 'number' && data.memory.confidence >= 0.82,
      `expected live Memory confidence >= 0.82, got ${data.memory?.confidence}`,
    )
    assert.equal(data.memory?.proof_scope?.mocked, false)
    assert.equal(data.memory?.proof_scope?.live, true)
    const exercised = [
      ...(data.memory?.proof_scope?.exercised || []),
      ...(data.memory?.proof_scope?.proves || []),
    ].join('\n')
    assert.match(exercised, /image_embedding/)
    assert.match(exercised, /qdrant/i)
    assert.match(exercised, /arangodb|hydration/i)
    assert.ok(
      (data.memory?.qdrant?.usable_hits || 0) > 0,
      `expected hydrated Qdrant hits, got ${data.memory?.qdrant?.usable_hits}`,
    )

    const receiptAfter = await optionalFileBytes(row9ReceiptPath)
    assert.deepEqual(
      receiptAfter,
      receiptBefore,
      'identity suggestions must not mutate the persisted row-9 YOLO label receipt',
    )
  } finally {
    await stopChild(child)
  }
}

main()
  .then(() => {
    console.log('watchMemorySuggestionLive smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
